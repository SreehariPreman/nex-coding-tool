"""CLI entry point — interactive Nex shell and optional project blurb."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nex_coding import __version__
from nex_coding.shell import run_interactive_shell


def _print_intro(prog: str) -> None:
    lines = [
        "",
        "  Nex Coding",
        "  ──────────",
        "  A terminal-first CLI for coding workflows.",
        "  The default mode is an interactive Nex shell in your chosen folder.",
        "",
        "  How to run",
        "  ──────────",
        f"    {prog}",
        f"    {prog} /path/to/project",
        "    python -m nex_coding",
        "",
        "  Options",
        "  ───────",
        "    --about    Print this blurb and exit (no shell).",
        "    --help     Show all flags.",
        "    --version  Print the installed version.",
        "",
        "  Inside the Nex shell",
        "  ────────────────────",
        "    help         List built-in and pass-through commands.",
        "    exit         Leave the shell (or Ctrl+D).",
        "    Ctrl+C       Interrupts the current line; does not exit.",
        "",
    ]
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nex-coding",
        description="Terminal-based coding CLI with an interactive Nex shell.",
    )
    parser.add_argument(
        "workdir",
        nargs="?",
        default=None,
        help="Directory to use as the initial working directory (default: current directory).",
    )
    parser.add_argument(
        "--about",
        action="store_true",
        help="Print the Nex Coding blurb and exit without starting the shell.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    if args.about:
        _print_intro(parser.prog)
        return 0

    start = Path(args.workdir).expanduser() if args.workdir else None
    if start is not None and not start.exists():
        print(f"nex: path does not exist: {start}", file=sys.stderr)
        return 1

    return run_interactive_shell(start)
