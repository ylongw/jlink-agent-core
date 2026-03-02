#!/usr/bin/env bash
set -euo pipefail

# Example: single-board flash + RTT capture
DEVICE="STM32H747XI_M7"
SN="801039104"
HEX=".build/pro2-debug/executables/nfc_test/nfc_test.hex"
MAP=".build/pro2-debug/executables/nfc_test/nfc_test.map"
LOG="/tmp/pro2_rtt.log"

jlink-agent flash --device "$DEVICE" --serial "$SN" --firmware "$HEX" --json
ADDR=$(jlink-agent rtt-addr --map "$MAP" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])')
jlink-agent rtt-capture --device "$DEVICE" --serial "$SN" --address "$ADDR" --out "$LOG" --duration 20 --json

echo "RTT saved: $LOG"
