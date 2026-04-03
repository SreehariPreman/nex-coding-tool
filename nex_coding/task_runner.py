"""Run agent, preview staged files, confirm save, optional git commit."""

from __future__ import annotations

import sys
import re
import difflib
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from nex_coding import ui
from nex_coding.coding_agent import run_coding_agent
from nex_coding.config import load_config, validate_config
from nex_coding.fs_safe import resolve_under_root
from nex_coding.git_undo import commit_paths, is_git_repo, undo_last_save
from nex_coding.session import SessionContext


# Map file extensions to Rich/Pygments lexer names
_EXT_TO_LEXER: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "jsx",
    "tsx": "tsx",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "json": "json",
    "toml": "toml",
    "yaml": "yaml",
    "yml": "yaml",
    "sh": "bash",
    "bash": "bash",
    "md": "markdown",
    "rs": "rust",
    "go": "go",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "env": "bash",
    "txt": "text",
    "xml": "xml",
}


def _lexer_for(path: str) -> str:
    name = Path(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    ext = Path(path).suffix.lstrip(".").lower()
    return _EXT_TO_LEXER.get(ext, "text")


def _file_tree_summary(staged: list[dict[str, str]], root: Path) -> Tree:
    """Build a Rich Tree showing all staged files, grouped by directory."""
    tree = Tree(
        f"[bold cyan]📦 Staged project[/] [dim]({len(staged)} file{'s' if len(staged) != 1 else ''})[/]",
        guide_style="dim cyan",
    )
    dirs: dict[str, list[dict]] = {}
    for item in staged:
        parts = Path(item["path"]).parts
        folder = str(Path(*parts[:-1])) if len(parts) > 1 else "."
        dirs.setdefault(folder, []).append(item)

    for folder in sorted(dirs):
        items = dirs[folder]
        if folder == ".":
            branch = tree
        else:
            branch = tree.add(f"[bold blue]📁 {folder}/[/]")
        for item in sorted(items, key=lambda x: x["path"]):
            fname = Path(item["path"]).name
            size = len(item.get("content", ""))
            try:
                path = resolve_under_root(root, item["path"])
                exists = path.exists()
            except ValueError:
                exists = False
            badge = "[yellow]✎ edit[/]" if exists else "[green]✚ new[/]"
            branch.add(f"[white]{fname}[/]  {badge}  [dim]{size:,} chars[/]")
    return tree


def _preview_single_file(
    console,
    root: Path,
    item: dict[str, str],
    index: int,
    total: int,
) -> None:
    rel = item["path"]
    content = item.get("content", "")
    lexer = _lexer_for(rel)

    header = f"[bold cyan][{index}/{total}][/] [bold white]{rel}[/]"
    try:
        path = resolve_under_root(root, rel)
        exists = path.exists()
    except ValueError:
        exists = False

    if exists:
        try:
            old_content = path.read_text(encoding="utf-8")
        except Exception:
            old_content = ""
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        ))
        if diff:
            console.print(Rule(header + " [yellow]✎ (diff)[/]"))
            console.print(Syntax("\n".join(diff), lexer="diff", theme="monokai",
                                 line_numbers=False, word_wrap=True))
        else:
            console.print(Rule(header + " [dim](unchanged)[/]"))
            console.print("[dim]No changes to this file.[/]")
    else:
        console.print(Rule(header + " [green]✚ (new)[/]"))
        try:
            console.print(Syntax(content, lexer=lexer, theme="monokai",
                                 line_numbers=True, word_wrap=True))
        except Exception:
            console.print(content)


def _preview_staged(console, root: Path, staged: list[dict[str, str]]) -> None:
    if not staged:
        console.print(Panel("[yellow]No files were staged by the agent.[/]", title="Preview"))
        return

    console.print()
    console.print(Rule("[bold cyan]Agent Preview[/] [dim]— nothing on disk yet[/]", style="cyan"))
    console.print()

    # Always show the file tree summary
    console.print(_file_tree_summary(staged, root))
    console.print()

    # Show each file's content
    total = len(staged)
    for i, item in enumerate(staged, 1):
        _preview_single_file(console, root, item, i, total)
        console.print()

    # Confirmation hint
    if total == 1:
        hint = "Save this file? [bold cyan](y/n)[/]"
    else:
        hint = (
            f"Save [bold]{total} files[/]? "
            "[bold cyan](y)[/] all  [bold cyan](n)[/] none  "
            "[bold cyan](1,3,...)[/] pick indices"
        )
    console.print(
        Panel(
            hint,
            border_style="yellow",
            box=box.ROUNDED,
            padding=(0, 2),
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


def run_task_and_confirm(
    cwd: Path,
    task: str,
    session: SessionContext | None = None,
) -> int:
    """Execute agent flow with confirmation. Returns process exit code.

    session: if provided, prior conversation history and saved-file context
             are injected into the agent, and the completed turn is recorded
             back into the session for future calls.
    """
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

    # Pull session context if available
    history = session.prior_messages_for_agent() if session else []
    context_banner = session.context_banner() if session else ""

    # Record the user turn in session before calling agent
    if session:
        session.record_user(task)

    # Show context indicator if we have prior turns
    if session and session.has_context():
        turn_num = session.turn_count + 1
        saved_count = len(session.saved_files)
        out.print(
            f"[dim cyan]Context: turn {turn_num} · "
            f"{saved_count} file{'s' if saved_count != 1 else ''} in session[/]"
        )

    try:
        out.print(Rule("[bold cyan]Agent[/]", style="cyan"))
        staged, summary = run_coding_agent(
            cwd.resolve(),
            task,
            cfg,
            history=history,
            context_banner=context_banner,
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
        # Still record assistant response so history is coherent
        if session:
            session.record_assistant(summary)
            session.record_turn(request=task, summary=summary, staged=[], saved=[])
        return 0

    total_staged = len(staged)
    try:
        if total_staged == 1:
            prompt = "[bold]Save?[/] [cyan](y/n)[/] "
        else:
            prompt = (
                f"[bold]Save {total_staged} files?[/] "
                "[cyan](y)[/] all  [cyan](n)[/] none  [cyan](1,3,...)[/] pick  — "
            )
        answer = out.input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        out.print("\n[dim]Cancelled — no files written.[/]")
        return 130

    # Determine which staged entries to actually save
    if answer in ("n", "no", ""):
        out.print("[dim]Discarded staged changes — disk unchanged.[/]")
        if session:
            session.record_assistant(summary)
            session.record_turn(request=task, summary=summary, staged=staged, saved=[], discarded=True)
        return 0
    elif answer in ("y", "yes"):
        to_save = staged
    else:
        # Parse comma-separated 1-based indices
        chosen: list[dict] = []
        bad: list[str] = []
        for token in answer.replace(" ", "").split(","):
            if not token:
                continue
            try:
                idx = int(token)
                if 1 <= idx <= total_staged:
                    chosen.append(staged[idx - 1])
                else:
                    bad.append(token)
            except ValueError:
                bad.append(token)
        if bad:
            ui.print_error(
                err,
                f"Invalid indices: {', '.join(bad)} — must be 1–{total_staged}. No files saved.",
            )
            return 1
        if not chosen:
            out.print("[dim]No files selected — disk unchanged.[/]")
            return 0
        to_save = chosen
        skipped = total_staged - len(to_save)
        if skipped:
            out.print(f"[dim]Saving {len(to_save)} of {total_staged} files ({skipped} skipped).[/]")

    try:
        paths = _apply_staged(cwd.resolve(), to_save)
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

    # Record the completed turn into the session
    if session:
        session.record_assistant(summary)
        session.record_turn(
            request=task,
            summary=summary,
            staged=staged,
            saved=paths,
        )

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
