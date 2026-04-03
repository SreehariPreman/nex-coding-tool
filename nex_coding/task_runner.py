"""Run agent, preview staged files, confirm save, optional git commit."""

from __future__ import annotations

import sys
import re
import difflib
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax

from nex_coding import ui
from nex_coding.coding_agent import run_coding_agent
from nex_coding.config import load_config, validate_config
from nex_coding.fs_safe import resolve_under_root
from nex_coding.git_undo import commit_paths, is_git_repo, undo_last_save


def _preview_staged(console, root: Path, staged: list[dict[str, str]]) -> None:
    if not staged:
        console.print(Panel("[yellow]No files were staged by the agent.[/]", title="Preview"))
        return
    console.print(Rule("[bold]Preview — not saved yet[/]"))
    for item in staged:
        rel = item["path"]
        content = item.get("content", "")
        console.print(f"\n[bold cyan]{rel}[/]")
        try:
            path = resolve_under_root(root, rel)
            exist = path.exists()
        except ValueError:
            exist = False
            
        if exist:
            try:
                old_content = path.read_text(encoding="utf-8")
            except Exception:
                old_content = ""
                
            diff = list(difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                n=3
            ))
            if diff:
                diff_text = "".join(diff)
                console.print(Syntax(diff_text, lexer="diff", theme="monokai", line_numbers=False, word_wrap=True))
            else:
                console.print("[dim]No changes to this file.[/]")
        else:
            ext = Path(rel).suffix.lstrip(".") or "text"
            lang = "python" if ext == "py" else ext
            try:
                console.print(Syntax(content, lexer=lang, theme="monokai", line_numbers=True, word_wrap=True))
            except Exception:
                console.print(content)
    console.print()
    console.print(
        Panel(
            "[bold]Agent completed changes.[/] Nothing has been written to disk.\n"
            "Save? [bold](y/n)[/]",
            border_style="yellow",
        )
    )


def _apply_staged(root: Path, staged: list[dict[str, str]]) -> list[str]:
    written: list[str] = []
    for item in staged:
        rel = item["path"]
        path = resolve_under_root(root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.get("content", ""), encoding="utf-8")
        written.append(rel)
    return written


def run_task_and_confirm(cwd: Path, task: str) -> int:
    """Execute agent flow with confirmation. Returns process exit code."""
    out = ui.stdout_console()
    err = ui.stderr_console()

    cfg = load_config(str(cwd))
    ok, msg = validate_config(cfg)
    if not ok:
        ui.print_error(err, f"LLM configuration invalid: {msg}")
        return 1

    streamed_chunks: list[str] = []

    def _stream_to_terminal(text: str) -> None:
        if text:
            streamed_chunks.append(text)
            out.print(text, end="", highlight=False, markup=False)
            sys.stdout.flush()

    # Parse @ mentions to inject file content directly
    mentions = set(re.findall(r"@([^\s]+)", task))
    context_text = ""
    for m in mentions:
        try:
            p = resolve_under_root(cwd, m)
            if p.is_file():
                file_content = p.read_text(encoding="utf-8")
                context_text += f"\n\n--- Mentioned File: {m} ---\n{file_content}\n---------------------------\n"
        except Exception:
            pass
            
    if context_text:
        task += "\n" + context_text

    try:
        out.print(Rule("[bold cyan]Agent[/]", style="cyan"))
        staged, summary = run_coding_agent(
            cwd.resolve(),
            task,
            cfg,
            stream_tokens=_stream_to_terminal,
        )
    except RuntimeError as exc:
        ui.print_error(err, str(exc))
        return 1
    except Exception as exc:
        ui.print_error(err, f"Agent error: {exc}")
        return 1

    out.print()
    if not summary.strip() and streamed_chunks:
        summary = "".join(streamed_chunks)
    if not summary.strip():
        summary = "(Agent finished — see staged files below.)"
    if summary.strip() and not streamed_chunks:
        out.print(Panel(Markdown(summary), title="Agent", border_style="green"))
    _preview_staged(out, cwd, staged)

    if not staged:
        return 0

    try:
        answer = out.input("[bold]Save?[/] [cyan](y/n)[/] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        out.print("\n[dim]Cancelled — no files written.[/]")
        return 130

    if answer not in ("y", "yes"):
        out.print("[dim]Discarded staged changes — disk unchanged.[/]")
        return 0

    try:
        paths = _apply_staged(cwd.resolve(), staged)
    except OSError as exc:
        ui.print_error(err, f"Failed to write files: {exc}")
        return 1

    out.print(f"[green]Saved {len(paths)} file(s).[/]")

    if is_git_repo(cwd):
        snippet = task.replace("\n", " ").strip()[:60]
        cr = commit_paths(cwd.resolve(), paths, snippet or "agent save")
        if cr.ok:
            out.print(f"[dim]{cr.message}[/]")
        else:
            ui.print_error(
                err,
                f"{cr.message} Files are on disk; fix git and commit manually if needed.",
            )
            return 1
    else:
        out.print("[dim]Not a git repo — files saved without commit (undo unavailable).[/]")

    return 0


def run_undo(cwd: Path) -> int:
    out = ui.stdout_console()
    err = ui.stderr_console()
    res = undo_last_save(cwd.resolve())
    if res.ok:
        out.print(f"[green]{res.message}[/]")
        return 0
    ui.print_error(err, res.message)
    return 1
