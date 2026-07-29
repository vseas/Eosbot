#!/usr/bin/env python3
"""
Eosbot main loop — subscribe to EOS feedback and offer operator options.

CVS 2026
2026-07-29

Vertical slice:
  1. Connect + ping
  2. Subscribe to feedback
  3. Log raw OSC
  4. Map events
  5. Present hard-coded options → send chosen command
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from eosbot.events import EosEvent, parse_osc_event
from eosbot.osc_recv import EosReceiver
from eosbot.osc_send import EosSender
from eosbot.policies.starter import Option, options_for_event


def load_config(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def default_config_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


class EosbotApp:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        conn = config.get("connection", {})
        behavior = config.get("behavior", {})

        self.dry_run = bool(behavior.get("dry_run", False))
        self.log_raw = bool(behavior.get("log_raw_osc", True))
        self.interactive = bool(behavior.get("interactive_options", True))

        self.sender = EosSender(
            ip=conn.get("eos_ip", "127.0.0.1"),
            port=int(conn.get("eos_port", 8000)),
            dry_run=self.dry_run,
            log_fn=self.log,
        )
        self.receiver = EosReceiver(
            listen_ip=conn.get("listen_ip", "0.0.0.0"),
            listen_port=int(conn.get("listen_port", 8001)),
            handler=self._on_osc,
            log_fn=self.log,
        )
        self._events: "queue.Queue[EosEvent]" = queue.Queue()

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _on_osc(self, address: str, args: Sequence[Any]) -> None:
        if self.log_raw:
            self.log(f"OSC IN: {address} {list(args)}")
        event = parse_osc_event(address, args)
        self._events.put(event)

    def start(self) -> None:
        self.log("Eosbot 0.1.0 — CVS 2026")
        self.log(f"Target EOS: {self.sender.ip}:{self.sender.port}")
        if self.dry_run:
            self.log("Mode: dry run (commands will not be sent)")

        self.receiver.start()
        time.sleep(0.2)

        self.sender.ping()
        if self.config.get("subscribe", {}).get("enabled", True):
            self.sender.subscribe(True)
            self.log("Subscribe sent — ensure EOS OSC UDP is enabled and reply port matches listen_port")

        self.log("Waiting for OSC. Press Ctrl+C to quit.")
        self.log("Tip: fire a cue or ping from the console to exercise policies.")

        try:
            while True:
                try:
                    event = self._events.get(timeout=0.25)
                except queue.Empty:
                    continue
                self._handle_event(event)
        except KeyboardInterrupt:
            self.log("\nShutting down…")
        finally:
            self.receiver.stop()

    def _handle_event(self, event: EosEvent) -> None:
        self.log(f"Event: kind={event.kind} cue={event.cue!r} summary={event.raw_summary}")
        options = options_for_event(event)
        if not options:
            return
        if not self.interactive:
            self.log(f"Options available ({len(options)}) but interactive_options is false")
            return
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
                self.sender.send(opt.address, list(opt.args or []))
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
    parser.add_argument("--port", type=int, help="Override EOS OSC port")
    parser.add_argument("--listen-port", type=int, help="Override local listen port")
    parser.add_argument("--dry-run", action="store_true", help="Log outbound commands without sending")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.ip:
        config.setdefault("connection", {})["eos_ip"] = args.ip
    if args.port is not None:
        config.setdefault("connection", {})["eos_port"] = args.port
    if args.listen_port is not None:
        config.setdefault("connection", {})["listen_port"] = args.listen_port
    if args.dry_run:
        config.setdefault("behavior", {})["dry_run"] = True

    EosbotApp(config).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
