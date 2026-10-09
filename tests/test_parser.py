from pathlib import Path

from uhubctl_py import HubInfo, parse_action, parse_description, parse_json, parse_status

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_status_parses_all_hubs():
    hubs = parse_status(read("macos_via_status.txt"))
    assert [h.location for h in hubs] == ["1-1.3", "1-2.3", "1-1", "1-2"]
    assert all(len(h.ports) == 4 for h in hubs)


def test_hub_info():
    hub = parse_status(read("macos_via_status.txt"))[2]
    assert hub.info.id == "2109:2817"
    assert hub.info.description == "VIA Labs, Inc. USB2.0 Hub"
    assert hub.info.usb_version == "2.10"
    assert hub.info.num_ports == 4
    assert hub.info.power_switching == "ppps"
    assert not hub.info.is_usb3


def test_ports_and_devices():
    hub = {h.location: h for h in parse_status(read("macos_via_status.txt"))}["1-1"]
    p4 = hub.port(4)
    assert p4.status == 0x0503
    assert p4.flags == ("power", "highspeed", "enable", "connect")
    assert p4.is_powered and p4.is_connected
    assert p4.device is not None and p4.device.id == "154b:1009"
    assert "PNY" in p4.device.description
    # A cascaded hub is reported with hub info.
    assert isinstance(hub.port(3).device, HubInfo)
    assert not hub.port(1).is_connected


def test_usb3_flags():
    hub = {h.location: h for h in parse_status(read("macos_via_status.txt"))}["1-2"]
    assert hub.info.is_usb3
    assert hub.port(1).flags == ("power", "5gbps", "Rx.Detect")
    assert hub.port(3).is_connected


def test_action_off_handles_usb3_twin():
    result = parse_action(read("macos_via_off.txt"))
    assert [h.location for h in result.before] == ["1-1", "1-2"]
    assert [h.location for h in result.after] == ["1-1", "1-2"]
    assert all(h.ports[0].is_powered for h in result.before)
    assert not any(h.ports[0].is_powered for h in result.after)
    assert result.after[0].ports[0].status == 0


def test_action_on():
    result = parse_action(read("macos_via_on.txt"))
    assert all(h.port(1).is_powered for h in result.after)


def test_non_hub_description_without_strings():
    d = parse_description("0bda:8153")
    assert d.id == "0bda:8153" and d.description == ""


def test_ganged_hub_description():
    d = parse_description("05e3:0610 GenesysLogic USB2.1 Hub, USB 2.10, 4 ports, ganged")
    assert isinstance(d, HubInfo) and d.power_switching == "ganged"


def _without_strings(hub):
    """Text output can't split vendor/product/serial, so compare without them."""
    from dataclasses import replace

    def strip(d):
        return d and replace(d, vendor="", product="", serial="")

    return replace(
        hub,
        info=strip(hub.info),
        ports=tuple(replace(p, device=strip(p.device)) for p in hub.ports),
    )


def test_json_matches_text():
    text_hubs = parse_status(read("macos_via_pair.txt"))
    json_hubs = parse_json(read("macos_via_pair.json")).before
    assert [_without_strings(h) for h in json_hubs] == text_hubs


def test_json_device_strings():
    hub = parse_json(read("macos_via_pair.json")).before[0]
    assert hub.info.vendor == "VIA Labs, Inc."
    assert hub.info.product.endswith("Hub")


def test_json_cycle_steps():
    result = parse_json(read("macos_via_cycle.json"))
    assert {h.location for h in result.before} == {"1-1", "1-2"}
    # off step then on step, each covering the USB2 and USB3 twins
    assert len(result.after) == 4
    assert not any(h.port(1).is_powered for h in result.after[:2])
    assert all(h.port(1).is_powered for h in result.after[2:])
