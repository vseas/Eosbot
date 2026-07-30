# Eosbot

Interactive OSC companion for **ETC EOS** lighting consoles.

Eosbot **subscribes** to feedback from the desk, maps it into events, presents
**options you define**, and sends chosen commands back to EOS.

## Status

Vertical slice (v0.1):

1. Connect + ping  
2. Subscribe to OSC feedback  
3. Log raw incoming OSC  
4. Normalize a few event kinds (`cue`, `command_line`, `ping`, …)  
5. Offer hard-coded starter options → send a command  

Outbound OSC helpers are seeded from LogWork **Show Target Manager**.

## Setup

```bash
cd Eosbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Edit `config.json`:

- `connection.eos_ip` — console IP
- `connection.transport` — **`tcp`** (preferred) or **`udp`**
- **TCP (default):** Eos listens on **3032**; one bidirectional socket. Match `tcp_mode` to the desk (`1.0` packet-length is Eos default; `1.1` = SLIP).
- **UDP fallback:** Eosbot transmits to `eos_port` (**8000**), receives on `listen_port` (**8001**) — the reverse of Eos RX 8000 / TX 8001.
- On the console: enable **OSC RX** and **OSC TX** (Setup → System → Show Control → OSC)

## Run

```bash
# Tk desk panel (recommended):
python3 -m eosbot.gui

# Terminal STATE logger:
python3 -m eosbot.app
# force UDP fallback:
python3 -m eosbot.app --transport udp
# dry-run outbound only:
python3 -m eosbot.app --dry-run
```

## Grow policies

Edit `eosbot/policies/starter.py` (or add new modules under `eosbot/policies/`)
to define what options appear for which events.

## Layout

```
Eosbot/
  config.json
  requirements.txt
  eosbot/
    app.py           # main loop / shared core
    gui.py           # Tk desk panel
    state.py         # live desk snapshot
    osc_tcp.py       # bidirectional TCP (port 3032)
    osc_send.py      # outbound UDP + command builders
    osc_recv.py      # inbound UDP listener
    events.py        # OSC → events
    policies/        # your growing option definitions
```

## Notes

- Exact `/eos/out/...` paths vary by EOS software version; start with raw logging
  and tighten `events.py` / policies as you see real traffic.
- Show Target Manager remains the batch CSV/palette import tool; Eosbot is the
  live observe → choose → act companion.
