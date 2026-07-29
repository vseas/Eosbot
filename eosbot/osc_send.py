"""
Outbound OSC helpers for ETC EOS.

Seeded from LogWork Show_Target_Manager (UDP send + /eos/newcmd path builders).
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional


def pad_single_digit_for_eos(number_str: str) -> str:
    """Spreadsheet-style values 0–9 are sent with a leading zero (4 → 04)."""
    if len(number_str) == 1 and number_str.isdigit():
        return f"0{number_str}"
    return number_str


def normalize_integer_string(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return ""
    return pad_single_digit_for_eos(str(int(float(text))))


def make_udp_sender(ip: str, port: int) -> Callable[[str, List[Any]], None]:
    from pythonosc import udp_client

    client = udp_client.SimpleUDPClient(ip, port)

    def send(address: str, args: Optional[List[Any]] = None) -> None:
        client.send_message(address, args or [])

    return send


class EosSender:
    """Thin wrapper around UDP OSC send with optional dry-run logging."""

    def __init__(
        self,
        ip: str,
        port: int = 8000,
        *,
        dry_run: bool = False,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self.ip = ip
        self.port = port
        self.dry_run = dry_run
        self.log_fn = log_fn or print
        self._send = make_udp_sender(ip, port)

    def send(self, address: str, args: Optional[List[Any]] = None) -> None:
        args = args or []
        if self.dry_run:
            self.log_fn(f"DRY RUN: {address} {args}")
            return
        self._send(address, args)
        self.log_fn(f"Sent: {address} {args}")

    def ping(self) -> None:
        self.send("/eos/ping", ["eosbot"])

    def subscribe(self, enable: bool = True) -> None:
        """Ask EOS to send OSC feedback to this client."""
        self.send("/eos/subscribe", [1 if enable else 0])

    def newcmd(self, path: str) -> None:
        """Send a literal /eos/newcmd/... path (path may already include prefix)."""
        address = path if path.startswith("/") else f"/eos/newcmd/{path}"
        self.send(address, [])

    def key(self, key_name: str) -> None:
        self.send(f"/eos/key/{key_name}", [])


def build_channel_full_command(channel: str, cue_only: bool = False) -> str:
    ch = normalize_integer_string(channel)
    if cue_only:
        return f"/eos/newcmd/{ch}/Full/CueOnly/Enter"
    return f"/eos/newcmd/{ch}/Full/Enter"


def build_clear_command_line_command() -> str:
    return "/eos/key/Clear_Cmd"


def build_go_command() -> str:
    return "/eos/key/Go_0"


def build_cue_fire_command(cue: str) -> str:
    return f"/eos/newcmd/Cue/{normalize_integer_string(cue)}/Go/Enter"
