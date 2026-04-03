"""Interactive Nex shell with a small set of familiar Unix-style commands."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from nex_coding import ui
from nex_coding.config import load_config, validate_config
from nex_coding.session import SessionContext
from nex_coding.task_runner import run_task_and_confirm, run_undo
import time

# Handled in this process so state (cwd) matches what users expect.
_INTERNAL = frozenset(
    {
        "cd",
        "pwd",
        "exit",
        "quit",
        "help",
        "clear",
        "create",
        "agent",
        "undo",
        "history",
        "context",
    }
)

# Run via PATH with no shell; first token must match exactly.
_SUBPROCESS_ALLOW = frozenset(
    {
        "ls",
        "cat",
        "echo",
        "mkdir",
        "rmdir",
        "rm",
        "cp",
        "mv",
        "touch",
        "ln",
        "chmod",
        "grep",
        "head",
        "tail",
        "wc",
        "sort",
        "uniq",
        "cut",
        "tr",
        "sed",
        "awk",
        "file",
        "which",
        "date",
        "cal",
        "whoami",
        "id",
        "uname",
        "env",
        "printenv",
        "du",
        "df",
        "less",
        "more",
        "nano",
        "vi",
        "vim",
    }
)


def _clear_screen() -> None:
    if sys.platform == "win32":
        os.system("cls")  # noqa: S605,S606 — no user input in argument
    else:
        # Prefer terminfo; fall back to common binaries.
        if shutil.which("clear"):
            subprocess.run(["clear"], check=False)  # noqa: S603,S607
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()


def _resolve_cd_target(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()
    return p


def _print_session_history(console, session) -> None:
    """Display the conversation history for the current session."""
    from rich import box
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table

    if not session.turns:
        console.print("[dim]No conversation history yet in this session.[/]")
        return

    console.print()
    console.print(Rule("[bold cyan]Session History[/]", style="cyan"))
    for i, turn in enumerate(session.turns, 1):
        req_short = turn.request.replace("\n", " ")[:80]
        status = "[red]discarded[/]" if turn.discarded else (
            f"[green]saved {len(turn.saved)} file(s)[/]" if turn.saved else "[dim]no files[/]"
        )
        console.print(f"  [bold cyan]{i}.[/] [white]{req_short}[/]")
        console.print(f"     {status}")
        if turn.staged and not turn.discarded:
            for f in turn.staged:
                mark = "✔" if f in turn.saved else "✘"
                color = "green" if f in turn.saved else "dim"
                console.print(f"     [{color}]{mark} {f}[/]")
    console.print()


def _print_session_context(console, session) -> None:
    """Display the saved-files snapshot for the current session."""
    from rich.rule import Rule
    from rich.tree import Tree

    if not session.saved_files:
        console.print("[dim]No files saved in this session yet.[/]")
        return

    console.print()
    console.print(Rule("[bold cyan]Session Context[/] [dim](files on disk from this session)[/]", style="cyan"))
    tree = Tree("[bold cyan]📦 Saved this session[/]", guide_style="dim cyan")
    for path in sorted(session.saved_files):
        lines = session.saved_files[path].count("\n") + 1
        tree.add(f"[white]{path}[/]  [dim]{lines} lines[/]")
    console.print(tree)
    console.print()


def run_interactive_shell(start_dir: Path | None) -> int:
    """Run until the user exits. Returns a process exit code."""
    out = ui.stdout_console()
    err = ui.stderr_console()

    # One session context per shell invocation
    session = SessionContext()

    base = (start_dir or Path.cwd()).resolve()
    if not base.is_dir():
        ui.print_error(err, f"not a directory: {base}")
        return 1

    try:
        os.chdir(base)
    except OSError as exc:
        ui.print_error(err, f"cannot change directory to {base}: {exc}")
        return 1

    try:
        import readline  # noqa: F401 — side effect: enables editing/history
    except ImportError:
        pass

    _clear_screen()
    out.print("\n[bold dim]nex starting...[/]")
    time.sleep(0.2)
    
    cfg = load_config(os.getcwd())
    src = cfg.get("_source", "None")
    is_valid, msg = validate_config(cfg)
    
    if src != "None":
        out.print(f"[green]✓[/] Config found — {Path(src).name}")
    else:
        out.print("[yellow]![/] No active config found")

    provider = cfg.get("provider")
    if provider and provider != "none":
        out.print(f"[green]✓[/] Provider — {provider.capitalize()}")
    
    model = cfg.get("model")
    if model:
        out.print(f"[green]✓[/] Model — {model}")
        
    if provider and provider != "none":
        if is_valid:
            out.print("[green]✓[/] API key — valid")
            out.print("[green]✓[/] Ready")
        else:
            out.print(f"[red]✗[/] API key invalid — {msg}. Check {Path(src).name}")
    
    time.sleep(0.4)
    ui.print_welcome(out, os.getcwd(), cfg)

    while True:
        try:
            line = out.input(ui.prompt_markup(os.getcwd()))
        except EOFError:
            out.print()
            ui.print_goodbye(out)
            return 0
        except KeyboardInterrupt:
            out.print()
            out.print(
                "[dim yellow]⌁[/] [yellow]Interrupted[/] — still in Nex; "
                "[dim]exit[/] or [dim]Ctrl+D[/] to leave."
            )
            continue

        stripped = line.strip()
        if not stripped:
            continue

        try:
            parts = shlex.split(stripped, posix=os.name != "nt")
        except ValueError as exc:
            ui.print_error(err, str(exc))
            continue

        cmd = parts[0]
        args = parts[1:]

        if cmd in {"exit", "quit"}:
            ui.print_goodbye(out)
            return 0

        if cmd == "help":
            ui.print_help(out, _INTERNAL, _SUBPROCESS_ALLOW)
            continue

        if cmd == "clear":
            _clear_screen()
            continue

        if cmd == "pwd":
            out.print(f"[green]{os.getcwd()}[/]")
            continue

        if cmd == "cd":
            if len(args) > 1:
                ui.print_error(err, "cd: too many arguments")
                continue
            target = str(Path.home()) if not args else args[0]
            try:
                dest = _resolve_cd_target(target)
                os.chdir(dest)
            except OSError as exc:
                ui.print_error(err, f"cd: {exc}")
            continue

        if cmd in {"create", "agent"} or cmd.startswith("@"):
            # Explicit prefix: strip the keyword, use the rest as the task.
            if cmd.startswith("@"):
                task = stripped
            else:
                task = " ".join(args).strip() or stripped
            run_task_and_confirm(Path(os.getcwd()).resolve(), task, session)
            continue

        if cmd == "undo":
            run_undo(Path(os.getcwd()).resolve())
            continue

        if cmd == "history":
            _print_session_history(out, session)
            continue

        if cmd == "context":
            _print_session_context(out, session)
            continue

        # ── Known subprocess commands (ls, cat, grep, …) ──────────────────
        if cmd in _SUBPROCESS_ALLOW:
            exe = shutil.which(cmd)
            if exe is None:
                ui.print_error(err, f"command not found on PATH: {cmd!r}")
            else:
                try:
                    subprocess.run([exe, *args], cwd=os.getcwd())
                except OSError as exc:
                    ui.print_error(err, f"could not run {cmd!r}: {exc}")
            continue

        # ── Everything else → natural-language agent request ─────────────
        # No prefix needed. Just type what you want.
        run_task_and_confirm(Path(os.getcwd()).resolve(), stripped, session)
