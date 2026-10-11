#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a board-local native HDMI DTB from the firmware-provided FDT."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

# qcom,gcc-sc7280.h: DISP_AHB, DISP_HF_AXI, DISP_SF_AXI, DISP_GPLL0_SRC;
# HLOS1_VOTE_MMNOC_MMU_TBU_HF0/HF1_GDSC. Provider phandles come from this DT.
DISPLAY_CLOCKS = (22, 24, 25, 23)
DISPLAY_DOMAINS = (5, 6)


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

    def cell(node, prop):
        values = get(args.source, "-t", "x", node, prop).split()
        if len(values) != 1:
            parser.error(f"expected one cell in {node}/{prop}")
        return int(values[0], 16)

    gcc = get(args.source, "/__symbols__", "gcc")
    mdss = get(args.source, "/__symbols__", "mdss")
    for node, binding in ((gcc, "qcom,gcc-sc7280"), (mdss, "qcom,sc7280-mdss")):
        if binding not in get(args.source, node, "compatible").split():
            parser.error(f"unexpected display resource provider: {node}")
    if cell(gcc, "#clock-cells") != 1 or cell(gcc, "#power-domain-cells") != 1:
        parser.error("only the SC7280 one-cell clock/power-domain bindings are supported")
    gcc_phandle, mdss_phandle = cell(gcc, "phandle"), cell(mdss, "phandle")
    if (not 0 < gcc_phandle < 0xffffffff or not 0 < mdss_phandle < 0xffffffff or
            gcc_phandle == mdss_phandle):
        parser.error("invalid GCC/MDSS phandles")
    chosen_props = get(args.source, "-p", "/chosen").splitlines()
    for prop in ("#address-cells", "#size-cells"):
        if prop in chosen_props and cell("/chosen", prop) != 2:
            parser.error("framebuffer handoff requires two-cell chosen addresses and sizes")
    if "ranges" in chosen_props and get(args.source, "-t", "x", "/chosen", "ranges"):
        parser.error("framebuffer handoff requires an untranslated chosen address space")
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
            props = get(dtb, "-p", node).splitlines()
            simplefb = "compatible" in props and "simple-framebuffer" in get(dtb, node, "compatible").split()
            if name.startswith("framebuffer@") and not simplefb:
                parser.error(f"preserving unrecognized framebuffer node: {node}")
            if simplefb:
                put("-r", str(dtb), node)
        # Keep boot scanout resources claimed until MSM takes over. Never reuse
        # a previous boot's GOP address, dimensions, or memory-region override:
        # EDK2's DT fixup fills this disabled template from the current GOP.
        for prop in ("#address-cells", "#size-cells"):
            put("-t", "x", str(dtb), "/chosen", prop, "2")
        put(str(dtb), "/chosen", "ranges")
        fb = "/chosen/framebuffer@0"
        put("-c", str(dtb), fb)
        put("-t", "s", str(dtb), fb, "compatible", "simple-framebuffer")
        put("-t", "x", str(dtb), fb, "reg", "0", "0", "0", "0")
        for prop in ("width", "height", "stride"):
            put("-t", "x", str(dtb), fb, prop, "0")
        put("-t", "s", str(dtb), fb, "format", "x8r8g8b8")
        put("-t", "s", str(dtb), fb, "status", "disabled")
        for prop, identifiers in (("clocks", DISPLAY_CLOCKS), ("power-domains", DISPLAY_DOMAINS)):
            cells = [value for identifier in identifiers for value in (gcc_phandle, identifier)]
            put("-t", "x", str(dtb), fb, prop, *(f"{value:x}" for value in cells))
        put("-t", "x", str(dtb), fb, "display", f"{mdss_phandle:x}")
        # EFI stub/GRUB must supply fresh addresses and boot entropy each boot.
        for prop in get(dtb, "-p", "/chosen").splitlines():
            if prop.startswith(("linux,uefi-", "linux,initrd-")) or prop in (
                    "bootargs", "kaslr-seed", "rng-seed", "flange,display-fixup-version"):
                put("-d", str(dtb), "/chosen", prop)
        put("-t", "s", str(dtb), "/chosen", "flange,display-profile", "native-hdmi-v1")
        dtb.chmod(0o644)
        dtb.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
