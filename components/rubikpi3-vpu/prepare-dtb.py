#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Enable Linux-managed Venus firmware on a board-local RubikPi3 EL2 DTB."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--el2", action="store_true", required=True,
                        help="this boot profile requires Linux to start at EL2")
    args = parser.parse_args()

    def get(file, *args):
        return subprocess.check_output(["fdtget", str(file), *args], text=True).strip()

    if "thundercomm,rubikpi3" not in get(args.source, "/", "compatible").split():
        parser.error("input must be this RubikPi3's own DTB")
    venus = get(args.source, "/__symbols__", "venus")
    smmu = get(args.source, "/__symbols__", "apps_smmu")
    if get(args.source, venus, "compatible") != "qcom,sc7280-venus":
        parser.error("only the SC7280 Venus binding is supported")
    phandle = get(args.source, "-t", "x", smmu, "phandle")
    streams = get(args.source, "-t", "x", venus, "iommus").split()
    base = [phandle, "2180", "20"]
    native = base + [phandle, "2184", "20"]
    if streams not in (base, native):
        parser.error("unexpected Venus stream mapping; refusing to overwrite it")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        candidate = Path(tmp) / "vpu.dtb"
        shutil.copyfile(args.source, candidate)

        def put(*args):
            subprocess.run(["fdtput", *args], check=True)

        # Upstream v7.0 sc7280-chrome-common.dtsi: data streams and the
        # dedicated firmware stream. The child selects Venus's no-TZ path.
        put("-t", "x", str(candidate), venus, "iommus", *native)
        if "video-firmware" not in get(candidate, "-l", venus).splitlines():
            put("-c", str(candidate), venus + "/video-firmware")
        else:
            existing = get(candidate, "-t", "x", venus + "/video-firmware", "iommus").split()
            if existing != [phandle, "21a2", "0"]:
                parser.error("unexpected firmware stream mapping")
        put("-t", "x", str(candidate), venus + "/video-firmware", "iommus", phandle, "21a2", "0")
        put("-t", "s", str(candidate), venus, "status", "okay")
        for prop in get(candidate, "-p", "/chosen").splitlines():
            if prop.startswith(("linux,uefi-", "linux,initrd-")) or prop in ("bootargs", "kaslr-seed", "rng-seed"):
                put("-d", str(candidate), "/chosen", prop)
        put("-t", "s", str(candidate), "/chosen", "flange,vpu-profile", "el2-direct-v1")
        candidate.chmod(0o644)
        candidate.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
