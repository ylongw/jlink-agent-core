from __future__ import annotations

import argparse
import json
import sys

from .jlink import (
    JLinkError,
    capture_rtt,
    flash,
    probe,
    read_rtt_address,
    start_gdbserver,
    stop_gdbserver,
)


def _print(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for k, v in data.items():
            print(f"{k}: {v}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jlink-agent", description="Agent-friendly J-Link automation")
    p.add_argument("--json", action="store_true", help="print JSON output")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_json_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", help="print JSON output")

    sp_probe = sub.add_parser("probe", help="list connected J-Link serial numbers")
    add_json_arg(sp_probe)

    sp_flash = sub.add_parser("flash", help="flash firmware with JLinkExe")
    add_json_arg(sp_flash)
    sp_flash.add_argument("--device", required=True)
    sp_flash.add_argument("--serial", required=True)
    sp_flash.add_argument("--firmware", required=True)
    sp_flash.add_argument("--speed", type=int, default=4000)

    sp_addr = sub.add_parser("rtt-addr", help="read _SEGGER_RTT address from map file")
    add_json_arg(sp_addr)
    sp_addr.add_argument("--map", required=True)
    sp_addr.add_argument("--symbol", default="_SEGGER_RTT")

    sp_gdbs = sub.add_parser("gdbserver-start", help="start JLinkGDBServer")
    add_json_arg(sp_gdbs)
    sp_gdbs.add_argument("--device", required=True)
    sp_gdbs.add_argument("--serial", required=True)
    sp_gdbs.add_argument("--gdb-port", type=int, default=50000)
    sp_gdbs.add_argument("--rtt-port", type=int, default=19021)
    sp_gdbs.add_argument("--speed", type=int, default=12000)
    sp_gdbs.add_argument("--foreground", action="store_true")

    sp_gdbstop = sub.add_parser("gdbserver-stop", help="stop JLinkGDBServer")
    add_json_arg(sp_gdbstop)

    sp_rtt = sub.add_parser("rtt-capture", help="capture RTT logs via JLinkRTTLogger")
    add_json_arg(sp_rtt)
    sp_rtt.add_argument("--device", required=True)
    sp_rtt.add_argument("--serial", required=True)
    sp_rtt.add_argument("--address", required=True)
    sp_rtt.add_argument("--out", required=True)
    sp_rtt.add_argument("--duration", type=int, default=30)
    sp_rtt.add_argument("--speed", type=int, default=12000)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    as_json = bool(getattr(args, "json", False))

    try:
        if args.cmd == "probe":
            r = probe()
            _print({"ok": True, "serial_numbers": r.serial_numbers, "raw": r.raw}, as_json)
            return 0

        if args.cmd == "flash":
            out = flash(device=args.device, serial=args.serial, firmware=args.firmware, speed=args.speed)
            _print(out, as_json)
            return 0 if out.get("ok") else 2

        if args.cmd == "rtt-addr":
            addr = read_rtt_address(args.map, symbol=args.symbol)
            _print({"ok": True, "address": addr}, as_json)
            return 0

        if args.cmd == "gdbserver-start":
            out = start_gdbserver(
                device=args.device,
                serial=args.serial,
                gdb_port=args.gdb_port,
                rtt_port=args.rtt_port,
                speed=args.speed,
                background=not args.foreground,
            )
            _print(out, as_json)
            return 0 if out.get("ok") else 2

        if args.cmd == "gdbserver-stop":
            out = stop_gdbserver()
            _print(out, as_json)
            return 0 if out.get("ok") else 2

        if args.cmd == "rtt-capture":
            out = capture_rtt(
                device=args.device,
                serial=args.serial,
                address=args.address,
                out_file=args.out,
                duration_sec=args.duration,
                speed=args.speed,
            )
            _print(out, as_json)
            return 0 if out.get("ok") else 2

        parser.print_help()
        return 1

    except JLinkError as e:
        _print({"ok": False, "error": str(e)}, as_json)
        return 3
    except Exception as e:  # noqa: BLE001
        _print({"ok": False, "error": f"unexpected: {e}"}, as_json)
        return 4


if __name__ == "__main__":
    sys.exit(main())
