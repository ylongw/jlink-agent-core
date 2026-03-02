# jlink-agent-core

Agent-friendly J-Link automation for embedded workflows.

This project abstracts the painful part of AI-driven embedded development:
**flash / GDB server / RTT capture orchestration on real hardware**.

## Why

Most agents can write code and compile.
Few can reliably operate external J-Link hardware for real-device loops.

`jlink-agent-core` provides a stable CLI so agents (Codex, Claude Code, OpenClaw, etc.) can drive J-Link deterministically.

## Features (v0.1.0)

- `probe`: detect connected J-Link serials
- `flash`: flash firmware via `JLinkExe`
- `rtt-addr`: extract `_SEGGER_RTT` symbol from `.map`
- `gdbserver-start` / `gdbserver-stop`
- `rtt-capture`: capture logs via `JLinkRTTLogger`
- structured output via `--json` for agent consumption

## Install

```bash
cd jlink-agent-core
python3 -m pip install -e .
```

## Quick start

```bash
# 1) Discover debuggers
jlink-agent probe --json

# 2) Flash
jlink-agent flash \
  --device STM32H747XI_M7 \
  --serial 801039104 \
  --firmware .build/pro2-debug/executables/nfc_test/nfc_test.hex \
  --json

# 3) Resolve RTT address from map
jlink-agent rtt-addr \
  --map .build/pro2-debug/executables/nfc_test/nfc_test.map \
  --json

# 4) Capture RTT for 30s
jlink-agent rtt-capture \
  --device STM32H747XI_M7 \
  --serial 801039104 \
  --address 0x38004010 \
  --out /tmp/pro2.log \
  --duration 30 \
  --json
```

## Agent Integration Pattern

Recommended orchestration:
1. build firmware
2. `jlink-agent flash`
3. `jlink-agent rtt-addr`
4. `jlink-agent rtt-capture`
5. parse log + classify pass/fail

This enables fully automated compile→flash→observe loops.

## Limitations (current)

- `gdbserver-stop` currently stops all JLinkGDBServer processes (coarse kill)
- no process lock manager yet (planned for multi-agent safety)
- assumes SEGGER tools are installed in PATH

## Roadmap

- board profile support (`--profile`) with YAML
- strict device lock manager (per-SN mutex)
- richer health checks and error taxonomy
- first-class OpenClaw/Claude/Codex wrapper skills

## License

MIT
