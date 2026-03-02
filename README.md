# jlink-debug (Skill-first repository)

A minimal, standard-style skill repository:

- `SKILL.md` (required metadata + instructions)
- `scripts/jlink_agent.py` (main executable wrapper)
- `scripts/jlink_nfc_ab.sh` (example orchestration)

## What it does

Provides agent-friendly J-Link primitives:

- probe J-Link devices
- flash firmware
- read `_SEGGER_RTT` address from map
- start/stop GDB server
- capture RTT logs

## Quick validation

```bash
python3 scripts/jlink_agent.py probe --json
```

## Example (with firmware-pro2)

```bash
python3 scripts/jlink_agent.py flash \
  --device STM32H747XI_M7 \
  --serial <JLINK_SN> \
  --firmware ~/Documents/dec/firmware-pro2/.build/pro2-debug/executables/nfc_test/nfc_test.hex \
  --json
```

## License

MIT
