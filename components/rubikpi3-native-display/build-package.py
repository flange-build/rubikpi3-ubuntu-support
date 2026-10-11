#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the LT9611 DKMS package from pinned Ubuntu 7.0.0-38.38 source."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

VERSION = "0.1.1"
SOURCE_SHA256 = "3371c76faaf71804e4da817e5767a7256216f708c4613f1fcc0f40ea117c1461"
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original drivers/gpu/drm/bridge/lontium-lt9611.c")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    data = args.source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        parser.error("expected unmodified Ubuntu 7.0.0-38.38 lontium-lt9611.c; SHA256 mismatch")
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve() / f"rubikpi3-lt9611-dkms_{VERSION}_arm64.deb"
    with tempfile.TemporaryDirectory(prefix="rubikpi3-lt9611-") as work:
        root = Path(work)
        src = root / f"usr/src/rubikpi3-lt9611-{VERSION}"
        src.mkdir(parents=True)
        (src / "lontium-lt9611.c").write_bytes(data)
        (src / "Makefile").write_text("obj-m += lontium-lt9611.o\n")
        for patch in sorted((HERE / "patches").glob("*.patch")):
            subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=src, check=True)
        for name in ("dkms.conf", "refresh-initramfs"):
            shutil.copyfile(HERE / "packaging" / name, src / name)
        (src / "SOURCE").write_text(f"Ubuntu linux-source-7.0.0 7.0.0-38.38\nOriginal C SHA256: {SOURCE_SHA256}\n")
        shutil.copytree(HERE / "patches", src / "applied-patches")
        docs = root / "usr/share/doc/rubikpi3-lt9611-dkms"
        docs.mkdir(parents=True)
        for name in ("README.md", "README.en.md"):
            shutil.copyfile(HERE / name, docs / name)
        shutil.copyfile("/usr/share/common-licenses/GPL-2", docs / "copyright")
        debian = root / "DEBIAN"
        debian.mkdir()
        for name in ("postinst", "prerm", "postrm"):
            shutil.copyfile(HERE / "packaging" / name, debian / name)
        size = (sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) + 1023) // 1024
        (debian / "control").write_text(f"""Package: rubikpi3-lt9611-dkms
Version: {VERSION}
Architecture: arm64
Section: kernel
Priority: optional
Maintainer: flange-build <flange-build@users.noreply.github.com>
Installed-Size: {size}
Depends: dkms (>= 3.2), build-essential, kmod, initramfs-tools | dracut
Recommends: linux-headers-generic
Description: LT9611 single-port-B support for RubikPi3 native HDMI
 Builds the Ubuntu LT9611 bridge driver with support for a sole DSI input
 on physical port B and preserves its I2C address across display blanking.
 Device-tree and boot profile deployment is separate.
""")
        sums = []
        for path in sorted(root.rglob("*")):
            executable = path.name == "refresh-initramfs" or path.parent == debian and path.name in ("postinst", "prerm", "postrm")
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
            if path.is_file() and debian not in path.parents:
                sums.append(f"{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n")
        (debian / "md5sums").write_text("".join(sums))
        (debian / "md5sums").chmod(0o644)
        root.chmod(0o755)
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
