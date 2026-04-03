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
        "  \033[1;92mNEX_OS v0.1.0\033[0m",
        "  \033[32m═════════════\033[0m",
        "  \033[32m[SYSTEM BOOT]: Terminal-first CLI workspace initialized.\033[0m",
        "  \033[32m[MODE]: Interactive shell access.\033[0m",
        "",
        "  \033[1;92mEXECUTION PROTOCOLS\033[0m",
        "  \033[32m───────────────────\033[0m",
        f"    $ {prog}",
        f"    $ {prog} /path/to/project",
        "    $ python -m nex_coding",
        "",
        "  \033[1;92mFLAGS & PARAMETERS\033[0m",
        "  \033[32m──────────────────\033[0m",
        "    --about    Print system parameters and terminate.",
        "    --help     Show detailed flag registry.",
        "    --version  Output kernel version.",
        "",
        "  \033[1;92mINTERNAL COMMANDS\033[0m",
        "  \033[32m─────────────────\033[0m",
        "    help         Display available binaries.",
        "    exit         Terminate session (or Ctrl+D).",
        "    Ctrl+C       Interrupt execution.",
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
