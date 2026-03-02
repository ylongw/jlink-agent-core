---
name: jlink-debug
description: Operate SEGGER J-Link for embedded bring-up and hardware-in-the-loop loops: detect probes, flash firmware, start/stop GDB server, resolve RTT address from map files, and capture RTT logs. Use when a user asks to burn/download firmware, run real-board debug sessions, or automate compile→flash→RTT verification on STM32/MCU projects.
---

# J-Link Debug Skill

Use this skill to run J-Link flashing and RTT debugging in a deterministic, agent-friendly way.

## Quick Start

1. Ensure `JLinkExe`, `JLinkGDBServer`, and `JLinkRTTLogger` are installed and in PATH.
2. Build target firmware first (`.hex` + `.map`).
3. Run `scripts/jlink_agent.py` with `--json` for machine-readable output.

## Core Commands

```bash
# 1) list connected probes
python3 scripts/jlink_agent.py probe --json

# 2) flash firmware
python3 scripts/jlink_agent.py flash \
  --device STM32H747XI_M7 \
  --serial <JLINK_SN> \
  --firmware <path/to/firmware.hex> \
  --json

# 3) resolve RTT address from map
python3 scripts/jlink_agent.py rtt-addr \
  --map <path/to/firmware.map> \
  --json

# 4) capture RTT logs
python3 scripts/jlink_agent.py rtt-capture \
  --device STM32H747XI_M7 \
  --serial <JLINK_SN> \
  --address <0xADDR> \
  --out /tmp/rtt.log \
  --duration 20 \
  --json
```

## Workflow Pattern

1. build firmware
2. `flash`
3. `rtt-addr`
4. `rtt-capture`
5. parse logs and classify pass/fail

## Safety Rules

- Never flash without explicit board-to-SN mapping.
- If RTT log is empty, diagnose infra first (wrong SN, wrong RTT address, logger timing).
- Prefer JSON output in automation.

## Scripts

- `scripts/jlink_agent.py` — main CLI wrapper.
- `scripts/jlink_nfc_ab.sh` — example orchestration script for one-board flash+RTT.
