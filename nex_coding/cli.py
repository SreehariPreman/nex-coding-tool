"""CLI entry point — starts the interactive Nex shell (coding agent runs only inside it)."""

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
        "  \033[1;92mCODING AGENT\033[0m",
        "  \033[32m────────────\033[0m",
        "    Start the shell, then:  create …  |  agent …  |  undo",
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


def _shell_only_message(prog: str) -> None:
    print(
        "nex: the coding agent and undo run only inside the interactive shell.",
        file=sys.stderr,
    )
    print(
        f"  Start: {prog}    then:  create …  or  agent …  ·  undo",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="nex-coding",
        description="Terminal-based Nex CLI: opens the interactive shell. "
        "Use create / agent / undo inside the shell for LLM-backed edits.",
    )
    parser.add_argument(
        "workdir",
        nargs="?",
        default=None,
        metavar="WORKDIR",
        help="Directory to start the shell in (default: current directory).",
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

    if args.workdir is None:
        start = Path.cwd().resolve()
    else:
        raw = Path(args.workdir).expanduser()
        if raw.is_dir():
            start = raw.resolve()
        elif raw.exists():
            print(f"nex: not a directory: {raw}", file=sys.stderr)
            return 1
        else:
            # Looks like a mistaken task string (CLI no longer accepts tasks here).
            _shell_only_message(parser.prog)
            return 2

    if not start.is_dir():
        print(f"nex: path does not exist or is not a directory: {start}", file=sys.stderr)
        return 1

    return run_interactive_shell(start)


if __name__ == "__main__":
    raise SystemExit(main())
