"""Parse the human-readable output of the ``uhubctl`` binary."""

from __future__ import annotations

import re

from .models import ActionResult, Device, Hub, HubInfo, Port

_HUB_RE = re.compile(r"^(Current|New) status for hub (\S+) \[(.*)\]\s*$")
_PORT_RE = re.compile(r"^\s+Port (\d+): ([0-9a-fA-F]{4})((?: [^\[\s]+)*)(?: \[(.*)\])?\s*$")
_DESC_RE = re.compile(r"^([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s?(.*)$")
_HUB_TAIL_RE = re.compile(r", USB ([0-9a-fA-F]+\.[0-9a-fA-F]+), (\d+) ports, (ppps|ganged|nops)$")


def parse_description(text: str) -> Device | HubInfo:
    """Parse a bracketed device description such as ``154b:1009 PNY USB 2.0 FD``."""
    m = _DESC_RE.match(text.strip())
    if not m:
        return Device(vid="", pid="", description=text.strip())
    vid, pid, rest = m.group(1).lower(), m.group(2).lower(), m.group(3)
    tail = _HUB_TAIL_RE.search(rest)
    if tail:
        return HubInfo(
            vid=vid,
            pid=pid,
            description=rest[: tail.start()].strip(),
            usb_version=tail.group(1),
            num_ports=int(tail.group(2)),
            power_switching=tail.group(3),
        )
    return Device(vid=vid, pid=pid, description=rest.strip())


def _as_hub_info(dev: Device | HubInfo) -> HubInfo:
    if isinstance(dev, HubInfo):
        return dev
    return HubInfo(vid=dev.vid, pid=dev.pid, description=dev.description)


def _parse_blocks(output: str) -> list[tuple[str, Hub]]:
    """Return ``(kind, hub)`` pairs where kind is ``"Current"`` or ``"New"``."""
    blocks: list[tuple[str, str, HubInfo, list[Port]]] = []
    for line in output.splitlines():
        hub_m = _HUB_RE.match(line)
        if hub_m:
            info = _as_hub_info(parse_description(hub_m.group(3)))
            blocks.append((hub_m.group(1), hub_m.group(2), info, []))
            continue
        port_m = _PORT_RE.match(line)
        if port_m and blocks:
            desc = port_m.group(4)
            blocks[-1][3].append(
                Port(
                    number=int(port_m.group(1)),
                    status=int(port_m.group(2), 16),
                    flags=tuple(port_m.group(3).split()),
                    device=parse_description(desc) if desc else None,
                )
            )
    return [(kind, Hub(loc, info, tuple(ports))) for kind, loc, info, ports in blocks]


def parse_status(output: str) -> list[Hub]:
    """Parse the output of ``uhubctl`` run without an action."""
    return [hub for kind, hub in _parse_blocks(output) if kind == "Current"]


def parse_action(output: str) -> ActionResult:
    """Parse the output of ``uhubctl -a ...``."""
    blocks = _parse_blocks(output)
    return ActionResult(
        before=tuple(h for k, h in blocks if k == "Current"),
        after=tuple(h for k, h in blocks if k == "New"),
        raw=output,
    )
