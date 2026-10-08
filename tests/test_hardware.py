"""Tests against a real hub. Enable with UHUBCTL_HW=1 (and optionally UHUBCTL_HW_LOCATION/PORT).

They toggle power on one port, so point them at a port with nothing important attached.
"""

import os

import pytest

from uhubctl_py import Uhubctl

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(os.environ.get("UHUBCTL_HW") != "1", reason="set UHUBCTL_HW=1 to run"),
]


@pytest.fixture(scope="module")
def ctl():
    return Uhubctl(sudo=os.environ.get("UHUBCTL_SUDO") == "1")


@pytest.fixture(scope="module")
def target(ctl):
    loc = os.environ.get("UHUBCTL_HW_LOCATION")
    port = int(os.environ.get("UHUBCTL_HW_PORT", "1"))
    if not loc:
        loc = next(h.location for h in ctl.hubs() if h.info.power_switching == "ppps")
    return loc, port


def test_lists_hubs(ctl):
    assert ctl.hubs()


def test_off_then_on(ctl, target):
    loc, port = target
    try:
        off = ctl.off(loc, port)
        assert not any(h.port(port).is_powered for h in off.after if h.location == loc)
    finally:
        on = ctl.on(loc, port)
    assert all(h.port(port).is_powered for h in on.after if h.location == loc)
