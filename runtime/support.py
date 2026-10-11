#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Manage the tested RubikPi3 Ubuntu profile; never flash or reboot firmware."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SHARE = Path('/usr/share/rubikpi3-support')
STATE = Path('/var/lib/rubikpi3-support')
NATIVE = '/etc/grub.d/44_rubikpi3_support'
RECOVERY = '/etc/grub.d/41_rubikpi3_firmware_recovery'
DEFAULT = '/etc/default/grub.d/zz-rubikpi3-support.cfg'
DTB = '/boot/dtb/rubikpi3-ubuntu-support.dtb'
USB = '/usr/lib/firmware/renesas_usb_fw.mem'
NATIVE_ID = 'rubikpi3-ubuntu-support'
RECOVERY_ID = 'rubikpi3-ubuntu-firmware'


def run(*args):
    try:
        return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    except subprocess.CalledProcessError as error:
        # DKMS puts useful failure details on stdout as well as in make.log.
        # Retain those details in apt's terminal/log instead of hiding them.
        if error.stdout:
            print(error.stdout, file=sys.stderr, end='')
        raise


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Support:
    # Root injection is for isolated lifecycle tests; the installed CLI always
    # operates on /. There is no environment-controlled privileged root.
    def __init__(self, root=Path('/')):
        self.root = root
        self.share = self.path(SHARE)
        self.state = self.path(STATE)
        self.manifest = json.loads((self.share / 'manifest.json').read_text())
        self.kernel = self.manifest['kernel']

    def path(self, path):
        return self.root / str(path).lstrip('/')

    def load_state(self):
        p = self.state / 'managed.json'
        return json.loads(p.read_text()) if p.exists() else {}

    def save_state(self, state):
        self.atomic(self.state / 'managed.json', json.dumps(state, indent=2).encode(), 0o600)

    @staticmethod
    def atomic(path, data, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            try:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                tmp.chmod(mode)
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)

    def check_managed(self, names):
        state = self.load_state()
        for name in names:
            p = self.path(name)
            if p.is_symlink():
                raise RuntimeError(f'Refusing symlink at managed path: {name}')
            if p.exists() and (name not in state or digest(p) != state[name]):
                raise RuntimeError(f'Preserving untracked/modified file: {name}; back it up and move it aside first')

    def preflight(self):
        if os.uname().machine != 'aarch64' or os.uname().release != self.kernel:
            raise RuntimeError(f'Boot aarch64 Ubuntu {self.kernel} before configuring this package')
        os_release = dict(line.split('=', 1) for line in self.path('/etc/os-release').read_text().splitlines()
                          if '=' in line and not line.startswith('#'))
        if os_release.get('ID', '').strip('"') != 'ubuntu' or os_release.get('VERSION_ID', '').strip('"') != self.manifest['ubuntu_version']:
            raise RuntimeError('This package version is validated only for Ubuntu 26.04')
        board = self.path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
        if self.manifest['compatible'].encode() not in board:
            raise RuntimeError('Not a RubikPi3')
        log = run('journalctl', '-k', '-b', '--no-pager', '-o', 'cat')
        if 'All CPU(s) started at EL2' not in log or 'VHE mode initialized successfully' not in log:
            raise RuntimeError('Current boot must confirm EL2 and VHE for GPU/VPU direct access')
        for var in self.path('/sys/firmware/efi/efivars').glob('SecureBoot-*'):
            if var.read_bytes()[4:5] == b'\x01':
                raise RuntimeError('Secure Boot is enabled; this package has not validated DKMS key enrollment')
        for name in (f'/boot/vmlinuz-{self.kernel}', f'/boot/initrd.img-{self.kernel}',
                     f'/lib/modules/{self.kernel}/build/Makefile', '/sys/firmware/fdt'):
            if not self.path(name).is_file():
                raise RuntimeError(f'Missing {name}')
        fw = '/usr/lib/firmware/qcom/vpu-2.0/venus.mbn'
        if not any(self.path(fw + suffix).is_file() for suffix in ('', '.zst', '.xz')):
            raise RuntimeError('Missing Venus firmware (linux-firmware-qualcomm-graphics)')
        self.check_managed((NATIVE, RECOVERY, DEFAULT, DTB))
        usb = self.path(USB)
        if usb.exists() and digest(usb) != self.manifest['usb_firmware_sha256']:
            raise RuntimeError('Existing Renesas firmware differs; preserving it for manual review')
        # Avoid hiding hand-installed modules behind DKMS. The module chosen by
        # modprobe must either be stock or in the managed DKMS directory.
        for module in ('msm', 'lontium_lt9611'):
            location = run('modinfo', '-k', self.kernel, '-n', module)
            if '/kernel/' not in location and '/updates/dkms/' not in location:
                raise RuntimeError(f'Unmanaged module override: {location}')

    def ensure_usb(self):
        source = self.share / 'firmware/renesas_usb_fw.mem'
        if digest(source) != self.manifest['usb_firmware_sha256']:
            raise RuntimeError('Bundled Renesas firmware checksum mismatch')
        target = self.path(USB)
        if target.exists():
            if digest(target) != digest(source):
                raise RuntimeError('Refusing to overwrite different Renesas firmware')
            return
        # Record intent first so interrupted configuration can still be removed.
        state = self.load_state()
        state[USB] = digest(source)
        self.save_state(state)
        self.atomic(target, source.read_bytes())

    def build_modules(self):
        for module, version in self.manifest['dkms'].items():
            if not self.path(f'/var/lib/dkms/{module}/{version}/source').exists():
                run('dkms', 'add', '-m', module, '-v', version)
            run('dkms', 'build', '--force', '-m', module, '-v', version, '-k', self.kernel)
            run('dkms', 'install', '--force', '-m', module, '-v', version, '-k', self.kernel)
        run('depmod', '-a', self.kernel)
        for module in ('msm', 'lontium_lt9611'):
            if '/updates/dkms/' not in run('modinfo', '-k', self.kernel, '-n', module):
                raise RuntimeError(f'DKMS module did not take precedence: {module}')

    def boot_entries(self):
        root_uuid = run('findmnt', '-n', '-o', 'UUID', '/')
        boot_uuid = run('grub-probe', '--target=fs_uuid', f'/boot/vmlinuz-{self.kernel}')
        for uuid in (root_uuid, boot_uuid):
            if not re.fullmatch('[0-9a-fA-F-]+', uuid):
                raise RuntimeError('Unsupported root/boot filesystem UUID')
        image = run('grub-mkrelpath', f'/boot/vmlinuz-{self.kernel}')
        initrd = run('grub-mkrelpath', f'/boot/initrd.img-{self.kernel}')
        self.path(DTB).parent.mkdir(parents=True, exist_ok=True)
        if run('grub-probe', '--target=fs_uuid', str(Path(DTB).parent)) != boot_uuid:
            raise RuntimeError('DTB and kernel must reside on the same boot filesystem')
        dtb = run('grub-mkrelpath', str(Path(DTB).parent)).rstrip('/') + '/' + Path(DTB).name
        for path in (image, initrd, dtb):
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path):
                raise RuntimeError(f'Unsupported GRUB path: {path}')

        def entry(native):
            title = 'native HDMI + GPU + VPU (EL2)' if native else 'firmware display recovery'
            ident = NATIVE_ID if native else RECOVERY_ID
            tree = f'    devicetree {dtb}\n' if native else ''
            params = ('msm.separate_gpu_kms=0 deferred_probe_timeout=120' if native else
                      'module_blacklist=msm,lontium_lt9611,venus_core,venus_enc,venus_dec')
            return f'''#!/bin/sh
exec tail -n +3 $0
menuentry 'Ubuntu - RubikPi3 {title} ({self.kernel})' --id {ident} {{
    insmod part_gpt
    insmod ext2
    insmod fdt
    search --no-floppy --fs-uuid --set=root {boot_uuid}
{tree}    linux {image} root=UUID={root_uuid} ro console=tty0 {params}
    initrd {initrd}
}}
'''.encode()
        return entry(True), entry(False)

    def publish(self, changes):
        """Back up generated files and restore them if GRUB generation fails."""
        self.check_managed(changes)
        self.state.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),
                                      dir=self.state))
        old = {}
        state = self.load_state()
        for name in changes:
            p = self.path(name)
            old[name] = (p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None
            if p.exists():
                dest = backup / name.lstrip('/')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        cfg = self.path('/boot/grub/grub.cfg')
        old_cfg = (cfg.read_bytes(), cfg.stat().st_mode & 0o777) if cfg.exists() else None
        if cfg.exists():
            shutil.copy2(cfg, backup / 'grub.cfg')
        try:
            for name, content in changes.items():
                if content is None:
                    self.path(name).unlink(missing_ok=True)
                    state.pop(name, None)
                else:
                    self.atomic(self.path(name), *content)
                    state[name] = digest(self.path(name))
            run('update-grub')
            run('grub-script-check', '/boot/grub/grub.cfg')
            self.save_state(state)
        except Exception:
            for name, content in old.items():
                if content is None:
                    self.path(name).unlink(missing_ok=True)
                else:
                    self.atomic(self.path(name), *content)
            if old_cfg:
                self.atomic(cfg, *old_cfg)
            else:
                cfg.unlink(missing_ok=True)
            raise
        print(f'Boot configuration backup: {backup}')

    @staticmethod
    def default(ident):
        return (f'GRUB_DEFAULT="{ident}"\nGRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=5\n'.encode(), 0o644)

    def configure(self):
        self.preflight()
        self.state.mkdir(parents=True, exist_ok=True)
        source = self.state / 'firmware-source.dtb'
        if not source.exists():
            self.atomic(source, self.path('/sys/firmware/fdt').read_bytes(), 0o600)
        # Validate and generate the complete DT before replacing any module or
        # selecting a new boot entry. The source and output belong to this board.
        with tempfile.TemporaryDirectory(dir=self.state) as tmp:
            candidate = Path(tmp) / 'native.dtb'
            components = self.share / 'components'
            run('python3', str(components / 'rubikpi3-native-display/prepare-dtb.py'), str(source), str(candidate))
            run('python3', str(components / 'rubikpi3-vpu/prepare-dtb.py'), str(candidate), str(candidate), '--el2')
            data = candidate.read_bytes()
        self.ensure_usb()
        native, recovery = self.boot_entries()
        # Establish a stock-driver recovery route before DKMS changes. If an
        # initial build fails, a retry is possible without booting a broken
        # native profile left by a previous manual/component installation.
        if NATIVE not in self.load_state():
            self.publish({RECOVERY: (recovery, 0o755), DEFAULT: self.default(RECOVERY_ID)})
        self.build_modules()
        run('update-initramfs', '-u', '-k', self.kernel)
        self.publish({DTB: (data, 0o644), NATIVE: (native, 0o755),
                      RECOVERY: (recovery, 0o755), DEFAULT: self.default(NATIVE_ID)})
        env = run('grub-editenv', '/boot/grub/grubenv', 'list')
        for line in env.splitlines():
            if line.startswith('next_entry=rubikpi3'):
                run('grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry')
        print(f'Installed {NATIVE_ID} for {self.kernel}. Reboot when ready; firmware was not flashed.')

    def remove(self):
        # Leave a firmware-backed recovery entry/default: old native profiles
        # can depend on the two DKMS modules that are about to be removed.
        state = self.load_state()
        if RECOVERY in state:
            self.check_managed((RECOVERY,))
            if not self.path(RECOVERY).is_file():
                raise RuntimeError('Recovery entry is missing; reconfigure the package before removing it')
            self.publish({NATIVE: None, DTB: None, DEFAULT: self.default(RECOVERY_ID)})
            env = run('grub-editenv', '/boot/grub/grubenv', 'list')
            if any(x.startswith('next_entry=rubikpi3') for x in env.splitlines()):
                run('grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry')
        for module, version in self.manifest['dkms'].items():
            if self.path(f'/var/lib/dkms/{module}/{version}').exists():
                run('dkms', 'remove', '-m', module, '-v', version, '--all')
        # Keep validated USB firmware for recovery and SSH. It was either
        # already present or copied by ensure_usb, never owned by dpkg here.
        print('Firmware recovery entry, USB firmware and backups retained. No live drivers unloaded.')

    def status(self):
        print(json.dumps(self.manifest, indent=2))
        print(run('dkms', 'status'))
        for name in (DEFAULT, DTB, USB):
            p = self.path(name)
            print(f'{name}: {digest(p) if p.is_file() else "missing"}')
        print('Checksums describe installed files; they do not prove the current boot or hardware tests passed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'configure', 'remove', 'status'))
    args = parser.parse_args()
    if args.action != 'status' and os.geteuid() != 0:
        parser.error('run with sudo')
    try:
        support = Support()
        getattr(support, 'preflight' if args.action == 'check' else args.action)()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'rubikpi3-support: {error}\n')


if __name__ == '__main__':
    main()
