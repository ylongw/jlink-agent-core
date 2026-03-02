#!/usr/bin/env bash
set -euo pipefail

# Example one-board loop: flash + resolve RTT address + capture RTT.
# Usage:
#   SN=801039104 HEX=/path/fw.hex MAP=/path/fw.map bash scripts/jlink_nfc_ab.sh

DEVICE="${DEVICE:-STM32H747XI_M7}"
SN="${SN:?SN is required}"
HEX="${HEX:?HEX is required}"
MAP="${MAP:?MAP is required}"
LOG="${LOG:-/tmp/jlink_skill_rtt.log}"
DURATION="${DURATION:-20}"

python3 scripts/jlink_agent.py flash \
  --device "$DEVICE" \
  --serial "$SN" \
  --firmware "$HEX" \
  --json

ADDR=$(python3 scripts/jlink_agent.py rtt-addr --map "$MAP" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])')

python3 scripts/jlink_agent.py rtt-capture \
  --device "$DEVICE" \
  --serial "$SN" \
  --address "$ADDR" \
  --out "$LOG" \
  --duration "$DURATION" \
  --json

echo "RTT log: $LOG"
