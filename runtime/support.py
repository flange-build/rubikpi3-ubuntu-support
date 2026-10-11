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
DTB = '/boot/dtb-7.0.0-38-generic'
USB = '/usr/lib/firmware/renesas_usb_fw.mem'
MANAGED_DKMS = ('rubikpi3-msm', 'rubikpi3-lt9611')
LEGACY_ENTRIES = {
    '/etc/grub.d/42_rubikpi3_native': 'rubikpi3-native',
    '/etc/grub.d/43_rubikpi3_native_vpu': 'rubikpi3-native-vpu',
    '/etc/grub.d/43_rubikpi3_vpu_test': 'rubikpi3-vpu-test',
    NATIVE: 'rubikpi3-ubuntu-support',
    RECOVERY: 'rubikpi3-ubuntu-firmware',
}
LEGACY_DTBS = tuple('/boot/dtb/' + name for name in (
    'rubikpi3-native-test.dtb', 'rubikpi3-native.dtb', 'rubikpi3-native-vpu.dtb',
    'rubikpi3-vpu-test.dtb', 'rubikpi3-ubuntu-support.dtb'))
LEGACY_DEFAULT = '/etc/default/grub.d/99-rubikpi3-native.cfg'


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
        self.check_managed((DEFAULT, DTB))
        self.legacy_changes()
        generator = self.path('/etc/grub.d/10_linux').read_text()
        if 'GRUB_TOP_LEVEL' not in generator or '"dtb-${version}"' not in generator:
            raise RuntimeError('Unsupported GRUB Linux generator: missing kernel priority or per-kernel DT support')
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
        # Finish both builds before replacing either installed driver.
        for module, version in self.manifest['dkms'].items():
            run('dkms', 'install', '--force', '-m', module, '-v', version, '-k', self.kernel)
        run('depmod', '-a', self.kernel)
        for module in ('msm', 'lontium_lt9611'):
            if '/updates/dkms/' not in run('modinfo', '-k', self.kernel, '-n', module):
                raise RuntimeError(f'DKMS module did not take precedence: {module}')
        self.cleanup_modules(keep_current=True)

    def cleanup_modules(self, keep_current=False):
        """Retire only this package's registrations, after replacements succeed."""
        for module in MANAGED_DKMS:
            directory = self.path(f'/var/lib/dkms/{module}')
            if directory.is_symlink():
                raise RuntimeError(f'Preserving symlinked DKMS directory: {directory}')
            if not directory.is_dir():
                continue
            current = self.manifest['dkms'].get(module)
            if keep_current and current is None:
                continue
            for entry in sorted(directory.iterdir()):
                # Skip kernel-* activation links, original_module backups and
                # unrelated metadata, not just the version listed by manifest.
                if (entry.is_symlink() or not entry.is_dir() or
                        not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]*', entry.name) or
                        keep_current and entry.name == current):
                    continue
                active = any(link.is_symlink() and link.resolve().is_relative_to(entry.resolve())
                             for link in directory.glob('kernel-*'))
                # An upgrade replaces only the tested kernel's modules. Keep
                # registrations still used by another installed kernel, even
                # if dpkg has already removed their source directory.
                if keep_current and active:
                    print(f'Keeping DKMS version used by an installed kernel: {module}/{entry.name}')
                    continue
                source = entry / 'source'
                if source.is_symlink() and (source / 'dkms.conf').is_file():
                    run('dkms', 'remove', '-m', module, '-v', entry.name, '--all')
                    continue
                # dpkg can remove the old /usr/src before our new postinst.
                # DKMS refuses a broken source link. Only archive an inactive
                # registration; never discard evidence of an installed driver.
                if active:
                    raise RuntimeError(f'Preserving active DKMS version with missing source: {module}/{entry.name}')
                self.state.mkdir(parents=True, exist_ok=True)
                backup = Path(tempfile.mkdtemp(prefix='retired-dkms-', dir=self.state))
                destination = backup / module / entry.name
                destination.parent.mkdir()
                shutil.move(str(entry), str(destination))
                print(f'Inactive DKMS registration backed up: {destination}')

    def legacy_changes(self):
        """Recognize only our old entries; never delete arbitrary custom menus."""
        changes = {}
        for name, ident in LEGACY_ENTRIES.items():
            path = self.path(name)
            if path.is_symlink():
                raise RuntimeError(f'Preserving legacy symlink: {name}')
            if not path.exists():
                continue
            text = path.read_text()
            ids = re.findall(r'--id[ =]+([A-Za-z0-9_-]+)', text)
            if ids != [ident] or len(re.findall(r'^menuentry ', text, re.M)) != 1:
                raise RuntimeError(f'Unexpected content in legacy entry: {name}')
            changes[name] = None
        path = self.path(LEGACY_DEFAULT)
        if path.exists():
            lines = [x.strip() for x in path.read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]
            if not all(re.fullmatch(r'GRUB_(DEFAULT|TIMEOUT_STYLE|TIMEOUT)=[A-Za-z0-9_"\'-]+', x) for x in lines):
                raise RuntimeError(f'Preserving customized legacy configuration: {LEGACY_DEFAULT}')
            if not any(re.fullmatch(r'GRUB_DEFAULT=["\']?rubikpi3-[A-Za-z0-9_-]+["\']?', x) for x in lines):
                raise RuntimeError('Legacy default no longer points to RubikPi3; preserving it')
            changes[LEGACY_DEFAULT] = None
        for name in LEGACY_DTBS:
            path = self.path(name)
            if path.is_symlink():
                raise RuntimeError(f'Preserving legacy symlink: {name}')
            if path.exists():
                if 'thundercomm,rubikpi3' not in run('fdtget', str(path), '/', 'compatible').split():
                    raise RuntimeError(f'Not a RubikPi3 DTB: {name}')
                changes[name] = None
        directory = self.path('/boot/dtb')
        if directory.is_dir() and any('/' + str(p.relative_to(self.root)) not in changes for p in directory.iterdir()):
            raise RuntimeError('Unrecognized files in /boot/dtb; preserving them. GRUB treats this directory as a DTB')
        return changes

    def publish(self, changes, legacy=()):
        """Back up generated files and restore them if GRUB generation fails."""
        self.check_managed(set(changes) - set(legacy))
        self.state.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),
                                      dir=self.state))
        old = {}
        old_directory = self.path('/boot/dtb')
        directory_mode = old_directory.stat().st_mode & 0o777 if old_directory.is_dir() else None
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
            if old_directory.is_dir() and not any(old_directory.iterdir()):
                old_directory.rmdir()
            run('update-grub')
            run('grub-script-check', '/boot/grub/grub.cfg')
            self.save_state(state)
        except Exception:
            if directory_mode is not None:
                old_directory.mkdir(parents=True, exist_ok=True)
                old_directory.chmod(directory_mode)
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

    def default(self, native=True):
        config = f'''# Managed by rubikpi3-ubuntu-support. Standard Ubuntu entry, tested kernel first.
GRUB_DEFAULT=0
GRUB_TOP_LEVEL="/boot/vmlinuz-{self.kernel}"
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=5
case " ${{GRUB_CMDLINE_LINUX:-}} ${{GRUB_CMDLINE_LINUX_DEFAULT:-}} " in
    *" console=ttyMSM0,"*|*" console=ttyMSM0 "*) ;;
    *) GRUB_CMDLINE_LINUX="console=ttyMSM0,115200n8 ${{GRUB_CMDLINE_LINUX:-}}" ;;
esac
'''
        if native:
            # Drop only the two parameters we own, leaving other distribution
            # settings (including quiet/splash and crashkernel) intact.
            clean = "sed -E 's/(^|[[:space:]])msm[.]separate_gpu_kms=[^[:space:]]*//g; s/(^|[[:space:]])deferred_probe_timeout=[^[:space:]]*//g'"
            for variable in ('GRUB_CMDLINE_LINUX', 'GRUB_CMDLINE_LINUX_DEFAULT'):
                config += f'{variable}=$(printf "%s" "${{{variable}:-}}" | {clean})\n'
            config += 'GRUB_CMDLINE_LINUX="${GRUB_CMDLINE_LINUX} msm.separate_gpu_kms=0 deferred_probe_timeout=120"\n'
        else:
            # Firmware display fallback uses the ordinary Ubuntu entry too.
            # Preserve unrelated module blacklists from the administrator.
            config += '''_rubikpi3_blacklist=msm,lontium_lt9611,venus_core,venus_enc,venus_dec
for _rubikpi3_arg in ${GRUB_CMDLINE_LINUX:-} ${GRUB_CMDLINE_LINUX_DEFAULT:-}; do
    case "$_rubikpi3_arg" in
        module_blacklist=*) _rubikpi3_blacklist="${_rubikpi3_blacklist},${_rubikpi3_arg#*=}" ;;
    esac
done
GRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX_DEFAULT:-} module_blacklist=${_rubikpi3_blacklist}"
unset _rubikpi3_blacklist _rubikpi3_arg
'''
        return config.encode(), 0o644

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
        cleanup = self.legacy_changes()
        # Before the initial build, restore the ordinary firmware-backed Ubuntu
        # route. If DKMS fails, no obsolete custom entry is left as default.
        if DTB not in self.load_state():
            self.publish({**cleanup, DEFAULT: self.default(False)}, legacy=cleanup)
        self.build_modules()
        run('update-initramfs', '-u', '-k', self.kernel)
        self.publish({**cleanup, DTB: (data, 0o644), DEFAULT: self.default()}, legacy=cleanup)
        env = run('grub-editenv', '/boot/grub/grubenv', 'list')
        for line in env.splitlines():
            if line.startswith('next_entry=rubikpi3'):
                run('grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry')
        print(f'Ubuntu now defaults to the adapted {self.kernel} profile. Reboot when ready.')

    def remove(self):
        # Return standard Ubuntu to firmware DT, with unsafe graphics/media
        # probing disabled until a replacement support package is installed.
        state = self.load_state()
        if DEFAULT in state or DTB in state:
            cleanup = self.legacy_changes()
            self.publish({**cleanup, DTB: None, DEFAULT: self.default(False)}, legacy=cleanup)
            env = run('grub-editenv', '/boot/grub/grubenv', 'list')
            if any(x.startswith('next_entry=rubikpi3') for x in env.splitlines()):
                run('grub-editenv', '/boot/grub/grubenv', 'unset', 'next_entry')
        self.cleanup_modules()
        # Keep validated USB firmware for recovery and SSH. It was either
        # already present or copied by ensure_usb, never owned by dpkg here.
        print('Standard Ubuntu restored to firmware display. USB firmware and backups retained.')

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
