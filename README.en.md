# RubikPi3 Ubuntu support package

[简体中文](README.md) | **English**

One `rubikpi3-ubuntu-support_0.2.2_arm64.deb` integrates the tested kernel patches,
firmware, board-local DT generation, module parameters, initramfs and GRUB logic.
Building does not need EDK2 sources or binaries.
See [PATCHES.en.md](PATCHES.en.md) for the firmware/OS split.

Scope: **Ubuntu 26.04 ARM64, 7.0.0-38-generic, RubikPi3, EL2/VHE**, with
edk2-flange UEFI, symbol-bearing board FDT and Secure Boot disabled.
The firmware must report `flange,display-fixup-version = <1>` or newer.
Upgrade older firmware and reboot first; installation rejects firmware that cannot
fill the boot framebuffer template correctly.
This is not a generic package for arbitrary Ubuntu/kernel/firmware versions.
It does not flash firmware, change TrustZone, repartition storage or reboot.

## Contents and build

The package contains MSM EL2 SECVID, board-specific DPU mixer allocation and
LT9611 port-B/blanking DKMS patches; native HDMI
and Venus EL2 DT helpers; AP6256 firmware/CLM/NVRAM with the sample MAC removed;
verified Renesas USB firmware; initramfs hooks and automatic standard Ubuntu boot configuration.
Venus and brcmfmac remain distribution drivers; GPU userspace remains Mesa.
The four components and their records are under `components/`, with individual build tools.
Only their payloads are merged, not nested debs or their maintainer scripts.

Build on x86_64 or ARM64 with Python 3.11+, dpkg-deb, patch, bzip2 support and
the system GPL-2 license text. Modules compile on the target during installation.

```sh
python3 build-package.py /path/to/linux-source-7.0.0_7.0.0-38.38_all.deb \
  --wifi-firmware /path/to/vendor-wifi \
  --usb-firmware /path/to/renesas_usb_fw.mem \
  --output dist
```

Inputs are pinned by SHA256. Obtain the three original Wi-Fi files as described
in the [Wi-Fi guide](components/rubikpi3-wifi-firmware/README.en.md), and Renesas
firmware from this board's `usb_fw` partition or its validated installed copy.
The build is offline and outputs one deb plus a checksum. It contains vendor
firmware for local installation: the original downloads do not provide explicit
redistribution permission. Confirm firmware rights before publishing binaries;
the scripts' GPL does not relicense firmware. See [copyright](copyright).
No board-specific DTB, MAC, EFI address, credentials or SSH setup is shipped.

## Install and verify

Boot the target into Ubuntu kernel `7.0.0-38-generic`, then:

```sh
sudo apt install ./dist/rubikpi3-ubuntu-support_0.2.2_arm64.deb
sudo rubikpi3-support status
sudo reboot
```

APT resolves the pinned kernel/headers, DKMS, Ubuntu Qualcomm graphics firmware,
Mesa and tooling. This replaces the old `rubikpi3-msm-dkms`, `rubikpi3-lt9611-dkms`
and `rubikpi3-wifi-firmware` packages, and conflicts with `qcom-adreno1` and
`kgsl-dkms`. One deb does not bundle all Ubuntu dependencies for offline installs.

Configuration checks the board, OS, kernel, EL2/VHE, firmware, headers and module
origins. It generates `/boot/dtb-7.0.0-38-generic` for Ubuntu's stock `10_linux`
generator, builds both DKMS modules and refreshes initramfs. The ordinary **Ubuntu**
entry defaults to the adapted, tested kernel; reboot after installation without
selecting a separate adaptation entry. The menu remains visible for five seconds
before Ubuntu starts automatically. Advanced options and firmware settings remain available.
The `ttyMSM0` serial console is enabled at 115200 baud, preserving existing screen console settings.
When `splash` is already enabled, the package automatically adds
`plymouth.ignore-serial-consoles` to keep graphical boot and UART logging together;
`nosplash` and `plymouth.enable=0` are respected. Early simpledrm holds the referenced
display resources until native MSM takes over. No global clock/power keepalive options
are used. UEFI DT fixup must fill the framebuffer template from the current GOP.
Only old RubikPi3 one-shot selections are cleared. There is no live driver unloading or automatic reboot. Errors fail
dpkg configuration; resolve the cause and retry with `sudo dpkg --configure -a`.
Do not ignore a failed installation and reboot.

State/backups live under `/var/lib/rubikpi3-support/`; pre-unpack Wi-Fi backups use
`/var/lib/rubikpi3-pre-unpack.*`. Recognized old native/VPU/test entries, their
old default configuration and project DTBs under `/boot/dtb/` are backed up and
removed. Unknown/customized files stop automatic cleanup. The empty old DTB
directory is removed so Ubuntu GRUB cannot mistake the directory for a DT file. Modified generated
files, different USB firmware and hand-installed module overrides are preserved
and reported for manual handling instead of silently overwritten.

```sh
uname -r
dkms status
cat /sys/class/graphics/fb0/name
nmcli device status
v4l2-ctl --list-devices
sudo apt install ffmpeg v4l-utils gstreamer1.0-tools gstreamer1.0-plugins-good
python3 /usr/share/rubikpi3-support/test-codecs.py ./vpu-results --size 1920x1080
```

See [VALIDATION.md](VALIDATION.md) for hardware and packaging test boundaries.
Maintainers can run `python3 -m unittest discover -s tests -v` and
`python3 tests/check-deb.py dist/rubikpi3-ubuntu-support_0.2.2_arm64.deb` to repeat the checks.
GStreamer encoding requires explicit profile/level; FFmpeg hardware encoding
still segfaults. Details: [VPU guide](components/rubikpi3-vpu/README.en.md).

DKMS and the default boot entry are pinned to `7.0.0-38-generic`. Ubuntu may
install newer kernels, but this profile will not switch to an untested ABI.
A new supported ABI needs updated manifests, source hashes, DKMS restrictions,
maintainer scripts and validation. This package does not disable Ubuntu updates.

## Recovery and removal

```sh
sudo apt remove rubikpi3-ubuntu-support
```

Removal deletes the per-kernel DTB and both DKMS modules, refreshing initramfs.
The ordinary Ubuntu entry reverts to the UEFI DT with GPU/bridge/Venus modules
blocked for firmware display. No recovery menu entry is created. Wi-Fi payloads
are removed, so Wi-Fi may stop working. The fallback configuration at
`/etc/default/grub.d/zz-rubikpi3-support.cfg`, backups and USB firmware survive
remove/purge. Once no longer needed, remove the fallback configuration and run
`sudo update-grub`. Mesa, Ubuntu firmware and kernel packages remain; old
experimental drivers are not restored.
