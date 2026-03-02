#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
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
    proc = _run(["bash", "-lc", "JLinkExe -CommandFile /dev/stdin <<'EOF'\nShowEmuList\nexit\nEOF"])
    raw = (proc.stdout or "") + (proc.stderr or "")
    sns = sorted(set(re.findall(r"\b\d{9}\b", raw)))
    return {"ok": True, "serial_numbers": sns, "raw": raw}


def cmd_flash(device: str, serial: str, firmware: str, speed: int) -> dict:
    _ensure_tool("JLinkExe")
    fw = Path(firmware).expanduser().resolve()
    if not fw.exists():
        raise JLinkError(f"firmware not found: {fw}")

    script = f"r\nh\nloadfile {fw}\nr\ng\nexit\n"
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(script)
        script_path = tf.name

    try:
        proc = _run([
            "JLinkExe",
            "-device", device,
            "-if", "SWD",
            "-speed", str(speed),
            "-USB", serial,
            "-AutoConnect", "1",
            "-CommandFile", script_path,
        ], timeout=120)
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


def cmd_rtt_capture(device: str, serial: str, address: str, out_file: str, duration: int, speed: int) -> dict:
    _ensure_tool("JLinkRTTLogger")
    out = Path(out_file).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "JLinkRTTLogger",
        "-Device", device,
        "-If", "SWD",
        "-Speed", str(speed),
        "-SelectEmuBySN", serial,
        "-RTTChannel", "0",
        "-RTTAddress", address,
        str(out),
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(max(1, duration))
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    return {"ok": out.exists(), "output_file": str(out), "bytes": out.stat().st_size if out.exists() else 0}


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
    sp.add_argument("--speed", type=int, default=4000)

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

    sp = sub.add_parser("rtt-capture", help="capture RTT logs via JLinkRTTLogger")
    add_json_arg(sp)
    sp.add_argument("--device", required=True)
    sp.add_argument("--serial", required=True)
    sp.add_argument("--address", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--duration", type=int, default=30)
    sp.add_argument("--speed", type=int, default=12000)

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
            out = cmd_flash(args.device, args.serial, args.firmware, args.speed)
        elif args.cmd == "rtt-addr":
            out = cmd_rtt_addr(args.map, args.symbol)
        elif args.cmd == "gdbserver-start":
            out = cmd_gdbserver_start(args.device, args.serial, args.gdb_port, args.rtt_port, args.speed, args.foreground)
        elif args.cmd == "gdbserver-stop":
            out = cmd_gdbserver_stop()
        elif args.cmd == "rtt-capture":
            out = cmd_rtt_capture(args.device, args.serial, args.address, args.out, args.duration, args.speed)
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
