# RubikPi3 Ubuntu support package

[简体中文](README.md) | **English**

One `rubikpi3-ubuntu-support_0.1.0_arm64.deb` integrates the tested kernel patches,
firmware, board-local DT generation, module parameters, initramfs and GRUB logic.
Building does not need EDK2 sources or binaries.
See [PATCHES.en.md](PATCHES.en.md) for the firmware/OS split.

Scope: **Ubuntu 26.04 ARM64, 7.0.0-38-generic, RubikPi3, EL2/VHE**, with
edk2-flange UEFI, symbol-bearing board FDT and Secure Boot disabled.
This is not a generic package for arbitrary Ubuntu/kernel/firmware versions.
It does not flash firmware, change TrustZone, repartition storage or reboot.

## Contents and build

The package contains MSM EL2 SECVID and LT9611 port-B DKMS sources; native HDMI
and Venus EL2 DT helpers; AP6256 firmware/CLM/NVRAM with the sample MAC removed;
verified Renesas USB firmware; initramfs hooks and dedicated native/recovery entries.
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
sudo apt install ./dist/rubikpi3-ubuntu-support_0.1.0_arm64.deb
sudo rubikpi3-support status
sudo reboot
```

APT resolves the pinned kernel/headers, DKMS, Ubuntu Qualcomm graphics firmware,
Mesa and tooling. This replaces the old `rubikpi3-msm-dkms`, `rubikpi3-lt9611-dkms`
and `rubikpi3-wifi-firmware` packages, and conflicts with `qcom-adreno1` and
`kgsl-dkms`. One deb does not bundle all Ubuntu dependencies for offline installs.

Configuration checks the board, OS, kernel, EL2/VHE, firmware, headers and module
origins. It validates a local DT, establishes a firmware recovery entry, builds
both DKMS modules, updates initramfs, then selects **native HDMI + GPU + VPU (EL2)**
as default with a five-second GRUB menu. Only old RubikPi3 one-shot selections
are cleared. There is no live driver unloading or automatic reboot. Errors fail
dpkg configuration; resolve the cause and retry with `sudo dpkg --configure -a`.
Do not ignore a failed installation and reboot.

State/backups live under `/var/lib/rubikpi3-support/`; pre-unpack Wi-Fi backups use
`/var/lib/rubikpi3-pre-unpack.*`. Old manual entries are retained. Modified generated
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
`python3 tests/check-deb.py dist/rubikpi3-ubuntu-support_0.1.0_arm64.deb` to repeat the checks.
GStreamer encoding requires explicit profile/level; FFmpeg hardware encoding
still segfaults. Details: [VPU guide](components/rubikpi3-vpu/README.en.md).

DKMS and the default boot entry are pinned to `7.0.0-38-generic`. Ubuntu may
install newer kernels, but this profile will not switch to an untested ABI.
A new supported ABI needs updated manifests, source hashes, DKMS restrictions,
maintainer scripts and validation. This package does not disable Ubuntu updates.

## Recovery and removal

Select **Ubuntu - RubikPi3 firmware display recovery** in GRUB. It uses UEFI's
compatibility FDT, omits the package DTB and blocks GPU/bridge/Venus modules.
This assumes edk2-flange compatibility firmware; the new integrated recovery
entry still needs a real boot acceptance test.

```sh
sudo apt remove rubikpi3-ubuntu-support
```

Removal selects recovery before removing the native entry and both DKMS modules,
then refreshes initramfs. Wi-Fi payloads are removed, so Wi-Fi may stop working.
**Recovery entry/default, backups and deployed USB firmware survive remove/purge**
to avoid falling back to old native entries that need the removed modules. This
does not reconstruct every historical manual setting. Once another entry works,
you may remove `/etc/grub.d/41_rubikpi3_firmware_recovery` and
`/etc/default/grub.d/zz-rubikpi3-support.cfg`, then run `sudo update-grub`.
Mesa, Ubuntu firmware and kernel packages remain; old experimental drivers are
not restored.
