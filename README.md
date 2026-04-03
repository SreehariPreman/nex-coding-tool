# nex-coding-tool

Terminal-first **Nex Coding** CLI, implemented in Python. The default experience is an **interactive Nex shell**: you get a `nex>` prompt in a chosen folder, with a curated set of common Unix-style commands (plus built-ins like `cd` and `pwd`). Deeper coding workflows can build on top of this later.

## Requirements

- Python 3.9 or newer
- [Rich](https://github.com/Textualize/rich) (installed automatically with `pip install .`)

## Run without installing

From the repository root:

```bash
PYTHONPATH=. python3 -m nex_coding
```

Start in a specific directory:

```bash
PYTHONPATH=. python3 -m nex_coding /path/to/project
```

Show help, version, or the longer project blurb (no shell):

```bash
PYTHONPATH=. python3 -m nex_coding --help
PYTHONPATH=. python3 -m nex_coding --version
PYTHONPATH=. python3 -m nex_coding --about
```

## Install and run (recommended)

Using a virtual environment keeps dependencies and the `nex-coding` command isolated:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install .
nex-coding
nex-coding /path/to/project
nex-coding --help
```

Deactivate the environment with `deactivate` when you are done.

## Nex shell

- **Prompt:** `nex>`
- **Leave:** `exit`, `quit`, or Ctrl+D (end of input).
- **Ctrl+C:** Clears the current input line; does not exit the shell.
- **Built-ins:** `cd`, `pwd`, `help`, `clear`, `exit` / `quit`.
- **Pass-through:** Other supported names are executed from your `PATH` with **no shell** (safer than `sh -c`). If a name is not in the allow-list, Nex refuses it — type `help` inside the shell for the full list.

## Layout

| Path | Role |
|------|------|
| `nex_coding/cli.py` | Argument parsing, `--about`, starts the shell |
| `nex_coding/shell.py` | Interactive loop and command dispatch |
| `nex_coding/ui.py` | Rich layouts: welcome, help, prompts, errors |
| `nex_coding/__main__.py` | Enables `python -m nex_coding` |
| `pyproject.toml` | Package metadata, dependencies, `nex-coding` script |
