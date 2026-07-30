"""
Bidirectional OSC over TCP for ETC EOS (default port 3032).

Eos listens for TCP connections; one socket carries both directions.
Default framing is OSC 1.0 (4-byte packet-length headers), which matches
Eos Setup → Show Control → OSC unless you switch the desk to OSC 1.1 SLIP.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional, Sequence

from pythonosc.dispatcher import Dispatcher
from pythonosc.tcp_client import SimpleTCPClient

OscHandler = Callable[[str, Sequence[Any]], None]


class EosTcpSession:
    """Connect to Eos OSC TCP and send/receive on the same socket."""

    def __init__(
        self,
        ip: str,
        port: int = 3032,
        *,
        mode: str = "1.0",
        handler: Optional[OscHandler] = None,
        log_fn: Optional[Callable[[str], None]] = None,
        dry_run: bool = False,
    ):
        self.ip = ip
        self.port = port
        self.mode = mode
        self.handler = handler
        self.log_fn = log_fn or print
        self.dry_run = dry_run
        self._client: Optional[SimpleTCPClient] = None
        self._dispatcher = Dispatcher()
        self._dispatcher.set_default_handler(self._on_message)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _on_message(self, address: str, *args: Any) -> None:
        if self.handler:
            self.handler(address, args)

    def connect(self) -> None:
        if self._client is not None:
            return
        self.log_fn(f"Connecting OSC TCP to {self.ip}:{self.port} (mode {self.mode})")
        self._client = SimpleTCPClient(self.ip, self.port, mode=self.mode, timeout=5.0)
        self.log_fn(f"OSC TCP connected to {self.ip}:{self.port}")

    def start(self) -> None:
        self.connect()
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self) -> None:
        assert self._client is not None
        while not self._stop.is_set():
            try:
                packets = self._client.receive(0.25)
            except OSError as exc:
                if self._stop.is_set():
                    break
                self.log_fn(f"OSC TCP receive error: {exc}")
                break
            for packet in packets:
                self._dispatcher.call_handlers_for_packet(packet, (self.ip, self.port))

    def send(self, address: str, args: Optional[List[Any]] = None) -> None:
        args = args or []
        if self.dry_run:
            self.log_fn(f"DRY RUN: {address} {args}")
            return
        if self._client is None:
            self.connect()
        assert self._client is not None
        self._client.send_message(address, args if args else [])
        self.log_fn(f"Sent: {address} {args}")

    def ping(self) -> None:
        self.send("/eos/ping", ["eosbot"])

    def subscribe(self, enable: bool = True) -> None:
        self.send("/eos/subscribe", [1 if enable else 0])

    def newcmd(self, path: str) -> None:
        address = path if path.startswith("/") else f"/eos/newcmd/{path}"
        self.send(address, [])

    def key(self, key_name: str) -> None:
        self.send(f"/eos/key/{key_name}", [])

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
            self.log_fn("OSC TCP disconnected")
