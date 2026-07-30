"""
Live desk state derived from EOS OSC feedback.

Policies and the UI can read this snapshot instead of reacting to every OSC packet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from eosbot.events import EosEvent

_MODE_RE = re.compile(r"^(LIVE|BLIND)\b", re.IGNORECASE)
_CUE_TOKEN_RE = re.compile(r"^(\d+(?:\.\d+)?/\d+(?:\.\d+)?)")


def command_line_is_commit(event: EosEvent) -> bool:
    """
    True when the command line looks finished (Enter) or is an error.

    Eos marks errors with a second OSC arg of 1. Completed lines usually end with '#'.
    """
    if event.kind not in ("command_line", "user_command_line"):
        return False
    if len(event.args) >= 2:
        try:
            if int(event.args[1]) == 1:
                return True
        except (TypeError, ValueError):
            pass
    text = (event.text or "").rstrip()
    return text.endswith("#")


def _mode_from_cmd(text: str) -> Optional[str]:
    match = _MODE_RE.match(text.strip())
    return match.group(1).upper() if match else None


def _cue_id_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    match = _CUE_TOKEN_RE.match(text.strip())
    return match.group(1) if match else None


@dataclass
class DeskState:
    """Current operator-facing snapshot of the console."""

    show_name: Optional[str] = None
    mode: Optional[str] = None  # LIVE / BLIND
    user: Optional[int] = None

    active_cue: Optional[str] = None
    active_cue_label: Optional[str] = None
    active_progress: Optional[float] = None

    previous_cue: Optional[str] = None
    previous_cue_label: Optional[str] = None

    pending_cue: Optional[str] = None
    pending_cue_label: Optional[str] = None

    last_fire_cue: Optional[str] = None
    last_fire_label: Optional[str] = None

    command_line: Optional[str] = None
    command_line_error: bool = False

    active_chan: Optional[str] = None
    active_wheel: Optional[str] = None

    # Fields that changed on the last apply() call (significant only).
    last_changes: Set[str] = field(default_factory=set)

    def apply(self, event: EosEvent) -> Set[str]:
        """Update state from an event. Returns names of *significant* changes."""
        significant: Set[str] = set()

        if event.kind == "show_name" and event.text is not None:
            if event.text != self.show_name:
                self.show_name = event.text
                significant.add("show_name")

        elif event.kind == "cue_fire":
            if event.cue and event.cue != self.last_fire_cue:
                self.last_fire_cue = event.cue
                significant.add("last_fire_cue")
            label = event.text
            if label != self.last_fire_label:
                self.last_fire_label = label
                significant.add("last_fire_label")

        elif event.kind == "active_cue":
            cue = event.cue or _cue_id_from_text(event.text or "")
            if cue and cue != self.active_cue:
                self.active_cue = cue
                significant.add("active_cue")
            if event.text is not None:
                # Keep latest label/progress text, but only flag when cue identity moved.
                label = event.text
                if label != self.active_cue_label:
                    self.active_cue_label = label
                    if "active_cue" in significant:
                        significant.add("active_cue_label")
            if event.progress is not None:
                self.active_progress = event.progress

        elif event.kind == "cue_progress":
            if event.progress is not None:
                self.active_progress = event.progress

        elif event.kind == "previous_cue":
            cue = event.cue or _cue_id_from_text(event.text or "")
            if cue and cue != self.previous_cue:
                self.previous_cue = cue
                significant.add("previous_cue")
            if event.text is not None and event.text != self.previous_cue_label:
                self.previous_cue_label = event.text
                if "previous_cue" in significant:
                    significant.add("previous_cue_label")

        elif event.kind == "pending_cue":
            cue = event.cue or _cue_id_from_text(event.text or "")
            if cue and cue != self.pending_cue:
                self.pending_cue = cue
                significant.add("pending_cue")
            if event.text is not None and event.text != self.pending_cue_label:
                self.pending_cue_label = event.text
                if "pending_cue" in significant:
                    significant.add("pending_cue_label")

        elif event.kind == "command_line":
            text = event.text or ""
            error = False
            if len(event.args) >= 2:
                try:
                    error = int(event.args[1]) == 1
                except (TypeError, ValueError):
                    error = False
            mode = _mode_from_cmd(text)
            if mode and mode != self.mode:
                self.mode = mode
                significant.add("mode")
            # Always keep latest typing in state.
            self.command_line = text
            self.command_line_error = error
            if command_line_is_commit(event):
                significant.add("command_line")

        elif event.kind == "user_command_line":
            # Other users' cmd lines — ignore for local desk state.
            pass
        elif event.kind == "active_chan":
            text = event.text or ""
            if text != (self.active_chan or ""):
                self.active_chan = text
                # Empty clear is still useful.
                significant.add("active_chan")

        elif event.kind == "active_wheel":
            text = event.text or ""
            if text != (self.active_wheel or ""):
                self.active_wheel = text
                significant.add("active_wheel")

        elif event.kind == "eos_out" and event.address.lower() == "/eos/out/user":
            if event.args:
                try:
                    user = int(event.args[0])
                except (TypeError, ValueError):
                    user = None
                if user is not None and user != self.user:
                    self.user = user
                    significant.add("user")

        self.last_changes = significant
        return significant

    def format_snapshot(self, changed: Optional[Set[str]] = None) -> str:
        """One-line STATE summary; highlight changed fields when provided."""
        changed = changed or set()

        def mark(name: str, value: str) -> str:
            prefix = "*" if name in changed else ""
            return f"{prefix}{name}={value}"

        parts: List[str] = []
        if self.show_name:
            parts.append(mark("show", repr(self.show_name)))
        if self.user is not None:
            parts.append(mark("user", str(self.user)))
        if self.mode:
            parts.append(mark("mode", self.mode))
        if self.active_cue:
            label = f" {self.active_cue_label!r}" if self.active_cue_label else ""
            parts.append(mark("active", f"{self.active_cue}{label}"))
        if self.previous_cue:
            parts.append(mark("prev", self.previous_cue))
        if self.pending_cue:
            parts.append(mark("next", self.pending_cue))
        if self.last_fire_cue and "last_fire_cue" in changed:
            fire = self.last_fire_cue
            if self.last_fire_label:
                fire = f"{fire} {self.last_fire_label!r}"
            parts.append(mark("fire", fire))
        if self.active_chan is not None and (
            "active_chan" in changed or self.active_chan
        ):
            if "active_chan" in changed or self.active_chan:
                parts.append(mark("chan", repr(self.active_chan)))
        if self.active_wheel and "active_wheel" in changed:
            parts.append(mark("wheel", repr(self.active_wheel)))
        if self.command_line is not None and "command_line" in changed:
            err = " ERROR" if self.command_line_error else ""
            parts.append(mark("cmd", repr(self.command_line) + err))
        return "STATE " + " ".join(parts) if parts else "STATE (empty)"
