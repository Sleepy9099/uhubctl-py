"""``uhubctl-py`` command line: friendlier output and JSON for scripting."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections.abc import Sequence

from . import __version__
from .client import Uhubctl, UhubctlError
from .hold import hold
from .models import Action, Hub


def _to_json(obj: object) -> str:
    def default(o: object) -> object:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        raise TypeError(type(o).__name__)

    return json.dumps(obj, default=default, indent=2)


def _print_hubs(hubs: Sequence[Hub]) -> None:
    for hub in hubs:
        info = hub.info
        print(
            f"{hub.location}  {info.id} {info.description}  (USB {info.usb_version}, {info.power_switching})"
        )
        for p in hub.ports:
            state = "on" if p.is_powered else "off"
            dev = f"  {p.device}" if p.device else ""
            print(f"  port {p.number}: {state:<3}{dev}".rstrip())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="uhubctl-py", description=__doc__)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--binary", help="path to uhubctl (default: $UHUBCTL_PATH or PATH)")
    ap.add_argument("--sudo", action="store_true", help="run uhubctl via sudo")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    sub = ap.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="show hubs and port state (default)")
    ls.add_argument("-l", "--location")

    find = sub.add_parser("find", help="find ports whose device matches TEXT")
    find.add_argument("text")

    for a in Action:
        p = sub.add_parser(a.name.lower(), help=f"power {a.name.lower()} ports")
        p.add_argument("location", help="hub location, e.g. 1-1")
        p.add_argument("-p", "--ports", help="ports, e.g. 1,3 or 1-4 (default: all)")
        if a in (Action.CYCLE, Action.FLASH):
            p.add_argument("-d", "--delay", type=float, default=2.0)
        p.add_argument("-e", "--exact", action="store_true", help="no USB2/USB3 twin handling")
        p.add_argument("-R", "--reset", action="store_true", help="reset hub after power on")

    h = sub.add_parser("hold", help="power-cycle a port whenever its device drops off (Ctrl-C to stop)")
    h.add_argument("location", help="hub location, e.g. 1-1.3")
    h.add_argument("-p", "--port", type=int, required=True)
    h.add_argument("--device", help="vid:pid to wait for, e.g. 1782:4d00 (default: any device)")
    h.add_argument("--off-time", type=float, default=2.0, help="first power-off duration, seconds [2]")
    h.add_argument("--off-step", type=float, default=2.0, help="added to off time after each miss [2]")
    h.add_argument("--max-off-time", type=float, default=15.0, help="longest power-off, seconds [15]")
    h.add_argument("--reset-off-time", action="store_true", help="restart from --off-time after each success")
    h.add_argument("--appear-timeout", type=float, default=5.0, help="seconds to wait after power on [5]")
    h.add_argument("--grace", type=float, default=1.0, help="seconds missing before cycling [1]")
    h.add_argument("--max-cycles", type=int, help="stop after this many power cycles")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ctl = Uhubctl(args.binary, sudo=args.sudo)
        if args.cmd in (None, "list"):
            hubs = ctl.hubs(getattr(args, "location", None))
            if args.json:
                print(_to_json(hubs))
            else:
                _print_hubs(hubs)
        elif args.cmd == "hold":
            events = hold(
                ctl,
                args.location,
                args.port,
                args.device,
                off_time=args.off_time,
                off_step=args.off_step,
                max_off_time=args.max_off_time,
                reset_off_time=args.reset_off_time,
                appear_timeout=args.appear_timeout,
                grace=args.grace,
                max_cycles=args.max_cycles,
            )
            try:
                for e in events:
                    if args.json:
                        print(json.dumps(dataclasses.asdict(e)), flush=True)
                    else:
                        print(
                            f"{time.strftime('%H:%M:%S')} +{e.elapsed:7.2f}s {e.kind:9} {e.detail}",
                            flush=True,
                        )
            except KeyboardInterrupt:
                pass
        elif args.cmd == "find":
            matches = ctl.find_device(args.text)
            if args.json:
                print(
                    _to_json([{"hub": h.location, "port": p.number, "device": p.device} for h, p in matches])
                )
            else:
                for h, p in matches:
                    print(f"{h.location} port {p.number}: {p.device}")
            return 0 if matches else 1
        else:
            result = ctl.action(
                Action[args.cmd.upper()],
                args.location,
                args.ports,
                exact=args.exact,
                reset=args.reset,
                delay=getattr(args, "delay", None),
            )
            if args.json:
                print(_to_json({"before": result.before, "after": result.after}))
            else:
                # A cycle reports an off step and an on step; show the final state per hub.
                _print_hubs(list({h.location: h for h in result.after}.values()))
    except UhubctlError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
