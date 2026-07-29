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

- `connection.eos_ip` / `eos_port` — console (usually port **8000**)
- `connection.listen_port` — local UDP port for EOS replies (default **8001**)
- On the console: enable OSC, set UDP target to this machine’s IP and listen port

## Run

```bash
python3 -m eosbot.app --ip 172.16.6.11
# or dry-run outbound only:
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
    app.py           # main loop
    osc_send.py      # outbound UDP + command builders
    osc_recv.py      # inbound listener
    events.py        # OSC → events
    policies/        # your growing option definitions
```

## Notes

- Exact `/eos/out/...` paths vary by EOS software version; start with raw logging
  and tighten `events.py` / policies as you see real traffic.
- Show Target Manager remains the batch CSV/palette import tool; Eosbot is the
  live observe → choose → act companion.
