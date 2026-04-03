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

_PROMPT_MARKUP = "[bold bright_green]nex-os[/][dim]:[/][bold green]~[/][bold bright_green]$[/] "


def stdout_console() -> Console:
    return Console(highlight=False, soft_wrap=True)


def stderr_console() -> Console:
    return Console(highlight=False, stderr=True, soft_wrap=True)


def prompt_markup() -> str:
    return _PROMPT_MARKUP


def print_welcome(console: Console, cwd: str) -> None:
    ascii_art = """[bold bright_green]
    _   __  ______  _  __
   / | / / / ____/ | |/ /
  /  |/ / / __/    |   / 
 / /|  / / /___   /   |  
/_/ |_/ /_____/  /_/|_|  
[/]"""
    title = Text.from_markup(ascii_art)

    tagline = Text(
        "INITIALIZING SYSTEM... ACCESS GRANTED",
        style="bold green",
        justify="center",
    )

    path_line = Text()
    path_line.append("MOUNT POINT: ", style="bold green dim")
    path_line.append(cwd, style="bold bright_green")

    inner = Group(
        Align.center(title),
        Text(""),
        Align.center(tagline),
        Text(""),
        Rule(style="green"),
        Text(""),
        path_line,
    )

    panel = Panel(
        inner,
        title="[bold bright_green]NEX_OS_BOOT_SEQ[/]",
        border_style="bold green",
        box=box.SQUARE,
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
                "TYPE `help` FOR SYSTEM COMMANDS  ·  `exit` TO TERMINATE",
                style="bold green dim",
            )
        )
    )
    console.print()


def print_help(
    console: Console,
    internal: Iterable[str],
    external: Iterable[str],
) -> None:
    internal_s = " ".join(f"`{c}`" for c in sorted(internal) if c != "quit")
    external_s = " ".join(f"`{c}`" for c in sorted(external))
    md = f"""## LOADED MODULES (INTERNAL)
{internal_s} — `quit` is an alias for `exit`.

## SYSTEM BINARIES (EXTERNAL)
{external_s}

> **WARNING:** UNREGISTERED COMMANDS WILL BE REJECTED. 
> NO SANDBOX DETECTED. ALL ACTIONS RUN ON BARE METAL.
"""
    console.print(
        Panel(
            Markdown(md),
            title="[bold bright_green]SYSTEM_MANUAL[/]",
            border_style="bold green",
            box=box.SQUARE,
            padding=(1, 2),
        )
    )


def print_goodbye(console: Console) -> None:
    console.print()
    console.print(Align.center(Text("CONNECTION TERMINATED.", style="bold green dim")))
    console.print()


def print_error(err: Console, message: str) -> None:
    err.print(f"[bold red]FATAL_ERROR[/] [red]{message}[/]")
