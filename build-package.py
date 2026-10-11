#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build ONE offline RubikPi3 support deb from pinned source/firmware inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_deb', type=Path, help='Ubuntu linux-source-7.0.0 7.0.0-38.38')
    parser.add_argument('--wifi-firmware', type=Path, required=True, help='three original vendor AP6256 files')
    parser.add_argument('--usb-firmware', type=Path, required=True, help='verified renesas_usb_fw.mem from this board')
    parser.add_argument('--output', type=Path, default=HERE / 'dist')
    args = parser.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text())
    usb = args.usb_firmware.read_bytes()
    if hashlib.sha256(usb).hexdigest() != manifest['usb_firmware_sha256']:
        parser.error('Renesas USB firmware SHA256 mismatch')
    components = HERE / 'components'
    # Validate the source archive before extracting even the bridge file.
    spec = importlib.util.spec_from_file_location('msm_builder', components / 'rubikpi3-msm-dkms/build-package.py')
    msm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(msm)
    with args.source_deb.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != msm.SOURCE_SHA256:
            parser.error('Ubuntu kernel source SHA256 mismatch')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package, version = manifest['package'], manifest['version']
    with tempfile.TemporaryDirectory(prefix='rubikpi3-support-build-') as tmp:
        work = Path(tmp)
        artifacts = work / 'components'
        root = work / 'package'
        root.mkdir()
        run('python3', components / 'rubikpi3-msm-dkms/build-package.py', args.source_deb,
            '--output', artifacts)
        run('dpkg-deb', '-x', args.source_deb, work / 'ubuntu')
        archive = work / 'ubuntu/usr/src/linux-source-7.0.0.tar.bz2'
        with tarfile.open(archive, 'r:bz2') as tar:
            member = tar.getmember('linux-source-7.0.0/drivers/gpu/drm/bridge/lontium-lt9611.c')
            bridge = work / 'lontium-lt9611.c'
            bridge.write_bytes(tar.extractfile(member).read())
        run('python3', components / 'rubikpi3-native-display/build-package.py', bridge,
            '--output', artifacts)
        run('python3', components / 'rubikpi3-wifi-firmware/build-package.py', args.wifi_firmware,
            '--output', artifacts)
        # Only merge payloads, never nested debs or the old maintainer scripts.
        for deb in sorted(artifacts.glob('*.deb')):
            run('dpkg-deb', '-x', deb, root)
        for module, modversion in manifest['dkms'].items():
            src = root / f'usr/src/{module}-{modversion}'
            conf = src / 'dkms.conf'
            text = conf.read_text().replace('^7[.]0[.]0-[0-9]+-generic$', '^7[.]0[.]0-38-generic$')
            conf.write_text(text)
            shutil.copyfile(HERE / 'packaging/refresh-initramfs', src / 'refresh-initramfs')
        share = root / 'usr/share/rubikpi3-support'
        share.mkdir(parents=True)
        shutil.copyfile(HERE / 'manifest.json', share / 'manifest.json')
        # Keep the sibling layout used by the DT helpers. No board DTB, MAC,
        # runtime address, kernel binary or precompiled .ko enters the package.
        for component in ('rubikpi3-native-display', 'rubikpi3-vpu'):
            dest = share / 'components' / component
            dest.mkdir(parents=True)
            for name in ('prepare-dtb.py',):
                shutil.copyfile(components / component / name, dest / name)
        shutil.copyfile(components / 'rubikpi3-vpu/test-codecs.py', share / 'test-codecs.py')
        (share / 'firmware').mkdir()
        (share / 'firmware/renesas_usb_fw.mem').write_bytes(usb)
        copies = {
            'runtime/support.py': 'usr/sbin/rubikpi3-support',
            'packaging/dracut.conf': 'usr/lib/dracut/dracut.conf.d/92-rubikpi3-support.conf',
            'packaging/initramfs-hook': 'usr/share/initramfs-tools/hooks/rubikpi3-support',
        }
        for src, dest in copies.items():
            path = root / dest
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / src, path)
        docs = root / f'usr/share/doc/{package}'
        docs.mkdir(parents=True)
        for name in ('README.md', 'README.en.md', 'PATCHES.md', 'PATCHES.en.md', 'VALIDATION.md', 'copyright'):
            shutil.copyfile(HERE / name, docs / name)
        # README relative links remain usable in the installed documentation.
        for component in components.iterdir():
            if component.is_dir():
                dest = docs / 'components' / component.name
                dest.mkdir(parents=True)
                for file in component.glob('*.md'):
                    shutil.copyfile(file, dest / file.name)
        debian = root / 'DEBIAN'
        debian.mkdir()
        for script in ('preinst', 'postinst', 'prerm', 'postrm'):
            shutil.copyfile(HERE / 'packaging' / script, debian / script)
        legacy = 'rubikpi3-msm-dkms, rubikpi3-lt9611-dkms, rubikpi3-wifi-firmware'
        kernel = manifest['kernel']
        (debian / 'control').write_text(f'''Package: {package}
Version: {version}
Architecture: arm64
Section: non-free/kernel
Priority: optional
Maintainer: flange-build <flange-build@users.noreply.github.com>
Depends: python3 (>= 3.11), dkms (>= 3.2), build-essential, kmod, device-tree-compiler, grub-common, grub2-common, initramfs-tools | dracut, linux-image-{kernel}, linux-headers-{kernel}, linux-firmware-qualcomm-graphics, libgl1-mesa-dri, mesa-vulkan-drivers
Conflicts: {legacy}, kgsl-dkms, qcom-adreno1
Replaces: {legacy}
Provides: {legacy}
Suggests: ffmpeg, v4l-utils, gstreamer1.0-tools, gstreamer1.0-plugins-good
Description: RubikPi3 Ubuntu EL2 board support, drivers and boot configuration
 Integrates MSM and LT9611 DKMS, AP6256 and Renesas firmware, local native
 HDMI/Venus DT generation, initramfs hooks and a GRUB recovery entry.
 Validated for Ubuntu 26.04, kernel {kernel}, EL2/VHE. No UEFI flashing.
 Vendor firmware is included for local use; redistribution rights are separate.
''')
        checksums = []
        size = 0
        for path in sorted(root.rglob('*')):
            executable = (path.parent == debian and path.name in ('preinst', 'postinst', 'prerm', 'postrm')
                          or path.name in ('refresh-initramfs', 'rubikpi3-support')
                          or path.parent == root / 'usr/share/initramfs-tools/hooks')
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
            if path.is_file() and debian not in path.parents:
                size += path.stat().st_size
                checksums.append(f'{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n')
        with (debian / 'control').open('a') as f:
            f.write(f'Installed-Size: {(size + 1023) // 1024}\n')
        (debian / 'md5sums').write_text(''.join(checksums))
        root.chmod(0o755)
        deb = output / f'{package}_{version}_arm64.deb'
        run('dpkg-deb', '--root-owner-group', '-Zxz', '--build', root, deb)
        (output / (deb.name + '.sha256')).write_text(f'{hashlib.sha256(deb.read_bytes()).hexdigest()}  {deb.name}\n')
        print(deb)


if __name__ == '__main__':
    main()
