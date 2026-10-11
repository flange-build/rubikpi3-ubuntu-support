# RubikPi3 hardware video codecs

[简体中文](README.md) | **English**

H.264 and HEVC hardware encoding/decoding were verified at 720p and 1080p on
RubikPi3, Ubuntu 26.04.1 ARM64, kernel `7.0.0-38-generic`, running Linux at EL2/VHE.
VPU uses stock Venus modules and system firmware; it needs no DKMS package.
GPU and native HDMI still need their respective packages.

## Fix and installation

The original DT lacked the firmware IOMMU stream. Venus selected the TrustZone
PAS path, which failed with -22. An experimental SHM bridge patch authenticated
the firmware but then failed video protection-range configuration with -5; that
patch was removed. The working configuration uses the
[upstream SC7280 mapping](https://github.com/torvalds/linux/blob/v7.0/arch/arm64/boot/dts/qcom/sc7280-chrome-common.dtsi):
data streams `0x2180/0x20`, `0x2184/0x20`, and a `video-firmware` child with stream
`0x21a2/0`. This selects stock Venus's Linux-managed firmware mapping and direct
boot path. It requires EL2 and does not support protected video sessions. Do not
use this DTB with EL1/Gunyah. No UEFI or TrustZone flashing is involved.

Follow the [native HDMI setup](../rubikpi3-native-display/README.en.md) first,
including GPU/bridge drivers and USB firmware. Keep these sibling directories together:

```sh
sudo python3 ../rubikpi3-native-display/install-boot-profile.py --vpu-el2
# Boot the scheduled one-time entry and verify it, then make it the default:
sudo python3 ../rubikpi3-native-display/install-boot-profile.py --vpu-el2 --make-default
```

The installer checks the current EL2 boot log and Venus firmware, backs up files,
and creates **Ubuntu - RubikPi3 native HDMI + VPU (EL2) (7.0.0-38-generic)**,
ID `rubikpi3-native-vpu`. The earlier HDMI entry remains available. The selected
kernel is pinned in the entry; retest after kernel upgrades.

To generate only a board-local DTB:

```sh
python3 prepare-dtb.py native-hdmi.dtb native-hdmi-vpu.dtb --el2
```

The tool checks the board and existing stream mapping, preserves unrelated
hardware settings, and clears stale EFI/initrd addresses and boot entropy.
Do not share the resulting DTB between boards.

## Tests and usage

```sh
sudo apt install --no-install-recommends ffmpeg v4l-utils
v4l2-ctl --list-devices
gst-inspect-1.0 v4l2h264enc
python3 test-codecs.py ./vpu-results --size 1920x1080
```

GStreamer tools, videotestsrc and video4linux2 must also be installed. If its
cached plugin registry misses newly available codecs, rescan with
`GST_REGISTRY=/tmp/rubikpi-vpu-registry.bin gst-inspect-1.0 video4linux2`.
The user needs device-node access; desktop ACLs do not imply access for all SSH users.
Encoder and decoder node numbers can swap between boots; discover their roles.

The script explicitly uses GStreamer hardware encoders and FFmpeg hardware
decoders, checks resolution/frame count, and compares every decoded frame's
YUV420P pixels against software decoding. It sets H.264 High / HEVC Main,
Level 4.1 and 6 Mbps. Unconstrained 1080p encoding triggered a firmware fatal
error; the explicit profile/level configuration passed. See the Chinese README
for the full GStreamer command.

## Results and limits

2026-10-11, boot ID `24c6103a-21f2-4978-b68b-1d36db52ef71`: both H.264 and HEVC
passed 90-frame hardware encode/decode tests at 1280×720 and 1920×1080. All decoded
pixels matched software decoding. Inputs were 30 fps; these were functional tests,
not sustained throughput benchmarks. Raw elementary streams need
`-fps_mode passthrough` for FFmpeg frame comparisons to avoid timestamp-based drops.

Ubuntu FFmpeg 8.0.1's h264_v4l2m2m **encoder** still segfaults on this device,
including with an explicit level. Use GStreamer encoding for now. Hardware
FFmpeg decoding passed. 4K, 10-bit, VP8/VP9/MPEG-2, long-running load, suspend and
automatic browser acceleration were not tested.

A warm reboot lost the PCIe USB controller; the user's next restart restored USB
Ethernet. This reboot-stability issue remains unresolved. Device logs/videos
are under `~/vpu-check-20261011/` and are not committed.

For recovery, select the earlier **Ubuntu - RubikPi3 native HDMI** entry.
Set `GRUB_DEFAULT="rubikpi3-native"` in
`/etc/default/grub.d/99-rubikpi3-native.cfg` and run `sudo update-grub` to restore
that default. To remove the VPU entry, move
`/etc/grub.d/43_rubikpi3_native_vpu` out of the active directory and update GRUB.
No VPU module uninstall is needed.
