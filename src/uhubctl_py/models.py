"""Data models describing hubs, ports and attached devices."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Action(enum.IntEnum):
    """Power actions understood by ``uhubctl -a``."""

    OFF = 0
    ON = 1
    CYCLE = 2
    TOGGLE = 3
    FLASH = 4


@dataclass(frozen=True)
class Device:
    """A USB device as described by uhubctl (``vid:pid vendor product serial``)."""

    vid: str
    pid: str
    description: str
    """Free-form text after ``vid:pid`` (manufacturer, product, serial)."""
    vendor: str = ""
    product: str = ""
    serial: str = ""
    """``vendor``/``product``/``serial`` are only filled when uhubctl supports ``--json``;
    the text output cannot be split reliably."""

    @property
    def id(self) -> str:
        return f"{self.vid}:{self.pid}"

    def __str__(self) -> str:
        return f"{self.id} {self.description}".rstrip()


@dataclass(frozen=True)
class HubInfo(Device):
    """Descriptor information for a hub (a device that has ports)."""

    usb_version: str = ""
    num_ports: int = 0
    power_switching: str = ""
    """``ppps`` (per-port), ``ganged`` (all ports together) or ``nops`` (none)."""

    @property
    def is_usb3(self) -> bool:
        try:
            return float(self.usb_version) >= 3.0
        except ValueError:
            return False


@dataclass(frozen=True)
class Port:
    """State of one hub port."""

    number: int
    status: int
    """Raw ``wPortStatus`` bitfield as printed by uhubctl."""
    flags: tuple[str, ...]
    """Decoded flags, e.g. ``("power", "highspeed", "enable", "connect")``."""
    device: Device | HubInfo | None = None

    @property
    def is_powered(self) -> bool:
        return "off" not in self.flags and "power" in self.flags

    @property
    def is_connected(self) -> bool:
        return "connect" in self.flags


@dataclass(frozen=True)
class Hub:
    """Snapshot of a smart hub and its ports."""

    location: str
    """USB location such as ``1-1`` or ``3-1.4``; pass to ``-l``."""
    info: HubInfo
    ports: tuple[Port, ...] = field(default_factory=tuple)

    def port(self, number: int) -> Port:
        for p in self.ports:
            if p.number == number:
                return p
        raise KeyError(f"hub {self.location} has no port {number} in this snapshot")

    @property
    def description(self) -> str:
        return str(self.info)


@dataclass(frozen=True)
class ActionResult:
    """Parsed output of a power action.

    ``before`` and ``after`` each hold one snapshot per affected hub per step; a
    cycle produces two steps (off then on), so hubs may repeat.
    """

    before: tuple[Hub, ...]
    after: tuple[Hub, ...]
    raw: str
