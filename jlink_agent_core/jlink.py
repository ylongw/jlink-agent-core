from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class JLinkError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc


def _ensure_tool(tool: str) -> None:
    if subprocess.run(["bash", "-lc", f"command -v {tool}"], capture_output=True).returncode != 0:
        raise JLinkError(f"missing required tool: {tool}")


@dataclass
class JLinkProbeResult:
    serial_numbers: list[str]
    raw: str


def probe() -> JLinkProbeResult:
    _ensure_tool("JLinkExe")
    cmd = ["bash", "-lc", "JLinkExe -CommandFile /dev/stdin <<'EOF'\nShowEmuList\nexit\nEOF"]
    proc = _run(cmd)
    raw = (proc.stdout or "") + (proc.stderr or "")
    sns = sorted(set(re.findall(r"\b\d{9}\b", raw)))
    return JLinkProbeResult(serial_numbers=sns, raw=raw)


def flash(*, device: str, serial: str, firmware: str, speed: int = 4000) -> dict[str, Any]:
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


def read_rtt_address(map_file: str, symbol: str = "_SEGGER_RTT") -> str:
    m = Path(map_file).expanduser().resolve()
    if not m.exists():
        raise JLinkError(f"map file not found: {m}")

    for line in m.read_text(errors="ignore").splitlines():
        if line.rstrip().endswith(symbol):
            addr = line.strip().split()[0].lower().replace("0x", "")
            return f"0x{addr}"
    raise JLinkError(f"symbol not found: {symbol}")


def start_gdbserver(*, device: str, serial: str, gdb_port: int, rtt_port: int, speed: int = 12000, background: bool = True) -> dict[str, Any]:
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

    if background:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)
        return {"ok": proc.poll() is None, "pid": proc.pid, "cmd": cmd}

    proc = _run(cmd)
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": (proc.stdout or "") + (proc.stderr or "")}


def stop_gdbserver(serial: str | None = None, port: int | None = None) -> dict[str, Any]:
    # Keep it simple/portable for now: kill all JLinkGDBServer.
    # Optional filters can be added by scanning process cmdline later.
    proc = _run(["bash", "-lc", "pkill -f JLinkGDBServer || true"])
    return {"ok": proc.returncode == 0}


def capture_rtt(*, device: str, serial: str, address: str, out_file: str, duration_sec: int = 30, speed: int = 12000) -> dict[str, Any]:
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
        time.sleep(max(1, duration_sec))
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    return {
        "ok": out.exists(),
        "output_file": str(out),
        "bytes": out.stat().st_size if out.exists() else 0,
    }
