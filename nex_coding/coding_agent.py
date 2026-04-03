"""LangGraph ReAct agent with read/list tools and staged writes (no disk writes)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from nex_coding.fs_safe import resolve_under_root


def _make_tools(
    root: Path,
    staged_writes: list[dict[str, str]],
    max_read_bytes: int = 256_000,
    max_list: int = 200,
) -> list[Callable[..., Any]]:
    root = root.resolve()

    @tool
    def read_file(relative_path: str) -> str:
        """Read a UTF-8 text file under the project root. Use a path relative to the project (e.g. src/app.py)."""
        try:
            path = resolve_under_root(root, relative_path)
        except ValueError as exc:
            return f"Error: {exc}"
        if not path.is_file():
            return f"Error: not a file: {relative_path}"
        try:
            data = path.read_bytes()
        except OSError as exc:
            return f"Error reading file: {exc}"
        if len(data) > max_read_bytes:
            return f"Error: file too large ({len(data)} bytes); max {max_read_bytes}."
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return "Error: file is not valid UTF-8 text."

    @tool
    def list_directory(relative_path: str = ".") -> str:
        """List files and subdirectories under relative_path (default: project root). Returns names, one per line."""
        try:
            base = resolve_under_root(root, relative_path)
        except ValueError as exc:
            return f"Error: {exc}"
        if not base.is_dir():
            return f"Error: not a directory: {relative_path}"
        try:
            entries = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            return f"Error: {exc}"
        lines: list[str] = []
        for p in entries[:max_list]:
            suffix = "/" if p.is_dir() else ""
            lines.append(f"{p.name}{suffix}")
        if len(entries) > max_list:
            lines.append(f"... ({len(entries) - max_list} more omitted)")
        return "\n".join(lines) if lines else "(empty)"

    @tool
    def stage_file_write(relative_path: str, content: str) -> str:
        """Stage a complete file for writing, given a path relative to the project root.

        Rules:
        - Call this once per file you want to create or modify.
        - For multi-file projects (e.g. web apps, packages) call this for EVERY file in the plan.
        - Include the FULL, COMPLETE content of each file — never truncate with comments like '# rest of file'.
        - Use conventional directory layouts:
          * Python packages: src/<package>/__init__.py, src/<package>/module.py, pyproject.toml, README.md
          * Web apps: frontend/index.html, frontend/style.css, frontend/app.js, backend/server.py, etc.
          * Node projects: src/index.js, package.json, .gitignore, README.md
        - Nested directories are created automatically; you may stage paths like 'backend/app.py'.
        - Nothing is written to disk until the user confirms.
        """
        try:
            resolve_under_root(root, relative_path)
        except ValueError as exc:
            return f"Error: {exc}"
        clean_path = relative_path.strip().lstrip("/")
        if not clean_path:
            return "Error: empty path."
        # Deduplicate: replace any previous staging of the same path
        for existing in staged_writes:
            if existing["path"] == clean_path:
                existing["content"] = content
                return (
            f"Updated staged `{clean_path}` ({len(content)} chars). "
            f"Nothing is on disk yet — the user must confirm save."
        )
        staged_writes.append({"path": clean_path, "content": content})
        total = len(staged_writes)
        return (
            f"Staged `{clean_path}` ({len(content)} chars) — "
            f"{total} file(s) staged so far. Nothing is on disk yet."
        )

    return [read_file, list_directory, stage_file_write]


def _build_chat_model(config: dict[str, Any]):
    provider = str(config.get("provider") or "").lower()
    model = config.get("model") or ""
    api_key = config.get("api_key")

    if provider in ("", "none"):
        raise RuntimeError("No LLM provider configured. Set provider and model in nex.toml or ~/.nex/config.toml.")

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model or "gpt-4o-mini",
            "streaming": True,
        }
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs = {
            "model": model or "claude-3-5-sonnet-20241022",
            "streaming": True,
        }
        if api_key:
            kwargs["api_key"] = api_key
        return ChatAnthropic(**kwargs)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": model or "gemini-1.5-flash"}
        if api_key:
            kwargs["google_api_key"] = api_key
        return ChatGoogleGenerativeAI(**kwargs)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or "llama3.2",
            base_url=os.environ.get("OLLAMA_BASE_URL"),
        )

    raise RuntimeError(f"Unsupported provider for agent: {provider!r}")


def _text_delta_from_chunk(msg: Any) -> str:
    """Extract printable text from an AIMessage / AIMessageChunk (streaming delta)."""
    c = getattr(msg, "content", None)
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            else:
                t = getattr(block, "text", None)
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(c)


def _final_ai_text(messages: list[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) or getattr(m, "type", None) == "ai":
            return _text_delta_from_chunk(m)
    return ""


def _consume_stream_part(
    part: Any,
    emit: Callable[[Any], None],
    set_values: Callable[[dict[str, Any]], None],
) -> None:
    """Normalize LangGraph stream chunks across v1 / v2 APIs."""
    if isinstance(part, dict) and "type" in part:
        ptype = part.get("type")
        data = part.get("data")
        if ptype == "messages" and isinstance(data, tuple) and data:
            emit(data[0])
        elif ptype == "values" and isinstance(data, dict):
            set_values(data)
        return

    if isinstance(part, tuple):
        if len(part) == 3:
            _, mode, payload = part
            if mode == "messages" and isinstance(payload, tuple) and payload:
                emit(payload[0])
            elif mode == "values" and isinstance(payload, dict):
                set_values(payload)
            return
        if len(part) == 2:
            a, b = part
            if isinstance(a, str):
                if a == "messages" and isinstance(b, tuple) and b:
                    emit(b[0])
                elif a == "values" and isinstance(b, dict):
                    set_values(b)
                return
            if hasattr(a, "content"):
                if getattr(a, "type", None) in ("human", "system", "tool"):
                    return
                emit(a)
                return


def _run_graph_with_stream(
    graph: Any,
    state: dict[str, Any],
    run_config: dict[str, Any],
    stream_tokens: Callable[[str], None] | None,
) -> dict[str, Any]:
    """Run compiled graph; stream LLM tokens when *stream_tokens* is set. Returns final state-like dict."""
    if not stream_tokens:
        return graph.invoke(state, config=run_config)

    last_values: dict[str, Any] | None = None

    def set_values(d: dict[str, Any]) -> None:
        nonlocal last_values
        last_values = d

    def emit(msg: Any) -> None:
        mtype = getattr(msg, "type", None)
        if mtype in ("human", "system", "tool"):
            return
        text = _text_delta_from_chunk(msg)
        if text:
            stream_tokens(text)

    stream_iter = None
    for extra in (
        {"stream_mode": ["messages", "values"], "version": "v2"},
        {"stream_mode": ["messages", "values"]},
        {"stream_mode": "messages"},
    ):
        try:
            stream_iter = graph.stream(state, config=run_config, **extra)
            break
        except TypeError:
            continue

    if stream_iter is None:
        return graph.invoke(state, config=run_config)

    for part in stream_iter:
        _consume_stream_part(part, emit, set_values)

    if isinstance(last_values, dict) and last_values.get("messages") is not None:
        return last_values
    try:
        snap = graph.get_state(run_config)
        vs = getattr(snap, "values", None)
        if isinstance(vs, dict) and vs.get("messages") is not None:
            return vs
    except Exception:
        pass
    return {"messages": []}


def run_coding_agent(
    root: Path,
    user_request: str,
    config: dict[str, Any],
    *,
    history: list[tuple[str, str]] | None = None,
    context_banner: str = "",
    recursion_limit: int = 40,
    stream_tokens: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """
    Run the LangGraph agent. Returns (staged_writes, assistant_summary).
    staged_writes: list of {path, content}.

    history: list of (role, text) pairs from prior turns.
             role is 'user' or 'assistant'.
    context_banner: optional text injected at the top of the user request
                    to remind the LLM what has already been built.
    If *stream_tokens* is set, model output is streamed chunk-by-chunk to the terminal.
    """
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Install with: pip install 'nex-coding-tool[agent]' "
            "or pip install langgraph langchain-openai (plus your provider package)."
        ) from exc

    staged: list[dict[str, str]] = []
    tools = _make_tools(root, staged)
    model = _build_chat_model(config)

    system = (
        "You are Nex, an expert full-stack coding agent operating inside a single project directory.\n"
        f"Project root (all paths are relative to this): {root.resolve()}\n\n"
        "## Exploration\n"
        "Use list_directory and read_file to understand any existing codebase before making changes.\n\n"
        "## Delivering work\n"
        "Call stage_file_write for EVERY file in your plan. Key rules:\n"
        "  1. Stage ALL files needed — do not skip boilerplate (e.g. __init__.py, package.json, .gitignore, README.md).\n"
        "  2. Each file must contain COMPLETE, working code — no truncation, no '# TODO: fill this in'.\n"
        "  3. Use conventional project layouts for the type of project requested.\n"
        "  4. When a user asks for a web app, include: HTML, CSS, JS frontend files AND a backend server file.\n"
        "  5. When a user asks for a Python package, include: __init__.py, pyproject.toml, README.md, and all modules.\n"
        "  6. Paths MUST be relative to the project root (e.g. 'backend/server.py', 'frontend/index.html').\n"
        "  7. Nested directories are created automatically — no need to create them explicitly.\n"
        "  8. Do not claim anything is on disk until the user confirms save.\n\n"
        "## Output\n"
        "After staging all files, give a short summary listing every staged file and what it does."
    )

    graph = create_react_agent(model, tools)

    # Build message list: system + prior history + current request
    messages: list[Any] = [SystemMessage(content=system)]

    for role, text in (history or []):
        if not text.strip():
            continue
        if role == "user":
            messages.append(HumanMessage(content=text))
        elif role == "assistant":
            messages.append(AIMessage(content=text))

    # Prepend the context banner (saved-files summary) to the current request
    full_request = (context_banner + user_request) if context_banner else user_request
    messages.append(HumanMessage(content=full_request))

    run_config = {"recursion_limit": recursion_limit}
    state = {"messages": messages}

    result = _run_graph_with_stream(graph, state, run_config, stream_tokens)

    msgs = result.get("messages") or []
    summary = _final_ai_text(msgs)
    return staged, summary
