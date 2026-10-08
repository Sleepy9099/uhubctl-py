"""High-level Python interface that drives the ``uhubctl`` binary."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .models import Action, ActionResult, Hub, Port
from .parser import parse_action, parse_status

ENV_BINARY = "UHUBCTL_PATH"


class UhubctlError(RuntimeError):
    """``uhubctl`` exited with an error."""

    def __init__(self, message: str, returncode: int | None = None, output: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.output = output


class UhubctlNotFoundError(UhubctlError, FileNotFoundError):
    """The ``uhubctl`` binary could not be located."""


class NoHubsFoundError(UhubctlError):
    """``uhubctl`` reported no compatible hubs (or lacked permission to see them)."""


def is_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _permission_hint() -> str:
    if is_wsl():
        return (
            " On WSL the hub must first be attached from Windows with "
            "`usbipd attach --wsl --busid <BUSID>`, and you need root or a udev rule."
        )
    if sys.platform.startswith("linux"):
        return " On Linux, run with sudo or install the udev rules from the uhubctl repo."
    if sys.platform == "win32":
        return " On Windows the hub needs the WinUSB driver (install it with Zadig)."
    return ""


def find_binary(path: str | os.PathLike[str] | None = None) -> str:
    """Locate ``uhubctl``: explicit path, then ``$UHUBCTL_PATH``, then ``PATH``."""
    candidates = [path, os.environ.get(ENV_BINARY)]
    for c in candidates:
        if c:
            p = Path(c).expanduser()
            if p.is_file():
                return str(p)
            raise UhubctlNotFoundError(f"uhubctl binary not found at {p}")
    found = shutil.which("uhubctl")
    if found:
        return found
    raise UhubctlNotFoundError(
        "uhubctl binary not found on PATH. Install it (e.g. `brew install uhubctl`, "
        f"`apt install uhubctl`) or set {ENV_BINARY}."
    )


def _ports_arg(ports: int | Iterable[int] | str | None) -> list[str]:
    if ports is None:
        return []
    if isinstance(ports, int):
        return ["-p", str(ports)]
    if isinstance(ports, str):
        return ["-p", ports]
    return ["-p", ",".join(str(p) for p in ports)]


class Uhubctl:
    """Control USB hub port power through the ``uhubctl`` binary.

    Args:
        binary: Path to ``uhubctl``. Defaults to ``$UHUBCTL_PATH`` or ``PATH``.
        sudo: Prefix commands with ``sudo`` (Linux/WSL without udev rules).
        timeout: Seconds to wait for each invocation.
        force: Pass ``-f`` to operate on hubs uhubctl does not consider smart.
        nodesc: Pass ``-N`` to skip querying device descriptions.
    """

    def __init__(
        self,
        binary: str | os.PathLike[str] | None = None,
        *,
        sudo: bool = False,
        timeout: float = 60.0,
        force: bool = False,
        nodesc: bool = False,
    ) -> None:
        self.binary = find_binary(binary)
        self.sudo = sudo
        self.timeout = timeout
        self.force = force
        self.nodesc = nodesc

    # -- low level -----------------------------------------------------------------

    def run(self, args: Sequence[str]) -> str:
        """Run uhubctl with raw ``args`` and return stdout."""
        cmd = [self.binary, *args]
        if self.force:
            cmd.append("-f")
        if self.nodesc:
            cmd.append("-N")
        if self.sudo:
            cmd = ["sudo", *cmd]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as e:
            raise UhubctlError(f"uhubctl timed out after {self.timeout}s: {cmd}") from e
        output = proc.stdout
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout).strip()
            if "No compatible devices detected" in err:
                raise NoHubsFoundError(err + _permission_hint(), proc.returncode, output)
            raise UhubctlError(err or f"uhubctl exited {proc.returncode}", proc.returncode, output)
        return output

    def version(self) -> str:
        return self.run(["-v"]).strip()

    # -- queries -------------------------------------------------------------------

    def hubs(
        self,
        location: str | None = None,
        *,
        vendor: str | None = None,
        search: str | None = None,
        search_hub: str | None = None,
        level: int | None = None,
        exact: bool = False,
    ) -> list[Hub]:
        """Return the status of all smart hubs, optionally filtered."""
        return parse_status(
            self.run(self._filter_args(location, None, vendor, search, search_hub, level, exact))
        )

    def hub(self, location: str) -> Hub:
        """Return the hub at exactly ``location``."""
        for h in self.hubs(location, exact=True):
            if h.location == location:
                return h
        raise NoHubsFoundError(f"no smart hub at location {location}")

    def find_device(self, text: str) -> list[tuple[Hub, Port]]:
        """Find ports whose attached device description contains ``text``."""
        needle = text.lower()
        return [
            (h, p)
            for h in self.hubs()
            for p in h.ports
            if p.device is not None and needle in str(p.device).lower()
        ]

    # -- actions -------------------------------------------------------------------

    def action(
        self,
        action: Action | int | str,
        location: str | None = None,
        ports: int | Iterable[int] | str | None = None,
        *,
        vendor: str | None = None,
        search: str | None = None,
        search_hub: str | None = None,
        level: int | None = None,
        exact: bool = False,
        delay: float | None = None,
        repeat: int | None = None,
        wait_ms: int | None = None,
        reset: bool = False,
    ) -> ActionResult:
        """Apply a power ``action`` and return before/after snapshots.

        uhubctl refuses to act on more than one physical hub at once, so pass a
        ``location`` (or a filter that narrows it to a single hub).
        """
        if isinstance(action, str):
            action = Action[action.upper()]
        args = ["-a", str(int(action))]
        args += self._filter_args(location, ports, vendor, search, search_hub, level, exact)
        if delay is not None:
            args += ["-d", str(delay)]
        if repeat is not None:
            args += ["-r", str(repeat)]
        if wait_ms is not None:
            args += ["-w", str(wait_ms)]
        if reset:
            args.append("-R")
        return parse_action(self.run(args))

    def off(self, location: str, ports: int | Iterable[int] | str | None = None, **kw: Any) -> ActionResult:
        return self.action(Action.OFF, location, ports, **kw)

    def on(self, location: str, ports: int | Iterable[int] | str | None = None, **kw: Any) -> ActionResult:
        return self.action(Action.ON, location, ports, **kw)

    def cycle(
        self, location: str, ports: int | Iterable[int] | str | None = None, *, delay: float = 2, **kw: Any
    ) -> ActionResult:
        return self.action(Action.CYCLE, location, ports, delay=delay, **kw)

    def toggle(
        self, location: str, ports: int | Iterable[int] | str | None = None, **kw: Any
    ) -> ActionResult:
        return self.action(Action.TOGGLE, location, ports, **kw)

    def flash(
        self, location: str, ports: int | Iterable[int] | str | None = None, *, delay: float = 2, **kw: Any
    ) -> ActionResult:
        return self.action(Action.FLASH, location, ports, delay=delay, **kw)

    @staticmethod
    def _filter_args(
        location: str | None,
        ports: int | Iterable[int] | str | None,
        vendor: str | None,
        search: str | None,
        search_hub: str | None,
        level: int | None,
        exact: bool,
    ) -> list[str]:
        args: list[str] = []
        if location:
            args += ["-l", location]
        args += _ports_arg(ports)
        if vendor:
            args += ["-n", vendor]
        if search:
            args += ["-s", search]
        if search_hub:
            args += ["-H", search_hub]
        if level is not None:
            args += ["-L", str(level)]
        if exact:
            args.append("-e")
        return args
