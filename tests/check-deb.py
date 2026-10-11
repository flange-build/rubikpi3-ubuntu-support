#!/usr/bin/env python3
"""Inspect a built deb without installing it or executing its maintainer scripts."""
import hashlib
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
    assert (root / 'usr/sbin/rubikpi3-support').read_bytes() == (source / 'runtime/support.py').read_bytes()
    for name in ('preinst', 'postinst', 'prerm', 'postrm'):
        assert (root / 'DEBIAN' / name).read_bytes() == (source / 'packaging' / name).read_bytes()
print('PASS: payload checksums, executable scripts, syntax, ABI gates, clean payload and current runtime')
