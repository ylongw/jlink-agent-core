# J-Link Debug Skill

Agent-friendly [SEGGER J-Link](https://www.segger.com/products/debug-probes/j-link/) automation for embedded firmware development. Detect probes, flash firmware, resolve RTT addresses, start/stop GDB server, and capture RTT logs — all with machine-readable JSON output.

Built for AI coding agents (OpenClaw, Claude Code, etc.) to run compile → flash → RTT verification loops on real hardware without human intervention.

## Features

- **Probe detection** — List all connected J-Link serial numbers
- **Firmware flashing** — Flash `.hex` files via SWD with automatic reset
- **RTT address resolution** — Parse `.map` files to find `_SEGGER_RTT` symbol address
- **GDB server management** — Start/stop `JLinkGDBServer` (foreground or background)
- **RTT log capture** — Time-limited `JLinkRTTLogger` capture with clean signal handling
- **JSON output** — All commands support `--json` for agent-friendly parsing

## Prerequisites

Install [SEGGER J-Link Software Pack](https://www.segger.com/downloads/jlink/):

| Tool | Purpose |
|------|---------|
| `JLinkExe` | Probe detection & firmware flashing |
| `JLinkGDBServer` | GDB debugging server |
| `JLinkRTTLogger` | RTT log capture |

Python 3.9+ (no external dependencies).

## Installation

### As OpenClaw Skill
```bash
clawhub install jlink-debug
```

### Manual
```bash
git clone https://github.com/ylongw/jlink-debug-skill.git
cd jlink-debug-skill
python3 scripts/jlink_agent.py probe --json
```

## Usage

### List connected J-Link probes
```bash
python3 scripts/jlink_agent.py probe --json
```
```json
{
  "ok": true,
  "serial_numbers": ["601012425", "801039104"]
}
```

### Flash firmware
```bash
python3 scripts/jlink_agent.py flash \
  --device STM32H747XI_M7 \
  --serial 801039104 \
  --firmware path/to/firmware.hex \
  --json
```

### Resolve RTT address from `.map` file
```bash
python3 scripts/jlink_agent.py rtt-addr \
  --map path/to/firmware.map \
  --json
```
```json
{
  "ok": true,
  "address": "0x24000000"
}
```

### Capture RTT logs
```bash
python3 scripts/jlink_agent.py rtt-capture \
  --device STM32H747XI_M7 \
  --serial 801039104 \
  --address 0x24000000 \
  --out /tmp/rtt.log \
  --duration 20 \
  --json
```

### Start/stop GDB server
```bash
# Start (background)
python3 scripts/jlink_agent.py gdbserver-start \
  --device STM32H747XI_M7 \
  --serial 801039104 \
  --json

# Stop
python3 scripts/jlink_agent.py gdbserver-stop --json
```

## Automation Workflow

The typical agent loop:

```
1. Build firmware        (cmake --build ...)
2. Flash to board        (jlink_agent.py flash ...)
3. Resolve RTT address   (jlink_agent.py rtt-addr ...)
4. Capture RTT logs      (jlink_agent.py rtt-capture ...)
5. Parse logs            (grep/regex for PASS/FAIL)
```

The included `scripts/jlink_nfc_ab.sh` demonstrates this full loop:

```bash
SN=801039104 \
HEX=path/to/firmware.hex \
MAP=path/to/firmware.map \
DURATION=20 \
bash scripts/jlink_nfc_ab.sh
```

## Supported Targets

Tested with STM32H747XI (Cortex-M7) but works with any J-Link-supported MCU:
- STM32 family (F4, H7, L4, etc.)
- nRF52/nRF53
- ESP32 (via J-Link)
- Any SWD/JTAG target

## Command Reference

| Command | Description | Key Options |
|---------|-------------|-------------|
| `probe` | List J-Link serial numbers | `--json` |
| `flash` | Flash firmware via SWD | `--device`, `--serial`, `--firmware`, `--speed` |
| `rtt-addr` | Resolve RTT symbol from map | `--map`, `--symbol` |
| `rtt-capture` | Capture RTT logs | `--device`, `--serial`, `--address`, `--out`, `--duration` |
| `gdbserver-start` | Start GDB server | `--device`, `--serial`, `--gdb-port`, `--rtt-port`, `--foreground` |
| `gdbserver-stop` | Kill GDB server | — |

## Safety

- Never flash without explicit board-to-serial-number mapping
- If RTT log is empty, check: wrong SN? wrong RTT address? logger timing?
- `--speed` default: 12000 kHz (flash / GDB / RTT)

## Project Structure

```
jlink-debug-skill/
├── SKILL.md                    # OpenClaw/Claude Code skill definition
├── README.md                   # This file
├── LICENSE                     # MIT
└── scripts/
    ├── jlink_agent.py          # Main CLI (probe/flash/rtt-addr/rtt-capture/gdbserver)
    └── jlink_nfc_ab.sh         # Example: one-board flash + RTT capture loop
```

## License

MIT
