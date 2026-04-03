"""CLI entry point — intro, usage, and exit. Coding features are not implemented yet."""

from __future__ import annotations

import argparse

from nex_coding import __version__


def _print_intro(prog: str) -> None:
    lines = [
        "",
        "  Nex Coding",
        "  ──────────",
        "  A terminal-first CLI for coding workflows.",
        "  This install is a scaffold: sessions, editors, and tools are not wired up yet.",
        "",
        "  How to run",
        "  ──────────",
        f"    {prog}",
        "    python -m nex_coding",
        "",
        "  Options",
        "  ───────",
        "    --help     Show all flags and commands.",
        "    --version  Print the installed version.",
        "",
        "  Stopping",
        "  ────────",
        "    When an interactive session exists, use Ctrl+C or the session quit command",
        "    (to be added). Right now the program exits after printing this screen.",
        "",
    ]
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nex-coding",
        description="Terminal-based coding CLI (scaffold only).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args()
    _print_intro(parser.prog)
    return 0
