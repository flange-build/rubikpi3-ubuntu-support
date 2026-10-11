# Patch inventory and UEFI / Ubuntu responsibilities

[简体中文](PATCHES.md) | **English**

“Patch” includes code, device descriptions, firmware and deployment logic.
Paths below are relative to `components/`. Candidates are not hardware results.

| Change | Current implementation | UEFI responsibility |
| --- | --- | --- |
| MSM EL2 SECVID | RubikPi3/VHE-gated DKMS patch | DT alternative exists in source; stock-driver validation pending |
| MSM trace include paths | Out-of-tree build patch | Disappears if MSM DKMS can be retired |
| LT9611 sole port B | Kernel parsing and B clock/data register selection | Kernel support still required; renaming port 1 to 0 is not equivalent |
| DPU/DISPCC/DSI/PHY/bridge | Local DT helper enables native display | Can move to a distinct firmware native-display mode |
| Framebuffer removal / DP disabled | Native helper removes compatibility framebuffer and disables untested USB-C DP | Can be firmware mode policy; installer still needs compatibility output |
| Venus firmware/data streams | Upstream stream mappings select stock Venus direct boot | Can move to EL2-specific firmware fixup, never unconditional EL1/Gunyah |
| AP6256 firmware/CLM/NVRAM | Board files, sample MAC removed, stock brcmfmac | Linux still needs firmware files; MAC/power/SDIO description belongs in DT |
| Renesas firmware | Validated payload and initramfs inclusion | Firmware can initialize USB, but Linux may request firmware after reset |
| separate_gpu_kms=0 | Native boot parameter | Linux policy managed by the package |
| deferred_probe_timeout=120 | Wait for display/GPU dependencies | Linux dependency/loading issue; no proven UEFI-only fix |
| separate_gpu_kms=1 | Legacy compatibility modprobe default; native entry overrides it | Linux compatibility policy |
| DKMS/depmod/initramfs hooks | OS package lifecycle | Ubuntu responsibility |
| GRUB default / pinned ABI / recovery | Generated entries and backed-up state | Ubuntu responsibility |
| Stale EFI/initrd addresses and entropy | Removed from saved DT | Fresh firmware FDT could eliminate static snapshots |
| Codec cache, encoding level, FFmpeg faults | Test tool and documented limits | Userspace, not UEFI |

Failed experimental Venus PAS/SHM patches, credentials, networking configuration,
partition changes and speculative fixes are excluded.

## GPU DT candidate

In the pinned Ubuntu 7.0.0-38.38 `adreno_gpu.c`, `zap_shader_load_mdt()` returns
`-ENODEV` if the `zap-shader` node is unavailable. `a6xx_gpu.c` handles that result
by writing `RBBM_SECVID_TRUST_CNTL=0` during initialization. This matches the
current patch's forced return value and supplies a source-level alternative.

UEFI could disable `zap-shader` when the required EL2/VHE access is confirmed,
allowing stock MSM to perform each direct transition. This is not a one-time
firmware register write: Linux must still handle GPU resets and runtime power
management. EL2 alone is not a general guarantee of secure register access.

The first package retains the validated MSM patch. Removing it requires stock
MSM + candidate DT cold/warm boot, render readback, window motion, GPU reset and
suspend/resume tests. Module enumeration alone is insufficient.

## Firmware modes to implement next

1. Installer compatibility: retain simple-framebuffer and existing clock/power,
   ICE/GPI workarounds. The official installer lacks the bridge patch.
2. Installed native system: enable real display nodes, omit the compatibility
   framebuffer, add Venus mapping in actual EL2 mode, and add GPU DT policy only
   after stock-driver validation.
3. EL1/Gunyah: keep that mode's own secure/PAS descriptions; do not reuse EL2 DT.

A future versioned DT marker can help the package recognize firmware capabilities
and avoid a local override, but cannot replace dependency validation. **This
change does not implement or flash these firmware modes.** Existing board DTS
ICE/GPI, supply/clock and GPIO handoff fixes are preserved. No global ignore-unused
parameters or ICE blacklist are added. DSP preload, pre-GRUB failures and warm
reboot PCIe USB loss are not established as fixed by this package.

## Sources

Driver analysis uses the pinned Ubuntu source and preserved SOURCE/applied-patches.
Venus mapping follows [upstream SC7280 Chrome DT](https://github.com/torvalds/linux/blob/v7.0/arch/arm64/boot/dts/qcom/sc7280-chrome-common.dtsi).
Maintainer scripts follow [Debian script semantics](https://www.debian.org/doc/debian-policy/ch-maintainerscripts.html)
and replacement metadata follows [Debian package relationships](https://www.debian.org/doc/debian-policy/ch-relationships.html).
