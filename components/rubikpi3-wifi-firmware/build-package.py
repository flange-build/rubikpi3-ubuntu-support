#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a local firmware package from verified vendor downloads (no network)."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

VERSION = "0.1.0"
PACKAGE = "rubikpi3-wifi-firmware"
BOARD = "brcmfmac43456-sdio.thundercomm,rubikpi3"
SHA256 = {
    "bin": "ddf83f2100885b166be52d21c8966db164fdd4e1d816aca2acc67ee9cc28d726",
    "clm_blob": "2dbd7d22fc9af0eb560ceab45b19646d211bc7b34a1dd00c6bfac5dd6ba25e8a",
    "txt": "44e0bb322dc1f39a4b0a89f30ffdd28bc93f7d7aaf534d06d229fe56f6198194",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    inputs = {}
    for suffix, expected in SHA256.items():
        path = args.firmware_dir / f"brcmfmac43456-sdio.{suffix}"
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            parser.error(f"SHA256 mismatch: {path}")
        inputs[suffix] = data
    # Never clone the sample MAC onto every board. brcmfmac uses the platform MAC.
    inputs["txt"], count = re.subn(rb"(?m)^macaddr=[^\r\n]*\r?\n", b"", inputs["txt"])
    if count != 1:
        parser.error("expected exactly one sample macaddr in pinned vendor NVRAM")
    here = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve() / f"{PACKAGE}_{VERSION}_all.deb"
    with tempfile.TemporaryDirectory(prefix=f"{PACKAGE}-") as tmp:
        root = Path(tmp)
        firmware = root / "usr/lib/firmware/brcm"
        firmware.mkdir(parents=True)
        for suffix, data in inputs.items():
            (firmware / f"{BOARD}.{suffix}").write_bytes(data)
        copies = {
            "packaging/dracut.conf": "usr/lib/dracut/dracut.conf.d/91-rubikpi3-wifi-firmware.conf",
            "packaging/initramfs-hook": "usr/share/initramfs-tools/hooks/rubikpi3-wifi-firmware",
            "packaging/postinst": "DEBIAN/postinst",
            "packaging/postrm": "DEBIAN/postrm",
            "README.md": f"usr/share/doc/{PACKAGE}/README.md",
            "README.en.md": f"usr/share/doc/{PACKAGE}/README.en.md",
            "packaging/copyright": f"usr/share/doc/{PACKAGE}/copyright",
        }
        executable = {"DEBIAN/postinst", "DEBIAN/postrm", copies["packaging/initramfs-hook"]}
        for source, dest in copies.items():
            target = root / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(here / source, target)
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() or path.relative_to(root).as_posix() in executable else 0o644)
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.parent != root / "DEBIAN")
        size = (sum(p.stat().st_size for p in files) + 1023) // 1024
        (root / "DEBIAN/control").write_text(f"""Package: {PACKAGE}
Version: {VERSION}
Architecture: all
Maintainer: flange-build <flange-build@users.noreply.github.com>
Section: non-free/kernel
Priority: optional
Depends: initramfs-tools | dracut
Installed-Size: {size}
Description: RubikPi3 AP6256 firmware for the in-tree brcmfmac driver
 Board-specific BCM43456 firmware, CLM and NVRAM for Thundercomm RubikPi3.
 No kernel module is built or replaced. Updates existing initramfs images.
""")
        (root / "DEBIAN/md5sums").write_text("".join(
            f"{hashlib.md5(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n" for p in files
        ))
        for path in (root / "DEBIAN/control", root / "DEBIAN/md5sums"):
            path.chmod(0o644)
        root.chmod(0o755)
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
