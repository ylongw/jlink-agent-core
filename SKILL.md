---
name: jlink-debug
description: Operate SEGGER J-Link for embedded bring-up and hardware-in-the-loop loops: detect probes, flash firmware, start/stop GDB server, resolve RTT address from map files, capture RTT logs, and drive gdb in batch mode for breakpoints/step/variable inspection. Use when a user asks to burn/download firmware, run real-board debug sessions, set breakpoints, inspect memory/registers, or automate compile→flash→RTT verification on STM32/MCU projects.
---

# J-Link Debug Skill

Agent-friendly J-Link automation. All commands support `--json` for machine-readable output.

## Prerequisites

- `JLinkExe`, `JLinkGDBServer` in PATH (SEGGER J-Link Software Pack). `JLinkRTTLogger`
  is **NOT** used — see [RTT notes](#rtt-known-issues--buffer-tuning).
- `arm-none-eabi-gdb` in PATH for `gdb-batch`
- Python 3.9+ (no external deps)

## Project defaults — OneKey Pro 2 (firmware-pro2)

When used in the firmware-pro2 repo, prefer these parameters:

| Param | Value |
|---|---|
| `--device` | `ONEKEYH7` (custom device ID mapped to STM32H747XI_M7) |
| `--speed` | `12000` |
| `--gdb` | `/Users/wangyunlong/onekey_toolchains/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gdb` |
| `--gdb-port` | `50000` |
| `--rtt-port` | `19021` |
| ELF path | `.build/arm-toolchain-debug/executables/apps/core/core.elf` |
| HEX path | `.build/arm-toolchain-debug/executables/apps/core/core.hex` |
| Map path | `.build/arm-toolchain-debug/executables/apps/core/core.map` |
| RTT symbol | `_SEGGER_RTT` (resolved dynamically from map) |

If only one J-Link is connected, first run `probe` to get the serial number; pass it to all subsequent commands.

## Commands

### 1. Probe detection

```bash
python3 scripts/jlink_agent.py probe --json
# → {"ok": true, "serial_numbers": ["801039104"], ...}
```

### 2. Flash firmware (JLinkExe loadfile)

```bash
python3 scripts/jlink_agent.py flash \
  --device ONEKEYH7 \
  --serial 801039104 \
  --firmware .build/arm-toolchain-debug/executables/apps/core/core.hex \
  --speed 12000 \
  --json
```

Uses a `r / h / loadfile / r / g / exit` JLinkExe script — simpler and more reliable than gdb `load`, and leaves the CPU running.

### 3. Resolve RTT address from map file

```bash
python3 scripts/jlink_agent.py rtt-addr \
  --map .build/arm-toolchain-debug/executables/apps/core/core.map \
  --json
# → {"ok": true, "address": "0x24008410"}
```

### 4. Start / stop JLinkGDBServer

```bash
# Start (background by default)
python3 scripts/jlink_agent.py gdbserver-start \
  --device ONEKEYH7 --serial 801039104 \
  --gdb-port 50000 --rtt-port 19021 --speed 12000 --json

# Stop any running instance
python3 scripts/jlink_agent.py gdbserver-stop --json
```

### 5. Capture RTT logs to a file

```bash
# Stops any pre-existing JLinkGDBServer to free the ports, spawns a
# transient one with -rtt -rttsearchaddr, drains the RTT telnet port,
# then tears down. Don't run concurrently with gdbserver-start / gdb-batch.
python3 scripts/jlink_agent.py rtt-capture \
  --device ONEKEYH7 --serial 801039104 \
  --address 0x24008410 \
  --out /tmp/boot.log --duration 20 --speed 12000 --json
```

`--address` is the `_SEGGER_RTT` control-block address; resolve it via
`rtt-addr` (it shifts every build, so don't hard-code).

Then read the resulting file with the `Read` tool. Output JSON includes
`"via": "gdbserver_telnet"` to confirm the transport used.

#### RTT known issues + buffer tuning

> Read this section before assuming RTT is "broken".

**1. `JLinkRTTLogger` does NOT work on J-Link Software V8.96+.** It
silently ignores `-RTTAddress` and `-RTTSearchRanges` and reports
"RTT Control Block not found" even when the address is verifiably
correct (verify with `JLinkExe ... mem <addr> 0x40` — the "SEGGER RTT"
magic is right there). This skill's `rtt-capture` works around this by
going through `JLinkGDBServer -rtt -rttsearchaddr` + a socket read of
the RTT telnet port. **Do not** fall back to `JLinkRTTLogger` thinking
it's "simpler" — it will look exactly the same as a probe / address
problem and waste an hour.

**2. `nc localhost <rtt-port>` exits on first EOF / banner.** If you're
manually inspecting the RTT telnet stream (instead of using
`rtt-capture`), use a Python socket reader with reconnect, not `nc`:

```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("localhost", 19021))
s.settimeout(1.0)
with open("/tmp/rtt.log", "wb", buffering=0) as f:
    while True:
        try:    f.write(s.recv(4096))
        except socket.timeout: continue
```

**3. RTT default `BUFFER_SIZE_UP = 1024` + `SEGGER_RTT_MODE_NO_BLOCK_SKIP`
silently drops logs during boot bursts.** The host drain rate over SWD
is finite (~tens of KB/s); LVGL / display init can emit several KB in
one tick. Symptom: early-boot logs from one task show up, others (e.g.
the FG task starting right when buffer is full) don't, even though
their format strings are clearly in the `.elf`. To debug
boot-window code, bump `BUFFER_SIZE_UP` to 16384 in
`hal/segger_sysview/SEGGER_RTT_Conf.h` and rebuild — and remember to
revert before shipping (it eats AXI SRAM).

**4. Address shifts every build.** Always re-run `rtt-addr` after a
rebuild; don't reuse the address from a previous session.

### 6. gdb-batch — breakpoints, stepping, variable/register inspection

Runs `arm-none-eabi-gdb` in batch mode against an **already-running** `JLinkGDBServer`, executes a list of gdb commands, and returns the captured stdout/stderr as JSON. Use this for agent-driven interactive debugging — set a breakpoint, let it hit, print variables, dump registers, then exit.

Prerequisite: a `JLinkGDBServer` is already listening on `--gdb-port`. Start one via `gdbserver-start` first.

#### Inline commands

```bash
python3 scripts/jlink_agent.py gdb-batch \
  --elf .build/arm-toolchain-debug/executables/apps/core/core.elf \
  --gdb /Users/wangyunlong/onekey_toolchains/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gdb \
  --gdb-port 50000 \
  --commands \
    "break task_foreground" \
    "continue" \
    "info registers" \
    "bt" \
    "print lvgl_disp_hres" \
    "print lvgl_disp_vres" \
  --timeout 30 \
  --json
```

Each `--commands` arg becomes a separate `-ex` passed to gdb. The skill prepends `target remote :<port>` and `monitor halt`, and appends `quit`. So the actual gdb invocation is:

```
arm-none-eabi-gdb -batch -nx \
  -ex "target remote :50000" \
  -ex "monitor halt" \
  -ex "break task_foreground" \
  -ex "continue" \
  -ex "info registers" \
  -ex "bt" \
  -ex "print lvgl_disp_hres" \
  -ex "print lvgl_disp_vres" \
  -ex quit \
  core.elf
```

#### Script file

For longer sequences, write a gdb script file and pass it via `--script`:

```bash
cat > /tmp/debug.gdb <<'EOF'
break page_manager_push
commands
  silent
  printf "push id=%d\n", id
  continue
end
continue
EOF

python3 scripts/jlink_agent.py gdb-batch \
  --elf core.elf --gdb arm-none-eabi-gdb --gdb-port 50000 \
  --script /tmp/debug.gdb --timeout 20 --json
```

#### Common recipes

**Halt and inspect current state (no breakpoint needed):**
```bash
--commands "info registers" "bt" "print g_alert"
```
The skill already halts the CPU on connect, so you don't need to add `monitor halt` yourself.

**Hit a breakpoint and dump context:**
```bash
--commands "break connect_app_wallet_create" "continue" \
           "bt full" "info locals" "info registers"
```

**Step through code:**
```bash
--commands "break page_manager_push" "continue" "step" "step" "bt"
```

**Inspect a variable or struct:**
```bash
--commands "print lvgl_disp_hres" "print *lv_scr_act()"
```

**Read memory at an address:**
```bash
--commands "x/32xw 0x24008410"   # 32 words at the RTT control block
```

**Dump the framebuffer header:**
```bash
--commands "x/4xw 0xD0000000" "x/4xw 0xD0200000"
```

#### Output

```json
{
  "ok": true,
  "returncode": 0,
  "stdout": "<full gdb output, parse for hits/values>",
  "stderr": "",
  "cmdline": ["arm-none-eabi-gdb", "-batch", ...]
}
```

On timeout the skill returns `{"ok": false, "timeout": true, ...}` with whatever output gdb produced so far. Raise `--timeout` if you're waiting on a breakpoint that takes a while to hit.

## Typical workflow (compile → flash → verify → debug)

1. `ExecBuild` — build the target (`core_outputs`)
2. `jlink-debug probe` — get J-Link serial
3. `jlink-debug flash` — burn `.hex`
4. `jlink-debug rtt-capture` — grab boot logs (stop beforehand: any gdbserver)
5. `framebuffer-dump` — read LCD content as PNG
6. If something's wrong:
   - `jlink-debug gdbserver-start` in background
   - `jlink-debug gdb-batch` with breakpoints / prints
   - `jlink-debug gdbserver-stop` when done

## Safety rules

- Never flash without explicit board-to-SN mapping (`--serial`).
- `gdb-batch` halts the CPU on connect — your firmware will be paused until gdb exits. Pass `--no-halt` only when you deliberately want to observe a running system (rare).
- Only one J-Link session at a time: `rtt-capture`, `flash`, and `gdbserver-*`/`gdb-batch` cannot run simultaneously. Stop one before starting the other. `rtt-capture` will auto-kill stale `JLinkGDBServer` to free the ports.
- If RTT log is empty, diagnose in this order:
  1. Re-resolve `--address` via `rtt-addr` — it shifts every build.
  2. Verify the magic with `JLinkExe ... mem <addr> 0x10` — first 10 bytes must be `"SEGGER RTT"`.
  3. Re-read [RTT known issues](#rtt-known-issues--buffer-tuning). Do NOT try `JLinkRTTLogger` directly; it's the broken path this skill specifically works around.
  4. If the firmware has just been re-flashed and a previous `JLinkGDBServer` is still alive, kill it (`gdbserver-stop`) before re-capturing — the old session may be holding a stale RTT control-block pointer.
- Prefer JSON output in automation.

## Scripts

- `scripts/jlink_agent.py` — main CLI wrapper.
- `scripts/jlink_nfc_ab.sh` — example orchestration script for one-board flash+RTT.
