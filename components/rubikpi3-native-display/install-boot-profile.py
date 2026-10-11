#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install a native HDMI GRUB entry; test once unless --make-default is given."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(*args):
    subprocess.run(args, check=True)


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default=os.uname().release)
    parser.add_argument("--make-default", action="store_true")
    parser.add_argument("--vpu-el2", action="store_true",
                        help="create a separate native HDMI + VPU entry; requires EL2")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run with sudo on the RubikPi3")
    vpu_tool = HERE.parent / "rubikpi3-vpu" / "prepare-dtb.py"
    if args.vpu_el2:
        if not vpu_tool.is_file():
            parser.error("keep the sibling rubikpi3-vpu directory alongside this tool")
        boot_log = output("journalctl", "-k", "-b", "--no-pager", "-o", "cat")
        if "All CPU(s) started at EL2" not in boot_log:
            parser.error("current boot does not confirm EL2; do not use this profile at EL1")
        fw = Path("/usr/lib/firmware/qcom/vpu-2.0/venus.mbn")
        if not any(Path(str(fw) + suffix).is_file() for suffix in ("", ".zst", ".xz")):
            parser.error("install linux-firmware-qualcomm-graphics first")
    kernel = args.kernel
    if not re.fullmatch(r"7\.0\.0-[0-9]+-generic", kernel):
        parser.error("this profile is limited to Ubuntu 7.0 generic; tested ABI: 38")
    for module in ("msm", "lontium_lt9611"):
        if "/updates/dkms/" not in output("modinfo", "-k", kernel, "-n", module):
            parser.error(f"install the required DKMS module first: {module}")
    for file in (f"/boot/vmlinuz-{kernel}", f"/boot/initrd.img-{kernel}",
                 "/usr/lib/firmware/renesas_usb_fw.mem"):
        if not Path(file).is_file():
            parser.error(f"required file missing: {file}")
    if not shutil.which("dracut"):
        parser.error("this boot installer currently requires dracut")
    root_uuid = output("findmnt", "-n", "-o", "UUID", "/")
    if not re.fullmatch(r"[0-9a-fA-F-]+", root_uuid):
        parser.error("could not resolve a UUID for the root filesystem")
    profile = "rubikpi3-native-vpu" if args.vpu_el2 else "rubikpi3-native"
    title = "native HDMI + VPU (EL2)" if args.vpu_el2 else "native HDMI"
    dtb = Path(f"/boot/dtb/{profile}.dtb")
    entry = Path("/etc/grub.d/43_rubikpi3_native_vpu" if args.vpu_el2
                 else "/etc/grub.d/42_rubikpi3_native")
    dracut = Path("/etc/dracut.conf.d/91-rubikpi3-native-display.conf")
    default = Path("/etc/default/grub.d/99-rubikpi3-native.cfg")
    backup = Path("/var/lib/rubikpi3-native-display") / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    source = backup / "firmware-source.dtb"
    shutil.copyfile("/sys/firmware/fdt", source)
    for file in (dtb, entry, dracut, default, Path("/boot/grub/grub.cfg")):
        if file.exists():
            dest = backup / file.relative_to("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)
    # Validate the board and complete generation before changing boot files.
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "native.dtb"
        run("python3", str(HERE / "prepare-dtb.py"), str(source), str(candidate))
        if args.vpu_el2:
            run("python3", str(vpu_tool), str(candidate), str(candidate), "--el2")
        dtb.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate, dtb)
        dtb.chmod(0o644)
    dracut.parent.mkdir(parents=True, exist_ok=True)
    dracut.write_text('add_drivers+=" msm lontium_lt9611 dispcc_sc7280 xhci_pci_renesas "\n'
                     'install_items+=" /usr/lib/firmware/renesas_usb_fw.mem "\n')
    dracut.chmod(0o644)
    run("update-initramfs", "-u", "-k", kernel)
    boot_uuid = output("grub-probe", "--target=fs_uuid", str(dtb))
    if not re.fullmatch(r"[0-9a-fA-F-]+", boot_uuid):
        parser.error("could not resolve the GRUB boot filesystem UUID")
    dtb_rel = output("grub-mkrelpath", str(dtb))
    linux_rel = output("grub-mkrelpath", f"/boot/vmlinuz-{kernel}")
    initrd_rel = output("grub-mkrelpath", f"/boot/initrd.img-{kernel}")
    entry.write_text(f'''#!/bin/sh
exec tail -n +3 $0
menuentry 'Ubuntu - RubikPi3 {title} ({kernel})' --id {profile} {{
    insmod part_gpt
    insmod ext2
    insmod fdt
    search --no-floppy --fs-uuid --set=root {boot_uuid}
    devicetree {dtb_rel}
    linux {linux_rel} root=UUID={root_uuid} ro quiet splash console=tty0 msm.separate_gpu_kms=0 deferred_probe_timeout=120
    initrd {initrd_rel}
}}
''')
    entry.chmod(0o755)
    if args.make_default:
        default.parent.mkdir(parents=True, exist_ok=True)
        default.write_text(f'GRUB_DEFAULT="{profile}"\nGRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=5\n')
        default.chmod(0o644)
    run("update-grub")
    run("grub-script-check", "/boot/grub/grub.cfg")
    if not args.make_default:
        run("grub-reboot", profile)
    print(f"Installed native HDMI entry for {kernel}; backups: {backup}")
    print("Reboot when ready. Original Ubuntu entries remain available.")


if __name__ == "__main__":
    main()
