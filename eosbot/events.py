"""
Normalize raw EOS OSC paths into typed events for policies.

Interest levels (from live capture analysis):
  high   — cue fire, active/pending/previous cue identity+text, selection, notify
  normal — command line, wheels, show name, ping, event state
  low    — fade progress ticks, empty geometry packs, locked flags
  noise  — softkeys (very chatty; demoted by default)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

# softkey / cue_progress dominate live traffic; keep them parseable but quiet.
DEFAULT_DEMOTE_KINDS = frozenset({"softkey", "cue_progress", "empty_geometry"})


@dataclass
class EosEvent:
    """A normalized event derived from an incoming OSC message."""

    kind: str
    address: str
    args: Sequence[Any] = field(default_factory=tuple)
    cue: Optional[str] = None
    cue_list: Optional[str] = None
    text: Optional[str] = None
    progress: Optional[float] = None
    interest: str = "normal"  # high | normal | low | noise
    raw_summary: str = ""


def summarize_osc(address: str, args: Sequence[Any]) -> str:
    if args:
        return f"{address} {list(args)}"
    return address


def parse_osc_event(address: str, args: Sequence[Any]) -> EosEvent:
    """Map known /eos/out/... patterns into event kinds + interest."""
    summary = summarize_osc(address, args)
    lower = address.lower()
    args_list = list(args)
    parts = [p for p in address.split("/") if p]

    # --- Noise / demoted ---
    if "/eos/out/softkey/" in lower:
        return EosEvent(
            kind="softkey",
            address=address,
            args=args_list,
            text=str(args_list[0]) if args_list else "",
            interest="noise",
            raw_summary=summary,
        )

    if lower in ("/eos/out/color/hs", "/eos/out/pantilt", "/eos/out/xyz") and not args_list:
        return EosEvent(
            kind="empty_geometry",
            address=address,
            args=args_list,
            interest="noise",
            raw_summary=summary,
        )

    # --- Cue fire ---
    if "/eos/out/event/cue/" in lower and lower.endswith("/fire"):
        list_n, cue_n = _list_cue_from_event_fire(parts)
        cue = f"{list_n}/{cue_n}" if list_n and cue_n else _cue_from_path(address)
        return EosEvent(
            kind="cue_fire",
            address=address,
            args=args_list,
            cue=cue,
            cue_list=list_n,
            text=str(args_list[0]) if args_list else None,
            interest="high",
            raw_summary=summary,
        )

    # --- Active / previous / pending cue ---
    if "/eos/out/active/cue/text" in lower:
        text = str(args_list[0]) if args_list else ""
        cue = _cue_from_text(text)
        return EosEvent(
            kind="active_cue",
            address=address,
            args=args_list,
            cue=cue,
            text=text,
            interest="high",
            raw_summary=summary,
        )

    if "/eos/out/previous/cue/text" in lower:
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="previous_cue",
            address=address,
            args=args_list,
            cue=_cue_from_text(text),
            text=text,
            interest="high",
            raw_summary=summary,
        )

    if "/eos/out/pending/cue/text" in lower:
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="pending_cue",
            address=address,
            args=args_list,
            cue=_cue_from_text(text),
            text=text,
            interest="high",
            raw_summary=summary,
        )

    # /eos/out/active/cue/1/135  (identity) vs /eos/out/active/cue [0.5] (progress)
    if "/eos/out/active/cue/" in lower and "/text" not in lower:
        list_n, cue_n = _list_cue_from_active_path(parts)
        progress = _as_float(args_list[0]) if args_list else None
        return EosEvent(
            kind="active_cue",
            address=address,
            args=args_list,
            cue=f"{list_n}/{cue_n}" if list_n and cue_n else None,
            cue_list=list_n,
            progress=progress,
            interest="high",
            raw_summary=summary,
        )

    if lower == "/eos/out/active/cue":
        progress = _as_float(args_list[0]) if args_list else None
        return EosEvent(
            kind="cue_progress",
            address=address,
            args=args_list,
            progress=progress,
            interest="low",
            raw_summary=summary,
        )

    if "/eos/out/previous/cue/" in lower and "/text" not in lower:
        list_n, cue_n = _list_cue_from_active_path(parts)
        return EosEvent(
            kind="previous_cue",
            address=address,
            args=args_list,
            cue=f"{list_n}/{cue_n}" if list_n and cue_n else None,
            cue_list=list_n,
            interest="high",
            raw_summary=summary,
        )

    if "/eos/out/pending/cue/" in lower and "/text" not in lower:
        list_n, cue_n = _list_cue_from_active_path(parts)
        return EosEvent(
            kind="pending_cue",
            address=address,
            args=args_list,
            cue=f"{list_n}/{cue_n}" if list_n and cue_n else None,
            cue_list=list_n,
            interest="high",
            raw_summary=summary,
        )

    # --- Selection / wheels ---
    if lower == "/eos/out/active/chan":
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="active_chan",
            address=address,
            args=args_list,
            text=text,
            interest="high" if text.strip() else "low",
            raw_summary=summary,
        )

    if "/eos/out/active/wheel/" in lower:
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="active_wheel",
            address=address,
            args=args_list,
            text=text,
            interest="normal",
            raw_summary=summary,
        )

    # --- Command line (prefer /eos/out/cmd; per-user paths are duplicates) ---
    if lower == "/eos/out/cmd":
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="command_line",
            address=address,
            args=args_list,
            text=text,
            interest="normal",
            raw_summary=summary,
        )

    if "/eos/out/user/" in lower and lower.endswith("/cmd"):
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="user_command_line",
            address=address,
            args=args_list,
            text=text,
            interest="low",  # duplicate of /eos/out/cmd for local user
            raw_summary=summary,
        )

    # --- Notify / show / ping / misc ---
    if "/eos/out/notify/" in lower:
        return EosEvent(
            kind="notify",
            address=address,
            args=args_list,
            interest="high",
            raw_summary=summary,
        )

    if lower == "/eos/out/show/name":
        text = str(args_list[0]) if args_list else ""
        return EosEvent(
            kind="show_name",
            address=address,
            args=args_list,
            text=text,
            interest="high",
            raw_summary=summary,
        )

    if "/eos/out/ping" in lower or address.endswith("/ping"):
        return EosEvent(
            kind="ping",
            address=address,
            args=args_list,
            interest="normal",
            raw_summary=summary,
        )

    if "/eos/out/event/" in lower:
        return EosEvent(
            kind="eos_event",
            address=address,
            args=args_list,
            interest="normal",
            raw_summary=summary,
        )

    if "/eos/out/" in lower:
        return EosEvent(
            kind="eos_out",
            address=address,
            args=args_list,
            interest="normal",
            raw_summary=summary,
        )

    return EosEvent(
        kind="raw",
        address=address,
        args=args_list,
        interest="normal",
        raw_summary=summary,
    )


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cue_from_text(text: str) -> Optional[str]:
    """Pull '1/135' from strings like '1/135 Restore Scenelts 15.0 100%'."""
    if not text:
        return None
    token = text.strip().split()[0]
    if "/" in token:
        return token
    return token or None


def _cue_from_path(address: str) -> Optional[str]:
    parts = [p for p in address.split("/") if p]
    for i, part in enumerate(parts):
        if part.lower() == "cue" and i + 1 < len(parts):
            # event/cue/1/135/fire → list then cue
            if i + 2 < len(parts) and parts[i + 2].lower() != "fire":
                return f"{parts[i + 1]}/{parts[i + 2]}"
            return parts[i + 1]
    return None


def _list_cue_from_active_path(parts: Sequence[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse .../active|previous|pending/cue/<list>/<cue>."""
    for i, part in enumerate(parts):
        if part.lower() == "cue" and i + 2 < len(parts):
            return parts[i + 1], parts[i + 2]
    return None, None


def _list_cue_from_event_fire(parts: Sequence[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse .../event/cue/<list>/<cue>/fire."""
    for i, part in enumerate(parts):
        if part.lower() == "cue" and i + 2 < len(parts):
            return parts[i + 1], parts[i + 2]
    return None, None
