---
name: jlink-debug
description: Operate SEGGER J-Link for embedded bring-up and agent-driven hardware loops: detect probes, flash firmware, start/stop GDB server, resolve RTT address from map, and capture RTT logs. Use when a user asks to burn/download firmware, run real-board debug sessions, or automate compile→flash→RTT verification on STM32/MCU projects.
---

# J-Link Debug

Use this skill to run hardware-in-the-loop steps with J-Link.

## Quick Start

1. Ensure `JLinkExe`, `JLinkGDBServer`, `JLinkRTTLogger` are installed.
2. Ensure target firmware is already compiled (`.hex` and `.map` available).
3. Use `jlink-agent` CLI commands in this order:
   - `probe`
   - `flash`
   - `rtt-addr`
   - `rtt-capture`

## Commands

Use the core CLI from `~/Documents/dec/jlink-agent-core`.

```bash
# list connected probes
python3 -m jlink_agent_core.cli probe --json

# flash firmware
python3 -m jlink_agent_core.cli flash \
  --device STM32H747XI_M7 \
  --serial <JLINK_SN> \
  --firmware <path/to/firmware.hex> \
  --json

# resolve RTT control block from map
python3 -m jlink_agent_core.cli rtt-addr \
  --map <path/to/firmware.map> \
  --json

# capture RTT logs for 30s
python3 -m jlink_agent_core.cli rtt-capture \
  --device STM32H747XI_M7 \
  --serial <JLINK_SN> \
  --address <0x...> \
  --out /tmp/rtt.log \
  --duration 30 \
  --json
```

## Workflow for Agent Automation

1. Build firmware.
2. Flash target with `flash`.
3. Resolve RTT address from `.map` (`rtt-addr`).
4. Capture logs (`rtt-capture`).
5. Parse logs and classify pass/fail.

Use JSON output for deterministic parsing.

## Safety Rules

- Kill stale J-Link/GDBServer processes before reflashing if connection is busy.
- Never flash without explicit board-to-SN mapping.
- Treat RTT timeout/empty logs as infrastructure failure first, not firmware failure.
- For dual-board tests, start both RTT loggers before judging protocol behavior.

## Resources

- scripts/jlink_nfc_ab.sh — example A/B stress orchestration using jlink-agent CLI.
- references/roadmap.md — roadmap for lock manager, profile system, and multi-agent safety.
