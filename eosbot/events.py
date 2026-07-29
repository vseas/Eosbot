"""
Normalize raw EOS OSC paths into typed events for policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


@dataclass
class EosEvent:
    """A normalized event derived from an incoming OSC message."""

    kind: str
    address: str
    args: Sequence[Any] = field(default_factory=tuple)
    cue: Optional[str] = None
    text: Optional[str] = None
    raw_summary: str = ""


def summarize_osc(address: str, args: Sequence[Any]) -> str:
    if args:
        return f"{address} {list(args)}"
    return address


def parse_osc_event(address: str, args: Sequence[Any]) -> EosEvent:
    """
    Map known /eos/out/... patterns into event kinds.

    Unknown paths become kind='raw' so policies can still react later.
    """
    summary = summarize_osc(address, args)
    lower = address.lower()
    args_list = list(args)

    # Common EOS feedback families (exact paths vary by software version).
    if "/eos/out/event/cue" in lower or lower.endswith("/cue/fire") or "/cue/active" in lower:
        cue = str(args_list[0]) if args_list else _cue_from_path(address)
        return EosEvent(kind="cue", address=address, args=args_list, cue=cue, raw_summary=summary)

    if "/eos/out/cmd" in lower or "/eos/out/user" in lower and "cmd" in lower:
        text = str(args_list[0]) if args_list else ""
        return EosEvent(kind="command_line", address=address, args=args_list, text=text, raw_summary=summary)

    if "/eos/out/ping" in lower or address.endswith("/ping"):
        return EosEvent(kind="ping", address=address, args=args_list, raw_summary=summary)

    if "/eos/out/" in lower:
        return EosEvent(kind="eos_out", address=address, args=args_list, raw_summary=summary)

    return EosEvent(kind="raw", address=address, args=args_list, raw_summary=summary)


def _cue_from_path(address: str) -> Optional[str]:
    parts = [p for p in address.split("/") if p]
    for i, part in enumerate(parts):
        if part.lower() == "cue" and i + 1 < len(parts):
            return parts[i + 1]
    return None
