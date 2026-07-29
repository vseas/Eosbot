"""
Inbound OSC listener for ETC EOS feedback.

Runs a threaded UDP server and forwards messages to a callback.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional, Sequence

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

OscHandler = Callable[[str, Sequence[Any]], None]


class EosReceiver:
    """Listen for OSC from EOS and dispatch to a handler."""

    def __init__(
        self,
        listen_ip: str = "0.0.0.0",
        listen_port: int = 8001,
        *,
        handler: Optional[OscHandler] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.handler = handler
        self.log_fn = log_fn or print
        self._server: Optional[ThreadingOSCUDPServer] = None
        self._thread: Optional[threading.Thread] = None

    def _on_message(self, address: str, *args: Any) -> None:
        if self.handler:
            self.handler(address, args)

    def start(self) -> None:
        if self._server is not None:
            return

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._on_message)

        self._server = ThreadingOSCUDPServer((self.listen_ip, self.listen_port), dispatcher)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.log_fn(f"Listening for EOS OSC on {self.listen_ip}:{self.listen_port}")

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server = None
        self._thread = None
        self.log_fn("OSC listener stopped")
