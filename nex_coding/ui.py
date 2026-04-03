"""Rich-powered terminal presentation for the Nex shell."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.table import Table


def stdout_console() -> Console:
    return Console(highlight=False, soft_wrap=True)


def stderr_console() -> Console:
    return Console(highlight=False, stderr=True, soft_wrap=True)


def prompt_markup(cwd: str = "") -> str:
    return "[bold cyan]╭─[/][bold bright_blue]nex[/] [magenta]✨[/]\n[bold cyan]╰─❯[/] "


def _get_git_branch(cwd: str) -> str | None:
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        branch = res.stdout.strip()
        if branch:
            dirty_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False
            )
            is_dirty = bool(dirty_res.stdout.strip())
            return f"{branch}{'*' if is_dirty else ''}"
    except Exception:
        pass
    return None


def _get_env_info() -> str:
    py_version = platform.python_version()
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        venv_name = Path(venv).name
        return f"Python {py_version} ({venv_name})"
    return f"Python {py_version} (Global)"


def _get_project_stats(cwd: str) -> str:
    try:
        p = Path(cwd)
        files = [f for f in p.iterdir() if f.is_file()]
        dirs = [d for d in p.iterdir() if d.is_dir() and not d.name.startswith(".")]
        return f"{len(files)} files, {len(dirs)} folders"
    except Exception:
        return ""


def print_welcome(console: Console, cwd: str, config: dict = None) -> None:
    try:
        import pyfiglet
        ascii_logo = pyfiglet.figlet_format("NEXUS", font="slant")
        title = Text(ascii_logo, style="bold cyan")
    except ImportError:
        title = Text("NEXUS", style="bold cyan")
    
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()
    
    table.add_row("Directory", f"[bold cyan]{cwd}[/]")
    
    branch = _get_git_branch(cwd)
    if branch:
        table.add_row("Git Branch", f"[magenta]🌿 {branch}[/]")
        
    table.add_row("Environment", f"[blue]🐍 {_get_env_info()}[/]")
    
    stats = _get_project_stats(cwd)
    if stats:
        table.add_row("Contents", f"[dim]{stats}[/]")
        
    if config and config.get("provider") and config.get("provider") != "none":
        p = config.get("provider").capitalize()
        m = config.get("model") or "default"
        table.add_row("LLM Backend", f"[bold yellow]⚡ {p}[/] [dim]({m})[/]")

    inner = Group(
        Align.center(title),
        Text(""),
        Align.center(table),
    )

    panel = Panel(
        inner,
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 4),
        width=min(console.width, 88) if console.width is not None else None,
    )

    console.print()
    console.print(Align.center(panel))
    console.print()
    
    # Sleek footer
    footer_text = (
        " [dim]Shortcuts: [/][bold cyan]create[/] [dim]/[/] [bold cyan]agent[/] [dim]task ·[/] "
        "[bold cyan]undo[/] [dim]·[/] [bold cyan]history[/] [dim]·[/] [bold cyan]context[/] [dim]·[/] "
        "[bold cyan]help[/] [dim]|[/] [bold cyan]Ctrl+C[/] [dim]|[/] [bold cyan]Ctrl+D[/] [dim]exit[/] "
    )
    footer = Text.from_markup(footer_text)
    
    console.print(Align.center(footer))
    console.print()


def print_help(
    console: Console,
    internal: Iterable[str],
    external: Iterable[str],
) -> None:
    internal_s = ", ".join(f"[bold cyan]{c}[/]" for c in sorted(internal) if c != "quit")
    external_s = ", ".join(f"[bright_blue]{c}[/]" for c in sorted(external))
    
    table = Table(title="[bold]Command Palette[/]", box=box.ROUNDED, border_style="cyan", padding=(0, 2))
    table.add_column("Category", style="dim", no_wrap=True)
    table.add_column("Commands")
    
    table.add_row("Internal", internal_s)
    table.add_row("External", external_s)
    
    console.print()
    console.print(table)
    console.print("[dim]Commands not in this list are rejected.[/]")
    console.print(
        "[dim]Coding agent (same as CLI, stays in shell): [/]"
        "[bold cyan]create[/] [dim]or[/] [bold cyan]agent[/] [dim]then your request;[/] "
        "[bold cyan]undo[/] [dim]reverts the last confirmed Nex git save.[/]\n"
        "[dim]Session: [/][bold cyan]history[/] [dim]shows past turns ·[/] "
        "[bold cyan]context[/] [dim]shows files saved this session (auto-fed to LLM).[/]"
    )
    console.print()


def print_goodbye(console: Console) -> None:
    console.print()
    console.print(Align.center(Text("Session ended. See you later ✨", style="italic cyan")))
    console.print()


def print_error(err: Console, message: str) -> None:
    err.print(f"╭─ [bold red]Error[/]\n╰─❯ [red]{message}[/]")
