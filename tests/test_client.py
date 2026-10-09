import subprocess
from pathlib import Path

import pytest

from uhubctl_py import NoHubsFoundError, Uhubctl, UhubctlNotFoundError, cli

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """A Uhubctl whose subprocess calls are recorded and answered from fixtures."""
    binary = tmp_path / "uhubctl"
    binary.write_text("")
    monkeypatch.setenv("UHUBCTL_PATH", str(binary))
    calls = []
    replies = {"stdout": (FIXTURES / "macos_via_status.txt").read_text(), "rc": 0, "stderr": ""}

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, replies["rc"], replies["stdout"], replies["stderr"])

    monkeypatch.setattr(subprocess, "run", run)
    return Uhubctl(), calls, replies


def test_missing_binary(monkeypatch):
    monkeypatch.setenv("UHUBCTL_PATH", "/nonexistent/uhubctl")
    with pytest.raises(UhubctlNotFoundError):
        Uhubctl()


def test_action_args(fake):
    ctl, calls, replies = fake
    replies["stdout"] = (FIXTURES / "macos_via_off.txt").read_text()
    result = ctl.off("1-1", [1, 3], exact=True)
    assert calls[-1][1:] == ["-a", "0", "-l", "1-1", "-p", "1,3", "-e"]
    assert not result.after[0].port(1).is_powered


def test_cycle_args(fake):
    ctl, calls, _ = fake
    ctl.cycle("1-1", "2", delay=0.5, reset=True)
    assert calls[-1][1:] == ["-a", "2", "-l", "1-1", "-p", "2", "-d", "0.5", "-R"]


def test_sudo_and_flags(fake):
    ctl, calls, _ = fake
    ctl.sudo, ctl.force, ctl.nodesc = True, True, True
    ctl.hubs()
    assert calls[-1][0] == "sudo" and calls[-1][-2:] == ["-f", "-N"]


def test_find_device(fake):
    ctl, _, _ = fake
    [(hub, port)] = ctl.find_device("pny")
    assert (hub.location, port.number) == ("1-1", 4)


def test_no_hubs(fake):
    ctl, _, replies = fake
    replies.update(rc=1, stdout="", stderr="No compatible devices detected at location 9-9!\n")
    with pytest.raises(NoHubsFoundError):
        ctl.hubs("9-9")


def test_cli_json(fake, capsys):
    assert cli.main(["--json", "list"]) == 0
    assert '"location": "1-1"' in capsys.readouterr().out


def test_json_mode_args_and_parse(fake):
    ctl, calls, replies = fake
    ctl.json = True
    replies["stdout"] = (FIXTURES / "macos_via_cycle.json").read_text()
    result = ctl.cycle("1-1", 1, delay=0.3)
    assert calls[-1][1:] == ["-a", "2", "-l", "1-1", "-p", "1", "-d", "0.3", "-j"]
    assert len(result.after) == 4


def test_json_autodetect(fake):
    ctl, calls, replies = fake
    replies["stdout"] = "--json,     -j - print status as JSON.\n"
    assert ctl.supports_json
    ctl2 = Uhubctl()
    replies["stdout"] = "usage without it"
    assert not ctl2.supports_json
