# RubikPi3 native HDMI

[简体中文](README.md) | **English**

For installed Ubuntu ARM64, Linux owns MSM DPU → DSI0 → LT9611 port B → HDMI,
with Adreno rendering. Native output exposes HDMI-A-1, msmdrmfb and hardware vblank.
The firmware's installer compatibility DT remains unchanged. An EFI framebuffer
may appear during early boot and is removed when native MSM takes over.

This directory provides an LT9611 single-port-B DKMS patch and a board-local DTB
generator. The [MSM EL2 DKMS package](../rubikpi3-msm-dkms/README.en.md) is also needed.
Target kernel: Ubuntu 7.0.0-38-generic. Compilation alone does not validate other
kernels, modes, hotplug or suspend/resume.

## Bridge driver

Extract `drivers/gpu/drm/bridge/lontium-lt9611.c` from Ubuntu
`linux-source-7.0.0=7.0.0-38.38`, then run:

```sh
python3 build-package.py /path/to/lontium-lt9611.c --output dist
sudo apt install ./dist/rubikpi3-lt9611-dkms_0.1.0_arm64.deb
dkms status
modinfo -n lontium_lt9611
```

The original source SHA256 is pinned to
`3371c76faaf71804e4da817e5767a7256216f708c4613f1fcc0f40ea117c1461`.
The build host needs Python 3, patch, dpkg-deb and the system GPL-2 license text;
the target needs matching kernel headers. GPL-2.0-only; upstream copyrights remain.

The patch preserves physical port@1 wiring, treats a sole B input as the primary
DSI, and selects 0x8250=0x14 / 0x8303 bit 6, matching this project's tested UEFI
configuration. Existing A-only and A+B behavior is unchanged. Move any previous
manual `updates/rubikpi3-native/lontium-lt9611.ko` to backup and run depmod before
installing DKMS. Do not unload live display drivers.

## Boot profile

```sh
sudo cp /sys/firmware/fdt ./firmware-original.dtb
sudo python3 prepare-dtb.py firmware-original.dtb /boot/dtb/rubikpi3-native.dtb
```

The generator requires this project's symbol-bearing RubikPi3 firmware FDT. It
preserves memory, MAC, ICE/GPI workarounds and supplies; enables HDMI; disables
unverified USB-C DP; and removes the old framebuffer and stale EFI addresses/entropy.
The resulting DTB is board-local and must not be copied to other boards.

The boot installer can generate the entry and schedule a one-time test:

```sh
sudo python3 install-boot-profile.py
sudo reboot
# After validating the picture, USB and GPU:
sudo python3 install-boot-profile.py --make-default
```

It backs up files under `/var/lib/rubikpi3-native-display/`, resolves filesystem
UUIDs, generates a local DTB and updates dracut initramfs. Original Ubuntu entries
remain available. Default selection uses `/etc/default/grub.d/99-rubikpi3-native.cfg`
with a five-second menu. The native entry pins the selected kernel; after an
upgrade, explicitly select `--kernel` and retest rather than automatically switching
to an unverified ABI. The boot installer currently requires dracut.

When Linux starts at EL2, add `--vpu-el2` to create a separate native HDMI + VPU
entry. Read the [VPU documentation](../rubikpi3-vpu/README.en.md) for firmware
requirements, tested encoding settings and recovery instructions.

The separate GRUB entry uses that DTB, the updated Ubuntu initramfs and
`msm.separate_gpu_kms=0 deferred_probe_timeout=120`. These combine GPU/display and
allow GPU SMMU dependencies to load before the probe deadline. Use this board's
root UUID and kernel paths. Test with grub-reboot before selecting it as default;
retain the original Ubuntu entry for recovery.

The Renesas USB controller also needs `/usr/lib/firmware/renesas_usb_fw.mem`,
copied here from the board's read-only-mounted usb_fw partition, with SHA256
`177560c224c73d040836b17082348036430ecf59e8a32d7736ce2b80b2634f97`.
It is not bundled in the DKMS package. Include it in initramfs for USB input/Ethernet.

## Verification and recovery

Check `/sys/class/graphics/fb0/name` for msmdrmfb, DRM connectors for HDMI-A-1,
kernel logs and actual window motion. Connector enumeration alone does not prove
correct HDMI output. See this repository's VALIDATION.md for test scope.

For recovery, boot the original Ubuntu entry with the firmware DT and
separate_gpu_kms=1. Move the native default configuration and
`/etc/grub.d/42_rubikpi3_native` out of their active directories, run update-grub,
then remove rubikpi3-lt9611-dkms. Removal restores the stock
bridge module and updates initramfs, but does not remove manually created GRUB
entries. The stock bridge module cannot drive this board's sole B input.
