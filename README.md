# nex-coding-tool

Terminal-first **Nex Coding** CLI, implemented in Python. This repository currently ships a **scaffold**: it prints an intro, usage hints, and exits. Interactive sessions, editors, and coding workflows are not implemented yet.

## Requirements

- Python 3.9 or newer

## Run without installing

From the repository root:

```bash
PYTHONPATH=. python3 -m nex_coding
```

Show help or version:

```bash
PYTHONPATH=. python3 -m nex_coding --help
PYTHONPATH=. python3 -m nex_coding --version
```

## Install and run (recommended)

Using a virtual environment keeps dependencies and the `nex-coding` command isolated:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install .
nex-coding
nex-coding --help
nex-coding --version
```

Deactivate the environment with `deactivate` when you are done.

## Layout

| Path | Role |
|------|------|
| `nex_coding/cli.py` | CLI entry: argument parsing and intro text |
| `nex_coding/__main__.py` | Enables `python -m nex_coding` |
| `pyproject.toml` | Package metadata and `nex-coding` console script |
