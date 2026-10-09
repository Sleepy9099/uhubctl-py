from uhubctl_py import Device, Hub, HubInfo, Port
from uhubctl_py.hold import hold

PHONE = Device("1782", "4d00", "")


class FakeHub:
    """Simulated port: the device is present for `stay` polls after each power on."""

    def __init__(self, stay=3, appear_after=1):
        self.stay, self.appear_after = stay, appear_after
        self.powered, self.polls_since_on, self.calls = True, 0, []

    def hub(self, location):
        self.polls_since_on += 1
        n = self.polls_since_on
        present = self.powered and self.appear_after <= n < self.appear_after + self.stay
        port = Port(
            1,
            0x103 if present else 0x100,
            ("power", "connect") if present else ("power",),
            PHONE if present else None,
        )
        return Hub(location, HubInfo("2109", "2817", ""), (port,))

    def off(self, location, port):
        self.calls.append("off")
        self.powered = False

    def on(self, location, port):
        self.calls.append("on")
        self.powered, self.polls_since_on = True, 0


def run(fake, **kw):
    t = [0.0]

    def sleep(s):
        t[0] += s

    return list(hold(fake, "1-1.3", 1, "1782:4d00", sleep=sleep, clock=lambda: t[0], **kw))


def test_cycles_after_device_drops():
    fake = FakeHub(stay=3)
    fake.polls_since_on = 0
    events = run(fake, max_cycles=2, grace=0.5, poll=0.25)
    kinds = [e.kind for e in events]
    assert kinds[:4] == ["present", "dropped", "power_off", "power_on"]
    assert kinds.count("present") == 3  # initial + after each of 2 cycles
    assert fake.calls == ["off", "on", "off", "on"]


def test_retries_when_device_never_appears():
    fake = FakeHub(stay=0)
    events = run(fake, max_cycles=2, grace=0.5, appear_timeout=2, off_time=1)
    kinds = [e.kind for e in events]
    assert "present" not in kinds
    assert kinds.count("timeout") == 2 and fake.calls == ["off", "on", "off", "on"]


def test_off_time_grows_until_device_appears():
    class NeedsLongOff(FakeHub):
        """Device only comes back if power was off for at least 5 s."""

        def __init__(self):
            super().__init__(stay=3)
            self.t = None

        def off(self, location, port):
            super().off(location, port)
            self.off_at = clock[0]

        def on(self, location, port):
            super().on(location, port)
            if clock[0] - self.off_at < 5:
                self.stay = 0
            else:
                self.stay = 3

    clock = [0.0]

    def sleep(s):
        clock[0] += s

    fake = NeedsLongOff()
    events = list(
        hold(
            fake,
            "1-1.3",
            1,
            "1782:4d00",
            off_time=1,
            off_step=2,
            max_off_time=6,
            appear_timeout=2,
            grace=0.5,
            max_cycles=3,
            sleep=sleep,
            clock=lambda: clock[0],
        )
    )
    offs = [e.detail for e in events if e.kind == "power_off"]
    assert offs == ["cycle 1, off for 1s", "cycle 2, off for 3s", "cycle 3, off for 5s"]
    assert events[-1].kind == "present" or any(
        e.kind == "present" and "off time 5s" in e.detail for e in events
    )
