"""Resolve paths safely under a project root."""

from __future__ import annotations

from pathlib import Path


def resolve_under_root(root: Path, relative: str) -> Path:
    """Return an absolute path for *relative* if it stays under *root*."""
    root = root.resolve()
    raw = relative.strip().replace("\\", "/").lstrip("/")
    if not raw or raw == ".":
        return root
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {relative!r}") from exc
    return candidate
