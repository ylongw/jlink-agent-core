#!/usr/bin/env bash
set -euo pipefail

# Example only: quick hardware loop for one board.
# Real dual-board orchestration should be done in project-specific script.

DEVICE="${DEVICE:-STM32H747XI_M7}"
SN="${SN:?SN is required}"
HEX="${HEX:?HEX is required}"
MAP="${MAP:?MAP is required}"
LOG="${LOG:-/tmp/jlink_skill_rtt.log}"
DURATION="${DURATION:-20}"

python3 -m jlink_agent_core.cli flash \
  --device "$DEVICE" \
  --serial "$SN" \
  --firmware "$HEX" \
  --json

ADDR=$(python3 -m jlink_agent_core.cli rtt-addr --map "$MAP" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])')

python3 -m jlink_agent_core.cli rtt-capture \
  --device "$DEVICE" \
  --serial "$SN" \
  --address "$ADDR" \
  --out "$LOG" \
  --duration "$DURATION" \
  --json

echo "RTT log: $LOG"
