"""
Starter policies for Eosbot.

Each policy returns zero or more Option objects when an event matches.
You will add more policies as you invent desk workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence

from eosbot.events import EosEvent
from eosbot.osc_send import (
    build_clear_command_line_command,
    build_cue_fire_command,
    build_go_command,
)


@dataclass
class Option:
    """A choice the operator can take in response to an event."""

    key: str
    label: str
    # Absolute OSC address to send when chosen (e.g. /eos/newcmd/... or /eos/key/...)
    address: str
    args: Sequence[object] | None = None


PolicyFn = Callable[[EosEvent], List[Option]]


def policy_on_any_cue(event: EosEvent) -> List[Option]:
    """When a cue fires or active cue changes, offer a few hard-coded next steps."""
    if event.kind not in ("cue_fire", "active_cue"):
        return []

    cue = event.cue or "?"
    return [
        Option(
            key="1",
            label=f"Go (main playback) — after cue {cue}",
            address=build_go_command(),
        ),
        Option(
            key="2",
            label="Clear command line",
            address=build_clear_command_line_command(),
        ),
        Option(
            key="3",
            label="Fire cue 1 (example)",
            address=build_cue_fire_command("1"),
        ),
        Option(
            key="s",
            label="Skip / ignore",
            address="",  # sentinel: no send
        ),
    ]


def policy_on_ping(event: EosEvent) -> List[Option]:
    if event.kind != "ping":
        return []
    return [
        Option(
            key="1",
            label="Reply with ping",
            address="/eos/ping",
            args=["eosbot-ack"],
        ),
        Option(
            key="s",
            label="Skip / ignore",
            address="",
        ),
    ]


# Policies are evaluated in order; first non-empty result wins for the interactive prompt.
ACTIVE_POLICIES: List[PolicyFn] = [
    policy_on_ping,
    policy_on_any_cue,
]


def options_for_event(event: EosEvent) -> List[Option]:
    for policy in ACTIVE_POLICIES:
        options = policy(event)
        if options:
            return options
    return []
