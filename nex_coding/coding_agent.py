"""LangGraph ReAct agent with read/list tools and staged writes (no disk writes)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
        """Stage a full file body for the given path relative to the project root. Does NOT write to disk until the user confirms save. Call once per file; include complete working code."""
        try:
            resolve_under_root(root, relative_path)
        except ValueError as exc:
            return f"Error: {exc}"
        if not relative_path.strip():
            return "Error: empty path."
        staged_writes.append({"path": relative_path.strip().lstrip("/"), "content": content})
        return (
            f"Staged `{relative_path}` ({len(content)} characters). "
            "Nothing is on disk yet — the user must confirm save."
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
    recursion_limit: int = 40,
    stream_tokens: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """
    Run the LangGraph agent. Returns (staged_writes, assistant_summary).
    staged_writes: list of {path, content}.
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
        "You are Nex, an expert coding agent operating inside a single project directory.\n"
        f"Project root (all paths are relative to this): {root.resolve()}\n\n"
        "Use list_directory and read_file to explore the codebase when helpful.\n"
        "To deliver work, call stage_file_write once per file with the FULL path relative to the project root "
        "and the COMPLETE file contents. Prefer conventional layouts (e.g. src/package/module.py).\n"
        "Do not claim files exist on disk until the user confirms save — only staged writes count.\n"
        "Produce working, idiomatic code. If the user asked for a module, include what they need to run or import it."
    )

    graph = create_react_agent(model, tools)
    messages = [SystemMessage(content=system), HumanMessage(content=user_request)]
    run_config = {"recursion_limit": recursion_limit}
    state = {"messages": messages}

    result = _run_graph_with_stream(graph, state, run_config, stream_tokens)

    msgs = result.get("messages") or []
    summary = _final_ai_text(msgs)
    return staged, summary
