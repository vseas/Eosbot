"""
Eosbot Tk desk panel — live state from OSC feedback.

Run:
  python3 -m eosbot.gui
"""

from __future__ import annotations

import argparse
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk
from typing import List, Optional, Set

from eosbot.app import EosbotApp, default_config_path, load_config
from eosbot.events import EosEvent
from eosbot.policies.starter import Option, options_for_event


class EosbotGui:
    def __init__(self, app: EosbotApp):
        self.app = app
        # GUI owns prompting; keep CLI input() off.
        self.app.interactive = False
        self.app.log_style = "none"
        self.app.log = self._app_log

        self.root = tk.Tk()
        self.root.title("Eosbot")
        self.root.minsize(720, 420)
        self.root.geometry("860x620")

        self.status_var = tk.StringVar(value="Disconnected")
        self.show_var = tk.StringVar(value="—")
        self.mode_var = tk.StringVar(value="—")
        self.user_var = tk.StringVar(value="—")
        self.active_var = tk.StringVar(value="—")
        self.prev_var = tk.StringVar(value="—")
        self.next_var = tk.StringVar(value="—")
        self.fire_var = tk.StringVar(value="—")
        self.chan_var = tk.StringVar(value="—")
        self.wheel_var = tk.StringVar(value="—")
        self.cmd_var = tk.StringVar(value="—")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._show_desk_state = tk.BooleanVar(value=True)
        self._activity_expanded = tk.BooleanVar(value=True)
        self._activity_toggle_label = tk.StringVar(value="Minimize activity")

        self._option_buttons: List[ttk.Button] = []
        self._connected = False
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._tick)

    def _app_log(self, message: str) -> None:
        # Quiet console noise while GUI is up; connection errors still useful.
        if message.startswith("Connection") or message.startswith("Tip"):
            print(message, flush=True)

    def _build(self) -> None:
        self.outer = ttk.Frame(self.root, padding=10)
        self.outer.pack(fill="both", expand=True)

        # Connection
        conn = ttk.LabelFrame(self.outer, text="Connection", padding=8)
        conn.pack(fill="x")
        ttk.Label(conn, text=self.app.target_desc).pack(side="left")
        ttk.Label(conn, textvariable=self.status_var).pack(side="left", padx=12)
        ttk.Button(conn, text="Connect", command=self.connect).pack(side="right", padx=2)
        ttk.Button(conn, text="Disconnect", command=self.disconnect).pack(side="right", padx=2)
        ttk.Button(conn, text="Ping", command=self.ping).pack(side="right", padx=2)

        # View toggles
        view = ttk.Frame(self.outer)
        view.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            view,
            text="Show desk state",
            variable=self._show_desk_state,
            command=self._toggle_desk_state,
        ).pack(side="left")
        ttk.Button(
            view,
            textvariable=self._activity_toggle_label,
            command=self._toggle_activity,
            width=18,
        ).pack(side="right")

        # Desk state
        self.state_frame = ttk.LabelFrame(self.outer, text="Desk state", padding=8)
        self.state_frame.pack(fill="x", pady=(8, 0))
        self.state_frame.columnconfigure(1, weight=1)
        self.state_frame.columnconfigure(3, weight=1)

        rows = [
            (0, "Show", self.show_var, "Mode", self.mode_var),
            (1, "User", self.user_var, "Last fire", self.fire_var),
            (2, "Active", self.active_var, "Previous", self.prev_var),
            (3, "Pending", self.next_var, "Channel", self.chan_var),
            (4, "Wheel", self.wheel_var, "Command", self.cmd_var),
        ]
        for r, l1, v1, l2, v2 in rows:
            ttk.Label(self.state_frame, text=l1 + ":").grid(row=r, column=0, sticky="nw", pady=2)
            ttk.Label(self.state_frame, textvariable=v1, wraplength=320).grid(
                row=r, column=1, sticky="nw", padx=(4, 16), pady=2
            )
            ttk.Label(self.state_frame, text=l2 + ":").grid(row=r, column=2, sticky="nw", pady=2)
            ttk.Label(self.state_frame, textvariable=v2, wraplength=320).grid(
                row=r, column=3, sticky="nw", padx=4, pady=2
            )

        ttk.Label(self.state_frame, text="Fade:").grid(row=5, column=0, sticky="w", pady=2)
        self.progress = ttk.Progressbar(
            self.state_frame, variable=self.progress_var, maximum=1.0, mode="determinate"
        )
        self.progress.grid(row=5, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        # Options + activity
        self.lower = ttk.Frame(self.outer)
        self.lower.pack(fill="both", expand=True, pady=(8, 0))
        self.lower.columnconfigure(0, weight=1)
        self.lower.columnconfigure(1, weight=1)
        self.lower.rowconfigure(0, weight=1)

        opts = ttk.LabelFrame(self.lower, text="Options", padding=8)
        opts.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.options_hint = ttk.Label(
            opts, text="Options will appear here when a cue fires (starter policies)."
        )
        self.options_hint.pack(anchor="w")
        self.options_frame = ttk.Frame(opts)
        self.options_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.activity_frame = ttk.LabelFrame(self.lower, text="Activity", padding=8)
        self.activity_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.activity_body = ttk.Frame(self.activity_frame)
        self.activity_body.pack(fill="both", expand=True)
        self.log_box = scrolledtext.ScrolledText(
            self.activity_body, height=14, wrap="word", state="disabled"
        )
        self.log_box.pack(fill="both", expand=True)
        self._clear_btn = ttk.Button(
            self.activity_body, text="Clear", command=self._clear_log
        )
        self._clear_btn.pack(anchor="e", pady=(4, 0))

    def _toggle_desk_state(self) -> None:
        if self._show_desk_state.get():
            # Re-pack above the lower pane.
            self.state_frame.pack(fill="x", pady=(8, 0), before=self.lower)
        else:
            self.state_frame.pack_forget()

    def _toggle_activity(self) -> None:
        expanded = not self._activity_expanded.get()
        self._activity_expanded.set(expanded)
        if expanded:
            self._activity_toggle_label.set("Minimize activity")
            self.activity_body.pack(fill="both", expand=True)
            self.lower.columnconfigure(1, weight=1)
            self.activity_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        else:
            self._activity_toggle_label.set("Show activity")
            self.activity_body.pack_forget()
            # Collapse column weight so Options can use the width.
            self.lower.columnconfigure(1, weight=0)
            self.activity_frame.grid(row=0, column=1, sticky="ne", padx=(4, 0))

    def connect(self) -> None:
        if self._connected:
            return
        try:
            self.app.connect()
        except OSError as exc:
            self.status_var.set(f"Failed: {exc}")
            messagebox.showerror("Eosbot", f"Could not connect:\n{exc}")
            return
        self._connected = True
        self.status_var.set("Connected")
        self._log_activity(f"Connected to {self.app.target_desc}")

    def disconnect(self) -> None:
        if not self._connected:
            return
        self.app.disconnect()
        self._connected = False
        self.status_var.set("Disconnected")
        self._log_activity("Disconnected")

    def ping(self) -> None:
        if not self._connected:
            messagebox.showinfo("Eosbot", "Connect first.")
            return
        self.app.link.ping()
        self._log_activity("Ping sent")

    def _tick(self) -> None:
        if self._connected:
            for event, changed in self.app.drain_events():
                self._refresh_state()
                if changed:
                    self._log_activity(self.app.state.format_snapshot(changed))
                    self._maybe_show_options(event, changed)
        self.root.after(100, self._tick)

    def _refresh_state(self) -> None:
        s = self.app.state
        self.show_var.set(s.show_name or "—")
        self.mode_var.set(s.mode or "—")
        self.user_var.set(str(s.user) if s.user is not None else "—")
        if s.active_cue:
            label = f"  {s.active_cue_label}" if s.active_cue_label else ""
            self.active_var.set(f"{s.active_cue}{label}")
        else:
            self.active_var.set("—")
        if s.previous_cue:
            label = f"  {s.previous_cue_label}" if s.previous_cue_label else ""
            self.prev_var.set(f"{s.previous_cue}{label}")
        else:
            self.prev_var.set("—")
        if s.pending_cue:
            label = f"  {s.pending_cue_label}" if s.pending_cue_label else ""
            self.next_var.set(f"{s.pending_cue}{label}")
        else:
            self.next_var.set("—")
        if s.last_fire_cue:
            label = f"  {s.last_fire_label}" if s.last_fire_label else ""
            self.fire_var.set(f"{s.last_fire_cue}{label}")
        else:
            self.fire_var.set("—")
        self.chan_var.set(s.active_chan if s.active_chan else "—")
        self.wheel_var.set(s.active_wheel if s.active_wheel else "—")
        cmd = s.command_line or "—"
        if s.command_line_error:
            cmd = f"ERROR  {cmd}"
        self.cmd_var.set(cmd)
        if s.active_progress is not None:
            self.progress_var.set(max(0.0, min(1.0, float(s.active_progress))))

    def _maybe_show_options(self, event: EosEvent, changed: Set[str]) -> None:
        if not (
            event.kind == "cue_fire"
            or "active_cue" in changed
            or "command_line" in changed
        ):
            return
        options = options_for_event(event)
        self._set_options(options)

    def _set_options(self, options: List[Option]) -> None:
        for btn in self._option_buttons:
            btn.destroy()
        self._option_buttons.clear()
        if not options:
            self.options_hint.configure(
                text="Options will appear here when a cue fires (starter policies)."
            )
            return
        self.options_hint.configure(text="Choose an action:")
        for opt in options:
            btn = ttk.Button(
                self.options_frame,
                text=f"[{opt.key}] {opt.label}",
                command=lambda o=opt: self._run_option(o),
            )
            btn.pack(fill="x", pady=2)
            self._option_buttons.append(btn)

    def _run_option(self, opt: Option) -> None:
        if not opt.address:
            self._log_activity("Skipped")
            return
        if not self._connected:
            messagebox.showinfo("Eosbot", "Connect first.")
            return
        self.app.link.send(opt.address, list(opt.args or []))
        self._log_activity(f"Sent {opt.address} {list(opt.args or [])}")

    def _log_activity(self, line: str) -> None:
        if line == "STATE (empty)":
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{stamp}  {line}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        try:
            self.disconnect()
        finally:
            self.root.destroy()

    def run(self, auto_connect: bool = True) -> None:
        if auto_connect:
            self.root.after(200, self.connect)
        self.root.mainloop()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Eosbot — Tk desk panel")
    parser.add_argument("--config", default=default_config_path())
    parser.add_argument("--ip", help="Override EOS IP")
    parser.add_argument("--no-auto-connect", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.ip:
        config.setdefault("connection", {})["eos_ip"] = args.ip

    app = EosbotApp(config)
    EosbotGui(app).run(auto_connect=not args.no_auto_connect)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
