"""File-snapshot based undo for Nex saves.

No git commits are made. Before writing files to disk, Nex snapshots the
previous content (or absence) of each path into .nex/last_save.json.
'undo' restores those snapshots by writing the old content back (or deleting
newly created files).

Git is left entirely to the user.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEX_DIR = ".nex"
LAST_SAVE = "last_save.json"


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
class SnapshotResult:
    ok: bool
    message: str


def record_pre_write_snapshot(
    cwd: Path,
    paths: list[str],
    summary: str,
) -> SnapshotResult:
    """Snapshot the current on-disk content of *paths* before Nex overwrites them.

    For each path:
      - If the file exists  → store its content so undo can restore it.
      - If the file is new  → store None so undo knows to delete it.

    Call this BEFORE writing files to disk.
    """
    snapshots: list[dict[str, Any]] = []
    for rel in paths:
        abs_path = (cwd / rel).resolve()
        if abs_path.is_file():
            try:
                old_content = abs_path.read_text(encoding="utf-8")
            except Exception:
                old_content = None
            snapshots.append({"path": rel, "existed": True, "content": old_content})
        else:
            snapshots.append({"path": rel, "existed": False, "content": None})

    _write_state(
        cwd,
        {
            "summary": summary,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "snapshots": snapshots,
        },
    )
    return SnapshotResult(ok=True, message=f"Snapshot recorded for {len(paths)} file(s).")


@dataclass
class UndoResult:
    ok: bool
    message: str


def undo_last_save(cwd: Path) -> UndoResult:
    """Restore the on-disk state from the last Nex pre-write snapshot."""
    state = _load_state(cwd)
    if not state or not state.get("snapshots"):
        return UndoResult(False, "No recorded Nex save to undo.")

    snapshots: list[dict[str, Any]] = state["snapshots"]
    restored: list[str] = []
    deleted: list[str] = []
    errors: list[str] = []

    for snap in snapshots:
        rel = snap["path"]
        abs_path = (cwd / rel).resolve()
        existed: bool = snap.get("existed", False)
        content: str | None = snap.get("content")

        if existed and content is not None:
            # Restore the old content
            try:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                restored.append(rel)
            except OSError as exc:
                errors.append(f"{rel}: {exc}")
        elif not existed:
            # File was newly created by Nex — delete it
            try:
                if abs_path.is_file():
                    abs_path.unlink()
                    deleted.append(rel)
                    # Remove empty parent dirs
                    try:
                        abs_path.parent.rmdir()
                    except OSError:
                        pass
            except OSError as exc:
                errors.append(f"{rel}: {exc}")

    if errors:
        return UndoResult(False, f"Undo partially failed: {'; '.join(errors)}")

    _clear_state(cwd)

    parts: list[str] = []
    if restored:
        parts.append(f"restored {len(restored)} file(s)")
    if deleted:
        parts.append(f"deleted {len(deleted)} new file(s)")
    msg = "Undo complete — " + ", ".join(parts) + "." if parts else "Nothing to undo."
    return UndoResult(True, msg)
