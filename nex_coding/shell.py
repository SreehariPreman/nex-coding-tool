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


def run_interactive_shell(start_dir: Path | None) -> int:
    """Run until the user exits. Returns a process exit code."""
    out = ui.stdout_console()
    err = ui.stderr_console()

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
            if cmd.startswith("@"):
                task = " ".join(parts).strip()
            else:
                task = " ".join(args).strip()
                
            if not task:
                ui.print_error(
                    err,
                    f"{cmd}: missing task. Example: [bold]create[/] a python file that prints primes up to 10",
                )
                continue
            from nex_coding.task_runner import run_task_and_confirm
            run_task_and_confirm(Path(os.getcwd()).resolve(), task)
            continue

        if cmd == "undo":
            run_undo(Path(os.getcwd()).resolve())
            continue

        if cmd in _INTERNAL:
            ui.print_error(err, f"internal command not implemented: {cmd}")
            continue

        if cmd not in _SUBPROCESS_ALLOW:
            ui.print_error(
                err,
                f"unknown or disallowed command: {cmd!r}. Type [bold]help[/] for what is supported.",
            )
            continue

        exe = shutil.which(cmd)
        if exe is None:
            ui.print_error(err, f"command not found on PATH: {cmd!r}")
            continue

        try:
            subprocess.run([exe, *args], cwd=os.getcwd())
        except OSError as exc:
            ui.print_error(err, f"could not run {cmd!r}: {exc}")
            continue
