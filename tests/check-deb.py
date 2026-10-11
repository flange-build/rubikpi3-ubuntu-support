#!/usr/bin/env python3
"""Inspect a built deb without installing it or executing its maintainer scripts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

deb = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    subprocess.run(['dpkg-deb', '-R', str(deb), tmp], check=True)
    for line in (root / 'DEBIAN/md5sums').read_text().splitlines():
        expected, name = line.split('  ', 1)
        assert hashlib.md5((root / name).read_bytes()).hexdigest() == expected, name
    for script in ('preinst', 'postinst', 'prerm', 'postrm'):
        path = root / 'DEBIAN' / script
        assert os.access(path, os.X_OK), path
        subprocess.run(['sh', '-n', str(path)], check=True)
    for conf in root.glob('usr/src/*/dkms.conf'):
        assert '^7[.]0[.]0-38-generic$' in conf.read_text(), conf
    assert len(list(root.glob('usr/src/*/dkms.conf'))) == 2
    for hook in root.glob('usr/src/*/refresh-initramfs'):
        assert 'rubikpi3-ubuntu-support' in hook.read_text()
        subprocess.run(['sh', '-n', str(hook)], check=True)
    for ext in ('*.deb', '*.dtb', '*.ko'):
        assert not list(root.rglob(ext)), ext
    nvram = next(root.glob('usr/lib/firmware/brcm/*.txt')).read_text()
    assert not any(line.startswith('macaddr=') for line in nvram.splitlines())
    # Ensure the deliverable is current rather than a stale earlier build.
    source = Path(__file__).resolve().parents[1]
    manifest = json.loads((source / 'manifest.json').read_text())
    assert json.loads((root / 'usr/share/rubikpi3-support/manifest.json').read_text()) == manifest
    components = {'rubikpi3-msm': 'rubikpi3-msm-dkms', 'rubikpi3-lt9611': 'rubikpi3-native-display'}
    for module, version in manifest['dkms'].items():
        module_source = root / f'usr/src/{module}-{version}'
        assert f'PACKAGE_VERSION="{version}"' in (module_source / 'dkms.conf').read_text()
        patches = source / 'components' / components[module] / 'patches'
        for patch in patches.glob('*.patch'):
            assert (module_source / 'applied-patches' / patch.name).read_bytes() == patch.read_bytes()
    assert (root / 'usr/sbin/rubikpi3-support').read_bytes() == (source / 'runtime/support.py').read_bytes()
    for component in ('rubikpi3-native-display', 'rubikpi3-vpu'):
        name = f'components/{component}/prepare-dtb.py'
        assert (root / 'usr/share/rubikpi3-support' / name).read_bytes() == (source / name).read_bytes()
    for installed, original in (
        ('usr/lib/dracut/dracut.conf.d/92-rubikpi3-support.conf', 'packaging/dracut.conf'),
        ('usr/share/initramfs-tools/hooks/rubikpi3-support', 'packaging/initramfs-hook'),
    ):
        assert (root / installed).read_bytes() == (source / original).read_bytes()
    for name in ('preinst', 'postinst', 'prerm', 'postrm'):
        assert (root / 'DEBIAN' / name).read_bytes() == (source / 'packaging' / name).read_bytes()
print('PASS: payload checksums, executable scripts, syntax, ABI gates, clean payload and current runtime')
