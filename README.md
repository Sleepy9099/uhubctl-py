# uhubctl-py

A typed Python control layer for [uhubctl](https://github.com/mvp/uhubctl): turn power on and off for
individual ports on supported USB hubs from Python or the command line, on macOS, Linux, Windows, and WSL.

The C `uhubctl` binary does the USB work. This package runs it, parses its output into dataclasses, and
adds a scripting-friendly CLI with JSON output. It has no runtime dependencies.

## Install

1. Install the `uhubctl` binary:

   | Platform | Command |
   |---|---|
   | macOS | `brew install uhubctl` (or build from source, see [docs/PLATFORMS.md](docs/PLATFORMS.md)) |
   | Debian/Ubuntu/WSL | `sudo apt install uhubctl` |
   | Windows | build with MSYS2, see [docs/PLATFORMS.md](docs/PLATFORMS.md) |

   If it is not on `PATH`, set `UHUBCTL_PATH=/path/to/uhubctl`.

   Stock uhubctl works. The fork at [Sleepy9099/uhubctl](https://github.com/Sleepy9099/uhubctl) adds
   `--json` output and a non-zero exit status when a port fails to switch. uhubctl-py detects `--json`
   and uses it automatically, which also fills `Device.vendor`, `.product` and `.serial`. CI for the fork
   publishes a ready-to-use Windows build (`uhubctl-windows-x64`) as an artifact.

2. Install this package:

   ```bash
   pip install git+https://github.com/Sleepy9099/uhubctl-py
   ```

## Python usage

```python
from uhubctl_py import Uhubctl

ctl = Uhubctl()  # Uhubctl(sudo=True) on Linux without udev rules

for hub in ctl.hubs():
    print(hub.location, hub.info.description, hub.info.power_switching)
    for port in hub.ports:
        print("  ", port.number, "on" if port.is_powered else "off", port.device or "")

ctl.off("1-1", ports=[1, 2])  # power off ports 1 and 2
ctl.on("1-1", ports=1)
ctl.cycle("1-1", ports=4, delay=3)  # off, wait 3 s, on
ctl.toggle("1-1")  # every port on the hub

# Find where a device is plugged in, then power-cycle just that port
[(hub, port)] = ctl.find_device("PNY")
result = ctl.cycle(hub.location, port.number)
print(result.after[-1].port(port.number).is_powered)
```

Every action returns an `ActionResult` with `before`/`after` snapshots of each affected hub.
For USB 3 hubs, uhubctl switches the paired USB 2 and USB 3 hubs together. Pass `exact=True`
to switch only the location you name.

## CLI

```text
uhubctl-py                       # list hubs and ports
uhubctl-py --json list           # machine-readable output
uhubctl-py find PNY              # which hub/port is a device on?
uhubctl-py off 1-1 -p 1,2
uhubctl-py on 1-1 -p 1
uhubctl-py cycle 1-1 -p 4 -d 3
uhubctl-py toggle 1-1
uhubctl-py --sudo off 3-1 -p 2   # Linux/WSL without udev rules
```

`python -m uhubctl_py` works too.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                    # unit tests use captured uhubctl output; no hardware needed
ruff check . && mypy
UHUBCTL_HW=1 UHUBCTL_HW_LOCATION=1-1 UHUBCTL_HW_PORT=1 pytest -m hardware   # toggles a real port
```

To add support for new output, capture it with `uhubctl > tests/fixtures/<name>.txt` and add a test.

## License

MIT for this wrapper. `uhubctl` itself is GPL-2.0 and is run as a separate program, not bundled.
