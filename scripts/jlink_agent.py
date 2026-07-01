#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class JLinkError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _ensure_tool(tool: str) -> None:
    if _run(["bash", "-lc", f"command -v {tool}"]).returncode != 0:
        raise JLinkError(f"missing required tool: {tool}")


def cmd_probe() -> dict:
    _ensure_tool("JLinkExe")
    proc = _run(["bash", "-lc", "JLinkExe -NoGui 1 -CommandFile /dev/stdin <<'EOF'\nShowEmuList\nexit\nEOF"])
    raw = (proc.stdout or "") + (proc.stderr or "")
    sns = sorted(set(re.findall(r"\b\d{9}\b", raw)))
    return {"ok": True, "serial_numbers": sns, "raw": raw}


def cmd_flash(device: str, serial: str, firmware: str, speed: int, jlinkscript: str | None = None) -> dict:
    _ensure_tool("JLinkExe")
    fw = Path(firmware).expanduser().resolve()
    if not fw.exists():
        raise JLinkError(f"firmware not found: {fw}")

    script = f"r\nh\nloadfile {fw}\nr\ng\nexit\n"
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(script)
        script_path = tf.name

    try:
        jlink_cmd = [
            "JLinkExe",
            "-NoGui", "1",
            "-device", device,
            "-if", "SWD",
            "-speed", str(speed),
            "-USB", serial,
            "-AutoConnect", "1",
        ]
        if jlinkscript:
            js = Path(jlinkscript).expanduser().resolve()
            if not js.exists():
                raise JLinkError(f"JLinkScript not found: {js}")
            # InitTarget() in this script brings up FMC/SDRAM, required so
            # loadfile can write the SDRAM UI-code segment (@0xD0400000).
            jlink_cmd += ["-JLinkScriptFile", str(js)]
        jlink_cmd += ["-CommandFile", script_path]
        proc = _run(jlink_cmd, timeout=120)
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = ("O.K." in out) and proc.returncode == 0
        return {"ok": ok, "returncode": proc.returncode, "output": out}
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass


def cmd_rtt_addr(map_file: str, symbol: str) -> dict:
    m = Path(map_file).expanduser().resolve()
    if not m.exists():
        raise JLinkError(f"map file not found: {m}")

    for line in m.read_text(errors="ignore").splitlines():
        if line.rstrip().endswith(symbol):
            addr = line.strip().split()[0].lower().replace("0x", "")
            return {"ok": True, "address": f"0x{addr}"}

    raise JLinkError(f"symbol not found: {symbol}")


def cmd_gdbserver_start(device: str, serial: str, gdb_port: int, rtt_port: int, speed: int, foreground: bool) -> dict:
    _ensure_tool("JLinkGDBServer")
    cmd = [
        "JLinkGDBServer",
        "-nogui",
        "-if", "swd",
        "-port", str(gdb_port),
        "-RTTTelnetPort", str(rtt_port),
        "-device", device,
        "-speed", str(speed),
        "-select", f"USB={serial}",
    ]

    if foreground:
        proc = _run(cmd)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": (proc.stdout or "") + (proc.stderr or "")}

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    return {"ok": proc.poll() is None, "pid": proc.pid, "cmd": cmd}


def cmd_gdbserver_stop() -> dict:
    # coarse stop for now
    _run(["bash", "-lc", "pkill -f JLinkGDBServer || true"])
    return {"ok": True}


def cmd_rtt_capture(device: str, serial: str, address: str, out_file: str, duration: int, speed: int,
                    gdb_port: int = 50000, rtt_port: int = 19021) -> dict:
    """Capture RTT for `duration` seconds via JLinkGDBServer + telnet socket.

    Why not JLinkRTTLogger: on J-Link Software V8.96 (Dec 2025) JLinkRTTLogger
    silently ignores ``-RTTAddress`` / ``-RTTSearchRanges`` and reports
    "RTT Control Block not found" even when the address is verifiably
    correct (confirmed via JLinkExe ``mem`` dump showing the "SEGGER RTT"
    magic at the requested address). JLinkGDBServer's ``-rtt
    -rttsearchaddr`` flag set goes through a different RTT implementation
    and honours the explicit address. We spin up a transient GDBServer,
    open the RTT telnet port, drain it into a file, then tear down.

    Side effect: kills any pre-existing JLinkGDBServer to free the port.
    Caller must not have a parallel GDB session — this is a capture, not
    a debug session.
    """
    _ensure_tool("JLinkGDBServer")
    out = Path(out_file).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Kill any stale GDBServer to free the gdb_port / rtt_port.
    _run(["bash", "-lc", "pkill -f JLinkGDBServer || true"])
    time.sleep(1.0)

    gdb_cmd = [
        "JLinkGDBServer",
        "-nogui",
        "-if", "swd",
        "-port", str(gdb_port),
        "-RTTTelnetPort", str(rtt_port),
        "-device", device,
        "-speed", str(speed),
        "-select", f"USB={serial}",
        "-rtt",
        "-rttsearchaddr", address,
        "-rttsearchranges", f"{address} 0x10000",
    ]
    gdb_proc = subprocess.Popen(gdb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        # Wait up to 5s for the RTT telnet port to accept connections.
        sock: socket.socket | None = None
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect(("localhost", rtt_port))
                break
            except (ConnectionRefusedError, socket.timeout, OSError):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                sock = None
                time.sleep(0.25)

        if sock is None:
            return {
                "ok": False,
                "error": f"GDBServer RTT telnet port {rtt_port} not reachable within 5s",
                "via": "gdbserver_telnet",
            }

        # Drain for `duration` seconds. Reconnect transparently if the
        # server closes the socket (rare, but happens after long idles).
        sock.settimeout(0.5)
        end = time.time() + duration
        with open(out, "wb", buffering=0) as f:
            while time.time() < end:
                try:
                    data = sock.recv(4096)
                    if not data:
                        try:
                            sock.close()
                        except OSError:
                            pass
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(0.5)
                            sock.connect(("localhost", rtt_port))
                        except OSError:
                            time.sleep(0.5)
                            continue
                        continue
                    f.write(data)
                except socket.timeout:
                    continue
                except OSError:
                    break
        try:
            sock.close()
        except OSError:
            pass

        return {
            "ok": out.exists() and out.stat().st_size > 0,
            "output_file": str(out),
            "bytes": out.stat().st_size if out.exists() else 0,
            "via": "gdbserver_telnet",
        }
    finally:
        if gdb_proc.poll() is None:
            gdb_proc.send_signal(signal.SIGTERM)
            try:
                gdb_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                gdb_proc.kill()


def cmd_gdb_batch(elf: str,
                  gdb: str,
                  gdb_port: int,
                  commands: list[str],
                  script_file: str | None,
                  timeout: int,
                  halt: bool) -> dict:
    """Run arm-none-eabi-gdb in batch mode against a running JLinkGDBServer.

    The gdb binary executes `target remote :<port>` first, then either:
      - the inline command list from --commands, or
      - the commands from the file passed via --script.
    Finally issues `quit` and returns the captured stdout/stderr.

    Use this for agent-driven breakpoint / step / variable inspection.
    The CPU is halted on `target remote`; pass --halt false only if your
    workflow needs to leave it running (rare).
    """
    _ensure_tool(gdb)
    elf_path = Path(elf).expanduser().resolve()
    if not elf_path.exists():
        raise JLinkError(f"elf not found: {elf_path}")

    cmdline: list[str] = [
        gdb,
        "-batch",
        "-nx",                              # ignore ~/.gdbinit
        "-ex", f"target remote :{gdb_port}",
    ]

    if halt:
        cmdline += ["-ex", "monitor halt"]

    if script_file:
        sp = Path(script_file).expanduser().resolve()
        if not sp.exists():
            raise JLinkError(f"gdb script not found: {sp}")
        cmdline += ["-x", str(sp)]
    else:
        for c in commands:
            cmdline += ["-ex", c]

    cmdline += ["-ex", "quit", str(elf_path)]

    try:
        proc = _run(cmdline, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "timeout": True,
            "error": f"gdb batch timed out after {timeout}s",
            "stdout": (e.stdout.decode(errors="ignore") if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or "")),
            "stderr": (e.stderr.decode(errors="ignore") if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or "")),
        }

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "cmdline": cmdline,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jlink-agent", description="Agent-friendly J-Link automation")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_json_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", help="print JSON output")

    sp = sub.add_parser("probe", help="list connected J-Link serial numbers")
    add_json_arg(sp)

    sp = sub.add_parser("flash", help="flash firmware with JLinkExe")
    add_json_arg(sp)
    sp.add_argument("--device", required=True)
    sp.add_argument("--serial", required=True)
    sp.add_argument("--firmware", required=True)
    sp.add_argument("--speed", type=int, default=12000)
    sp.add_argument("--jlinkscript",
        default="",
        help="JLinkScript whose InitTarget() inits FMC/SDRAM — required to flash the SDRAM UI-code segment (@0xD0400000). Empty = none (default).")

    sp = sub.add_parser("rtt-addr", help="read _SEGGER_RTT address from map file")
    add_json_arg(sp)
    sp.add_argument("--map", required=True)
    sp.add_argument("--symbol", default="_SEGGER_RTT")

    sp = sub.add_parser("gdbserver-start", help="start JLinkGDBServer")
    add_json_arg(sp)
    sp.add_argument("--device", required=True)
    sp.add_argument("--serial", required=True)
    sp.add_argument("--gdb-port", type=int, default=50000)
    sp.add_argument("--rtt-port", type=int, default=19021)
    sp.add_argument("--speed", type=int, default=12000)
    sp.add_argument("--foreground", action="store_true")

    sp = sub.add_parser("gdbserver-stop", help="stop JLinkGDBServer")
    add_json_arg(sp)

    sp = sub.add_parser("rtt-capture",
        help="capture RTT logs via GDBServer + telnet (workaround for broken JLinkRTTLogger -RTTAddress on V8.96+)")
    add_json_arg(sp)
    sp.add_argument("--device", required=True)
    sp.add_argument("--serial", required=True)
    sp.add_argument("--address", required=True,
        help="_SEGGER_RTT control-block address (resolve via `rtt-addr` from the map file)")
    sp.add_argument("--out", required=True)
    sp.add_argument("--duration", type=int, default=30)
    sp.add_argument("--speed", type=int, default=12000)
    sp.add_argument("--gdb-port", type=int, default=50000,
        help="port for the transient GDBServer (default 50000). Killed at end.")
    sp.add_argument("--rtt-port", type=int, default=19021,
        help="GDBServer's RTT telnet port (default 19021). The capture reads from here.")

    sp = sub.add_parser("gdb-batch",
        help="run gdb in batch mode against a running gdb server (breakpoints/step/print/regs)")
    add_json_arg(sp)
    sp.add_argument("--elf", required=True,
        help="path to the ELF with symbols")
    sp.add_argument("--gdb", default="arm-none-eabi-gdb",
        help="gdb binary (default: arm-none-eabi-gdb)")
    sp.add_argument("--gdb-port", type=int, default=50000,
        help="JLinkGDBServer port (must already be running)")
    sp.add_argument("--commands", nargs="*", default=[],
        help="inline gdb commands, each as a separate -ex. Mutually exclusive with --script")
    sp.add_argument("--script",
        help="path to a gdb command script (loaded via -x). Mutually exclusive with --commands")
    sp.add_argument("--timeout", type=int, default=60,
        help="kill gdb after N seconds (default 60)")
    sp.add_argument("--no-halt", dest="halt", action="store_false", default=True,
        help="skip the initial 'monitor halt' after connect")

    return p


def _emit(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for k, v in data.items():
            print(f"{k}: {v}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    as_json = bool(getattr(args, "json", False))

    try:
        if args.cmd == "probe":
            out = cmd_probe()
        elif args.cmd == "flash":
            out = cmd_flash(args.device, args.serial, args.firmware, args.speed, args.jlinkscript)
        elif args.cmd == "rtt-addr":
            out = cmd_rtt_addr(args.map, args.symbol)
        elif args.cmd == "gdbserver-start":
            out = cmd_gdbserver_start(args.device, args.serial, args.gdb_port, args.rtt_port, args.speed, args.foreground)
        elif args.cmd == "gdbserver-stop":
            out = cmd_gdbserver_stop()
        elif args.cmd == "rtt-capture":
            out = cmd_rtt_capture(args.device, args.serial, args.address, args.out, args.duration, args.speed,
                                  args.gdb_port, args.rtt_port)
        elif args.cmd == "gdb-batch":
            if args.commands and args.script:
                raise JLinkError("--commands and --script are mutually exclusive")
            out = cmd_gdb_batch(args.elf, args.gdb, args.gdb_port, args.commands, args.script, args.timeout, args.halt)
        else:
            parser.print_help()
            return 1

        _emit(out, as_json)
        return 0 if out.get("ok") else 2

    except JLinkError as e:
        _emit({"ok": False, "error": str(e)}, as_json)
        return 3
    except Exception as e:  # noqa: BLE001
        _emit({"ok": False, "error": f"unexpected: {e}"}, as_json)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
