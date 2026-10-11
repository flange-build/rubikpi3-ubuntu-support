#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a board-local native HDMI DTB from the firmware-provided FDT."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="saved /sys/firmware/fdt from this board")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    def get(path, *extra):
        return subprocess.check_output(["fdtget", str(path), *extra], text=True).strip()

    compatible = get(args.source, "/", "compatible").split()
    if "thundercomm,rubikpi3" not in compatible:
        parser.error("input FDT is not a Thundercomm RubikPi3")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        dtb = Path(tmp) / "native.dtb"
        shutil.copyfile(args.source, dtb)

        def put(*extra):
            subprocess.run(["fdtput", *extra], check=True)

        for label in ("mdss", "dispcc", "lt9611_codec", "mdss_dsi", "mdss_dsi_phy"):
            node = get(dtb, "/__symbols__", label)
            put("-t", "s", str(dtb), node, "status", "okay")
        # HDMI only. USB-C DisplayPort has not been validated in this profile.
        node = get(dtb, "/__symbols__", "mdss_dp")
        put("-t", "s", str(dtb), node, "status", "disabled")
        for name in get(dtb, "-l", "/chosen").splitlines():
            node = f"/chosen/{name}"
            if name.startswith("framebuffer@"):
                put("-r", str(dtb), node)
        # EFI stub/GRUB must supply fresh addresses and boot entropy each boot.
        for prop in get(dtb, "-p", "/chosen").splitlines():
            if prop.startswith(("linux,uefi-", "linux,initrd-")) or prop in ("bootargs", "kaslr-seed", "rng-seed"):
                put("-d", str(dtb), "/chosen", prop)
        put("-t", "s", str(dtb), "/chosen", "flange,display-profile", "native-hdmi-v1")
        dtb.chmod(0o644)
        dtb.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
