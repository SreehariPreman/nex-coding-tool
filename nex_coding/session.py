"""Per-shell-session conversation context for the Nex coding agent.

Keeps:
  - history: list of (role, text) pairs across all agent turns
  - saved_files: dict of {relative_path: content} for every file confirmed to disk
  - turn_log: light metadata about each turn (request, files staged/saved)

Nothing here is persisted to disk; it lives only for the duration of one
``nex`` shell session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass
class Turn:
    """One user→assistant exchange."""
    request: str
    summary: str
    staged: list[str] = field(default_factory=list)   # paths staged
    saved: list[str] = field(default_factory=list)    # paths confirmed to disk
    discarded: bool = False


@dataclass
class SessionContext:
    """Mutable conversation state for one nex shell session."""

    # Raw (role, text) message history — fed to the LLM as prior context
    history: list[tuple[Role, str]] = field(default_factory=list)

    # Snapshot of every file that has been confirmed-saved this session.
    # Maps relative path → content at time of save.
    saved_files: dict[str, str] = field(default_factory=dict)

    # Lightweight log of every turn (for display / debug)
    turns: list[Turn] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Mutation helpers
    # ------------------------------------------------------------------ #

    def record_user(self, text: str) -> None:
        self.history.append(("user", text))

    def record_assistant(self, text: str) -> None:
        if text.strip():
            self.history.append(("assistant", text))

    def record_turn(
        self,
        request: str,
        summary: str,
        staged: list[dict[str, str]],
        saved: list[str],
        discarded: bool = False,
    ) -> None:
        self.turns.append(
            Turn(
                request=request,
                summary=summary,
                staged=[s["path"] for s in staged],
                saved=saved,
                discarded=discarded,
            )
        )
        # Update the saved-files snapshot
        for item in staged:
            if item["path"] in saved:
                self.saved_files[item["path"]] = item.get("content", "")

    # ------------------------------------------------------------------ #
    # Context builders for the LLM
    # ------------------------------------------------------------------ #

    def has_context(self) -> bool:
        return bool(self.history) or bool(self.saved_files)

    def prior_messages_for_agent(self) -> list[tuple[Role, str]]:
        """Return history slice to prepend as prior conversation turns.

        We keep the last N turns to avoid blowing up the context window.
        Each turn is summarised to save tokens: full content is NOT resent.
        """
        # Return up to the last 10 (role, text) pairs
        return self.history[-10:]

    def saved_files_summary(self) -> str:
        """Compact description of every file saved this session."""
        if not self.saved_files:
            return ""
        lines = ["Files already saved to disk in this session:"]
        for path, content in sorted(self.saved_files.items()):
            lines_count = content.count("\n") + 1
            lines.append(f"  • {path}  ({lines_count} lines)")
        return "\n".join(lines)

    def context_banner(self) -> str:
        """Multi-line banner injected at the top of the user's next request."""
        parts: list[str] = []
        if self.saved_files:
            parts.append(self.saved_files_summary())
        if parts:
            return (
                "=== Session Context ===\n"
                + "\n".join(parts)
                + "\n======================\n\n"
            )
        return ""

    # ------------------------------------------------------------------ #
    # Display helpers
    # ------------------------------------------------------------------ #

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def last_saved_paths(self) -> list[str]:
        """Return paths saved in the most recent turn, or empty list."""
        for turn in reversed(self.turns):
            if turn.saved:
                return turn.saved
        return []
