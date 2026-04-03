"""Rich-powered terminal presentation for the Nex shell."""

from __future__ import annotations

import sys
from typing import Iterable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

_PROMPT_MARKUP = "[bold bright_cyan]nex[/][dim] › [/]"


def stdout_console() -> Console:
    return Console(highlight=False, soft_wrap=True)


def stderr_console() -> Console:
    return Console(highlight=False, stderr=True, soft_wrap=True)


def prompt_markup() -> str:
    return _PROMPT_MARKUP


def print_welcome(console: Console, cwd: str) -> None:
    title = Text()
    title.append("N", style="bold bright_magenta")
    title.append("e", style="bold magenta")
    title.append("x", style="bold bright_cyan")
    title.append(" ", style="")
    title.append("coding shell", style="italic dim")

    tagline = Text(
        "Terminal-first workspace · type commands like in your OS shell",
        style="dim",
        justify="center",
    )

    path_line = Text()
    path_line.append("Working directory\n", style="dim")
    path_line.append(cwd, style="bold green")

    inner = Group(
        Align.center(title),
        Text(""),
        Align.center(tagline),
        Text(""),
        Rule(style="dim"),
        Text(""),
        path_line,
    )

    panel = Panel(
        inner,
        title="[dim]welcome[/]",
        border_style="bright_blue",
        box=box.ROUNDED,
        padding=(1, 2),
        width=min(console.width, 88)
        if console.width is not None
        else None,
    )

    console.print()
    console.print(Align.center(panel))
    console.print()
    console.print(
        Align.center(
            Text(
                "help  ·  exit or quit  ·  Ctrl+D to leave  ·  Ctrl+C cancels the line",
                style="dim",
            )
        )
    )
    console.print()


def print_help(
    console: Console,
    internal: Iterable[str],
    external: Iterable[str],
) -> None:
    internal_s = ", ".join(f"`{c}`" for c in sorted(internal) if c != "quit")
    external_s = ", ".join(f"`{c}`" for c in sorted(external))
    md = f"""## Built-in commands
{internal_s} — `quit` is an alias for `exit`.

## Pass-through (from your PATH)
{external_s}

Commands not in this list are **rejected**. There is no extra sandbox: they run as **your user** with your environment.
"""
    console.print(
        Panel(
            Markdown(md),
            title="[bold bright_cyan]Nex[/] [dim]help[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def print_goodbye(console: Console) -> None:
    console.print()
    console.print(Align.center(Text("See you next time.", style="dim italic")))
    console.print()


def print_error(err: Console, message: str) -> None:
    err.print(f"[bold red]nex[/] [red]{message}[/]")
