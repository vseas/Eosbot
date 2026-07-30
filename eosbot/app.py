#!/usr/bin/env python3
"""
Eosbot main loop — subscribe to EOS feedback and offer operator options.

CVS 2026
2026-07-29

Vertical slice:
  1. Connect + ping
  2. Subscribe to feedback
  3. Maintain desk state / log useful changes
  4. Map events
  5. Present hard-coded options → send chosen command
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import time
from typing import Any, Dict, List, Optional, Protocol, Sequence

from eosbot.events import DEFAULT_DEMOTE_KINDS, EosEvent, parse_osc_event
from eosbot.osc_recv import EosReceiver
from eosbot.osc_send import EosSender
from eosbot.osc_tcp import EosTcpSession
from eosbot.policies.starter import Option, options_for_event
from eosbot.state import DeskState, command_line_is_commit


class _Transport(Protocol):
    def send(self, address: str, args: Optional[List[Any]] = None) -> None: ...
    def ping(self) -> None: ...
    def subscribe(self, enable: bool = True) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


def load_config(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def default_config_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


class _UdpTransport:
    """UDP: Eosbot transmits to eos_port, receives on listen_port."""

    def __init__(
        self,
        *,
        eos_ip: str,
        eos_port: int,
        listen_ip: str,
        listen_port: int,
        dry_run: bool,
        on_osc: Any,
        log_fn: Any,
    ):
        self.sender = EosSender(ip=eos_ip, port=eos_port, dry_run=dry_run, log_fn=log_fn)
        self.receiver = EosReceiver(
            listen_ip=listen_ip,
            listen_port=listen_port,
            handler=on_osc,
            log_fn=log_fn,
        )
        self.ip = eos_ip
        self.port = eos_port
        self.listen_port = listen_port

    def send(self, address: str, args: Optional[List[Any]] = None) -> None:
        self.sender.send(address, args)

    def ping(self) -> None:
        self.sender.ping()

    def subscribe(self, enable: bool = True) -> None:
        self.sender.subscribe(enable)

    def start(self) -> None:
        self.receiver.start()
        time.sleep(0.2)

    def stop(self) -> None:
        self.receiver.stop()


class EosbotApp:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        conn = config.get("connection", {})
        behavior = config.get("behavior", {})

        self.dry_run = bool(behavior.get("dry_run", False))
        self.log_raw = bool(behavior.get("log_raw_osc", False))
        self.interactive = bool(behavior.get("interactive_options", True))
        self.transport_name = str(conn.get("transport", "tcp")).lower()
        # "state" (default) prints STATE lines; "events" prints Event lines too.
        self.log_style = str(behavior.get("log_style", "state")).lower()
        # "commits" quiets per-keystroke cmd; "all" logs every command_line packet.
        self.command_line_log = str(behavior.get("command_line_log", "commits")).lower()

        demote = behavior.get("demote_kinds")
        if demote is None:
            self.demote_kinds = set(DEFAULT_DEMOTE_KINDS)
        else:
            self.demote_kinds = set(demote)
        self.min_event_interest = str(behavior.get("min_event_interest", "normal"))

        self.state = DeskState()
        self._events: "queue.Queue[EosEvent]" = queue.Queue()
        self._suppressed = 0

        if self.transport_name == "udp":
            self.link: _Transport = _UdpTransport(
                eos_ip=conn.get("eos_ip", "127.0.0.1"),
                eos_port=int(conn.get("eos_port", 8000)),
                listen_ip=conn.get("listen_ip", "0.0.0.0"),
                listen_port=int(conn.get("listen_port", 8001)),
                dry_run=self.dry_run,
                on_osc=self._on_osc,
                log_fn=self.log,
            )
            self.target_desc = (
                f"UDP {conn.get('eos_ip')}:{conn.get('eos_port', 8000)} "
                f"(listen {conn.get('listen_port', 8001)})"
            )
        else:
            self.link = EosTcpSession(
                ip=conn.get("eos_ip", "127.0.0.1"),
                port=int(conn.get("tcp_port", 3032)),
                mode=str(conn.get("tcp_mode", "1.0")),
                handler=self._on_osc,
                log_fn=self.log,
                dry_run=self.dry_run,
            )
            self.target_desc = (
                f"TCP {conn.get('eos_ip')}:{conn.get('tcp_port', 3032)} "
                f"(OSC {conn.get('tcp_mode', '1.0')})"
            )

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _interest_rank(self, interest: str) -> int:
        return {"noise": 0, "low": 1, "normal": 2, "high": 3}.get(interest, 2)

    def _should_quiet_packet(self, event: EosEvent) -> bool:
        if event.kind in self.demote_kinds or event.interest == "noise":
            return True
        if self._interest_rank(event.interest) < self._interest_rank(self.min_event_interest):
            return True
        if (
            event.kind in ("command_line", "user_command_line")
            and self.command_line_log == "commits"
            and not command_line_is_commit(event)
        ):
            return True
        return False

    def _on_osc(self, address: str, args: Sequence[Any]) -> None:
        event = parse_osc_event(address, args)
        if self._should_quiet_packet(event):
            self._suppressed += 1
        elif self.log_raw:
            self.log(f"OSC IN: {address} {list(args)}")
        self._events.put(event)

    def connect(self) -> None:
        """Open transport, ping, and subscribe. Raises OSError on failure."""
        self.link.start()
        self.link.ping()
        if self.config.get("subscribe", {}).get("enabled", True):
            self.link.subscribe(True)

    def disconnect(self) -> None:
        self.link.stop()

    def start(self) -> None:
        self.log("Eosbot 0.1.0 — CVS 2026")
        self.log(f"Target EOS: {self.target_desc}")
        self.log(
            f"Logging: style={self.log_style}, command_line={self.command_line_log}"
        )
        if self.dry_run:
            self.log("Mode: dry run (commands will not be sent)")

        try:
            self.connect()
        except OSError as exc:
            self.log(f"Connection failed: {exc}")
            if self.transport_name == "tcp":
                self.log(
                    "Tip: confirm Eos OSC RX/TX are on, TCP port 3032 is open, "
                    "and tcp_mode matches the desk (1.0 packet-length vs 1.1 SLIP)."
                )
                self.log('Or set connection.transport to "udp" (TX 8000 / RX 8001).')
            raise SystemExit(1) from exc

        self.log("Subscribe sent — building desk state from feedback")
        if self.demote_kinds:
            self.log(f"Demoted kinds: {', '.join(sorted(self.demote_kinds))}")
        self.log("Waiting for OSC. Press Ctrl+C to quit.")

        try:
            while True:
                try:
                    event = self._events.get(timeout=0.25)
                except queue.Empty:
                    continue
                self._handle_event(event)
        except KeyboardInterrupt:
            self.log(f"\nShutting down… (suppressed {self._suppressed} quiet messages)")
            self.log(self.state.format_snapshot())
        finally:
            self.disconnect()

    def drain_events(self, max_n: int = 200) -> List[tuple]:
        """
        Non-blocking: apply queued OSC events into desk state.

        Returns list of (event, changed_fields) for UI updates.
        """
        results: List[tuple] = []
        while len(results) < max_n:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            changed = self._apply_event(event)
            results.append((event, changed))
        return results

    def _apply_event(self, event: EosEvent):
        """Fold one event into desk state; optional console logging. Returns changed set."""
        changed = self.state.apply(event)

        if changed and self.log_style in ("state", "both"):
            line = self.state.format_snapshot(changed)
            if line != "STATE (empty)":
                self.log(line)

        quiet = self._should_quiet_packet(event)
        if (
            not quiet
            and self.log_style in ("events", "both")
            and event.kind not in self.demote_kinds
            and event.interest != "noise"
            and self._interest_rank(event.interest)
            >= self._interest_rank(self.min_event_interest)
        ):
            bits = [f"kind={event.kind}", f"interest={event.interest}"]
            if event.cue is not None:
                bits.append(f"cue={event.cue!r}")
            if event.text:
                bits.append(f"text={event.text!r}")
            elif event.progress is not None:
                bits.append(f"progress={event.progress:.2f}")
            self.log("Event: " + " ".join(bits))
        return changed

    def _handle_event(self, event: EosEvent) -> None:
        changed = self._apply_event(event)

        if not self.interactive:
            return
        if event.kind == "cue_fire" or "command_line" in changed or "active_cue" in changed:
            options = options_for_event(event)
            if options:
                self._prompt_options(options)

    def _prompt_options(self, options: List[Option]) -> None:
        self.log("--- Options ---")
        for opt in options:
            self.log(f"  [{opt.key}] {opt.label}")
        try:
            choice = input("Choose: ").strip().lower()
        except EOFError:
            return

        for opt in options:
            if opt.key.lower() == choice:
                if not opt.address:
                    self.log("Skipped.")
                    return
                self.link.send(opt.address, list(opt.args or []))
                return
        self.log(f"Unknown choice: {choice!r}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Eosbot — EOS OSC companion")
    parser.add_argument(
        "--config",
        default=default_config_path(),
        help="Path to config.json",
    )
    parser.add_argument("--ip", help="Override EOS IP")
    parser.add_argument(
        "--transport",
        choices=("tcp", "udp"),
        help="Override transport (tcp=3032 bidirectional, udp=TX/RX ports)",
    )
    parser.add_argument("--port", type=int, help="Override EOS OSC port (UDP TX or TCP port)")
    parser.add_argument("--listen-port", type=int, help="Override local UDP listen port")
    parser.add_argument("--dry-run", action="store_true", help="Log outbound commands without sending")
    parser.add_argument(
        "--command-line-log",
        choices=("commits", "all"),
        help="Log cmd only on Enter/error (commits) or every keystroke (all)",
    )
    parser.add_argument("--gui", action="store_true", help="Open the Tk desk panel")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    conn = config.setdefault("connection", {})
    behavior = config.setdefault("behavior", {})
    if args.ip:
        conn["eos_ip"] = args.ip
    if args.transport:
        conn["transport"] = args.transport
    if args.port is not None:
        if conn.get("transport", "tcp") == "udp" or args.transport == "udp":
            conn["eos_port"] = args.port
        else:
            conn["tcp_port"] = args.port
    if args.listen_port is not None:
        conn["listen_port"] = args.listen_port
    if args.dry_run:
        behavior["dry_run"] = True
    if args.command_line_log:
        behavior["command_line_log"] = args.command_line_log

    if args.gui:
        from eosbot.gui import EosbotGui

        EosbotGui(EosbotApp(config)).run()
        return 0

    EosbotApp(config).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
