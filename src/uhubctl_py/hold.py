"""Keep a device present on a port by power-cycling the port whenever it drops off.

Useful for devices that only enumerate briefly after power is applied, such as phones in a
boot ROM / download mode that time out and continue booting if nothing talks to them.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .client import Uhubctl, UhubctlError
from .models import Port


@dataclass(frozen=True)
class HoldEvent:
    kind: str
    """``present``, ``dropped``, ``power_off``, ``power_on``, ``timeout`` or ``error``."""
    elapsed: float
    """Seconds since :func:`hold` started."""
    detail: str = ""


def _matches(port: Port, device_id: str | None) -> bool:
    if not port.is_connected or port.device is None:
        return False
    return device_id is None or port.device.id == device_id.lower()


def hold(
    ctl: Uhubctl,
    location: str,
    port: int,
    device_id: str | None = None,
    *,
    off_time: float = 2.0,
    max_off_time: float = 15.0,
    off_step: float = 2.0,
    reset_off_time: bool = False,
    appear_timeout: float = 5.0,
    grace: float = 1.0,
    poll: float = 0.25,
    max_cycles: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[HoldEvent]:
    """Yield events while keeping ``device_id`` (``vid:pid``, or any device if None) on a port.

    When the device has been missing for ``grace`` seconds, the port is powered off and back
    on. The first power-off lasts ``off_time`` seconds; each time the device fails to appear
    within ``appear_timeout``, the next power-off is ``off_step`` longer, up to
    ``max_off_time``. Once the device appears, that off time is kept for later drops
    (or restarted from ``off_time`` if ``reset_off_time``). Stops after ``max_cycles`` cycles.
    """
    start = clock()
    cycles = 0
    current_off = off_time
    present = False
    missing_since: float | None = start
    waiting_since: float | None = None  # set after power on, until the device appears

    def ev(kind: str, detail: str = "") -> HoldEvent:
        return HoldEvent(kind, round(clock() - start, 2), detail)

    while True:
        try:
            p = ctl.hub(location).port(port)
        except (UhubctlError, KeyError) as e:
            yield ev("error", str(e))
            sleep(poll)
            continue

        now = clock()
        if _matches(p, device_id):
            if not present:
                yield ev("present", str(p.device) + (f" (off time {current_off:g}s)" if cycles else ""))
                if reset_off_time:
                    current_off = off_time
            present, missing_since, waiting_since = True, None, None
        else:
            if present:
                yield ev("dropped")
                present, missing_since = False, now
            if missing_since is None:
                missing_since = now
            if waiting_since is not None and now - waiting_since > appear_timeout:
                yield ev("timeout", f"not seen {appear_timeout:g}s after power on")
                current_off = min(current_off + off_step, max_off_time)
                waiting_since = None
                missing_since = now - grace  # cycle again right away
            if waiting_since is None and now - missing_since >= grace:
                if max_cycles is not None and cycles >= max_cycles:
                    return
                cycles += 1
                ctl.off(location, port)
                yield ev("power_off", f"cycle {cycles}, off for {current_off:g}s")
                sleep(current_off)
                ctl.on(location, port)
                yield ev("power_on", f"cycle {cycles}")
                waiting_since = clock()
        sleep(poll)
