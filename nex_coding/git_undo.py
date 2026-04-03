"""Git-backed commit for confirmed saves and single-step undo."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEX_DIR = ".nex"
LAST_SAVE = "last_save.json"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(cwd: Path) -> bool:
    p = _git(cwd, "rev-parse", "--is-inside-work-tree")
    return p.returncode == 0 and p.stdout.strip() == "true"


def current_head(cwd: Path) -> str | None:
    p = _git(cwd, "rev-parse", "HEAD")
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def _state_path(cwd: Path) -> Path:
    return cwd / NEX_DIR / LAST_SAVE


def _load_state(cwd: Path) -> dict[str, Any] | None:
    path = _state_path(cwd)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(cwd: Path, data: dict[str, Any]) -> None:
    d = cwd / NEX_DIR
    d.mkdir(parents=True, exist_ok=True)
    _state_path(cwd).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _clear_state(cwd: Path) -> None:
    p = _state_path(cwd)
    if p.is_file():
        p.unlink()


@dataclass
class CommitResult:
    ok: bool
    message: str
    commit_sha: str | None = None


def commit_paths(cwd: Path, relative_paths: list[str], summary: str) -> CommitResult:
    """Stage *relative_paths*, commit if there is a diff, record undo metadata."""
    if not is_git_repo(cwd):
        return CommitResult(False, "Not a git repository. Run `git init` to enable undo.")

    for rel in relative_paths:
        p = _git(cwd, "add", "--", rel)
        if p.returncode != 0:
            return CommitResult(False, f"git add failed: {p.stderr.strip() or p.stdout.strip()}")

    st = _git(cwd, "diff", "--cached", "--quiet")
    if st.returncode == 0:
        return CommitResult(
            True,
            "Files saved. No new git commit (staged changes match HEAD).",
            commit_sha=current_head(cwd),
        )

    msg = f"nex: {summary}"[:72]
    c = _git(cwd, "commit", "-m", msg)
    if c.returncode != 0:
        return CommitResult(False, f"git commit failed: {c.stderr.strip() or c.stdout.strip()}")

    sha = current_head(cwd)
    if sha:
        _write_state(
            cwd,
            {
                "commit_sha": sha,
                "paths": relative_paths,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    return CommitResult(True, f"Committed {len(relative_paths)} file(s).", commit_sha=sha)


@dataclass
class UndoResult:
    ok: bool
    message: str


def undo_last_save(cwd: Path) -> UndoResult:
    """Reset HEAD to the parent of the last Nex commit if HEAD still matches."""
    if not is_git_repo(cwd):
        return UndoResult(False, "Not a git repository.")

    state = _load_state(cwd)
    if not state or not state.get("commit_sha"):
        return UndoResult(False, "No recorded Nex save to undo.")

    head = current_head(cwd)
    if not head:
        return UndoResult(False, "Could not read HEAD.")

    if head != state["commit_sha"]:
        return UndoResult(
            False,
            "Cannot undo: repository HEAD does not match the last Nex save "
            "(history changed). Use git manually if needed.",
        )

    dirty = _git(cwd, "status", "--porcelain")
    if dirty.stdout.strip():
        return UndoResult(
            False,
            "Cannot undo: working tree is not clean. Commit or stash changes first.",
        )

    r = _git(cwd, "reset", "--hard", "HEAD~1")
    if r.returncode != 0:
        return UndoResult(False, f"git reset failed: {r.stderr.strip() or r.stdout.strip()}")

    _clear_state(cwd)
    return UndoResult(True, "Reverted the last Nex commit (hard reset to parent).")
