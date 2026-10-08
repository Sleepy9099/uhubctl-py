# Platform setup

uhubctl-py needs a working `uhubctl` binary that can see the hub. Check it with `uhubctl` before you
debug anything in Python.

## macOS (tested: Apple Silicon, VIA Labs 2109:2817 / 2109:0817 hub)

```bash
brew install uhubctl
# or build the latest source:
brew install libusb pkg-config
git clone https://github.com/mvp/uhubctl && cd uhubctl && make
export UHUBCTL_PATH=$PWD/uhubctl
```

You don't need sudo. Port switching on hubs connected through a Thunderbolt/USB-C dock can be
unreliable; plug the hub directly into the Mac if ports don't turn off.

## Linux

```bash
sudo apt install uhubctl      # or build from source with libusb-1.0-0-dev
```

Without root, uhubctl reports "No compatible devices detected". Install the udev rules from the
uhubctl repo (`udev/rules.d/52-usb.rules`), add yourself to the `dialout` group, and replug the hub.
You can also use `Uhubctl(sudo=True)` / `uhubctl-py --sudo`.

## Windows (native)

uhubctl uses libusb, which on Windows can only control a hub after the hub's driver is replaced with
**WinUSB**:

1. Build uhubctl in an [MSYS2](https://www.msys2.org/) UCRT64 shell:
   ```bash
   pacman -S --needed git make mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-libusb mingw-w64-ucrt-x86_64-pkgconf
   git clone https://github.com/mvp/uhubctl && cd uhubctl && make
   ```
   Copy `uhubctl.exe` and `libusb-1.0.dll` (from `/ucrt64/bin`) to the same folder and set
   `UHUBCTL_PATH` to the exe.
2. Use [Zadig](https://zadig.akeo.ie/) (Options → List All Devices) to install WinUSB for the hub.
   This takes the hub away from the Windows hub driver: devices plugged into it stop working on that
   machine until you roll the driver back in Device Manager. Many users prefer the WSL route below.

This setup has not been tested yet. Results will go here once it is verified on hardware.

## WSL 2

WSL can't see host USB devices by default. Forward the hub with
[usbipd-win](https://github.com/dorssel/usbipd-win):

```powershell
# Windows, admin PowerShell
winget install usbipd
usbipd list                          # find the hub's BUSID (e.g. 2-3)
usbipd bind --busid 2-3
usbipd attach --wsl --busid 2-3
```

```bash
# Inside WSL
sudo apt install uhubctl
sudo uhubctl
```

Hub port-power requests over USB/IP depend on the usbipd version and the hub. When this route is
verified, the results will be recorded here.
