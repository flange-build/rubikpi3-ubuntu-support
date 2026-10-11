#!/usr/bin/env python3
"""Isolated boot lifecycle and real fdt transformation regression checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('support', HERE / 'runtime/support.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        share = self.root / 'usr/share/rubikpi3-support'
        share.mkdir(parents=True)
        shutil.copyfile(HERE / 'manifest.json', share / 'manifest.json')
        self.app = s.Support(self.root)
        self.calls = []

        def fake(*args):
            self.calls.append(args)
            if args[0] == 'update-grub':
                s.Support.atomic(self.app.path('/boot/grub/grub.cfg'), b'generated\n')
            return ''
        self.commands = patch.object(s, 'run', side_effect=fake)
        self.commands.start()

    def tearDown(self):
        self.commands.stop()
        self.tmp.cleanup()

    def install_boot(self):
        self.app.publish({s.DTB: (b'dtb', 0o644), s.DEFAULT: self.app.default()})

    def test_configure_repeat_upgrade_and_remove(self):
        self.install_boot()
        self.install_boot()
        self.app.publish({s.DTB: (b'new dtb', 0o644)})
        self.app.remove()
        self.app.remove()
        self.assertFalse(self.app.path(s.DTB).exists())
        self.assertFalse(self.app.path(s.NATIVE).exists())
        self.assertFalse(self.app.path(s.RECOVERY).exists())
        self.assertIn('module_blacklist=', self.app.path(s.DEFAULT).read_text())

    def test_grub_failure_restores_files_and_state(self):
        self.install_boot()
        state = self.app.load_state()
        old_cfg = self.app.path('/boot/grub/grub.cfg').read_bytes()
        def fail(*args):
            if args[0] == 'update-grub':
                s.Support.atomic(self.app.path('/boot/grub/grub.cfg'), b'broken')
            if args[0] == 'grub-script-check':
                raise subprocess.CalledProcessError(1, args)
            return ''
        with patch.object(s, 'run', side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                self.app.publish({s.DTB: (b'bad upgrade', 0o644)})
        self.assertEqual(self.app.path(s.DTB).read_bytes(), b'dtb')
        self.assertEqual(self.app.path('/boot/grub/grub.cfg').read_bytes(), old_cfg)
        self.assertEqual(self.app.load_state(), state)

    def test_first_grub_failure_leaves_no_partial_configuration(self):
        with patch.object(s, 'run', side_effect=RuntimeError('generation failed')):
            with self.assertRaises(RuntimeError):
                self.install_boot()
        self.assertFalse(self.app.path(s.DEFAULT).exists())
        self.assertFalse(self.app.path(s.DTB).exists())

    def test_modified_file_preserved(self):
        self.install_boot()
        self.app.path(s.DTB).write_text('admin edit')
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            self.install_boot()
        self.assertEqual(self.app.path(s.DTB).read_text(), 'admin edit')

    def test_untracked_file_and_symlink_rejected(self):
        target = self.app.path(s.DTB)
        target.parent.mkdir(parents=True)
        target.write_text('not ours')
        with self.assertRaises(RuntimeError):
            self.install_boot()
        target.unlink()
        target.symlink_to(self.root / 'elsewhere')
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            self.install_boot()

    def test_usb_preserves_existing_and_rejects_other_content(self):
        source = self.app.share / 'firmware/renesas_usb_fw.mem'
        source.parent.mkdir()
        source.write_bytes(b'test firmware')
        self.app.manifest['usb_firmware_sha256'] = s.digest(source)
        self.app.ensure_usb()
        self.app.ensure_usb()
        self.app.path(s.USB).write_bytes(b'other firmware')
        with self.assertRaises(RuntimeError):
            self.app.ensure_usb()
        self.assertEqual(self.app.path(s.USB).read_bytes(), b'other firmware')

    def test_standard_config_preserves_other_parameters_and_pins_kernel(self):
        config = self.root / 'grub.cfg'
        config.write_bytes(self.app.default()[0])
        shell = 'GRUB_CMDLINE_LINUX="rootwait msm.separate_gpu_kms=1"; GRUB_CMDLINE_LINUX_DEFAULT="quiet splash deferred_probe_timeout=30 crashkernel=512M"; . "$1"; printf "%s\\n" "$GRUB_DEFAULT" "$GRUB_TOP_LEVEL" "$GRUB_CMDLINE_LINUX" "$GRUB_CMDLINE_LINUX_DEFAULT"'
        result = subprocess.check_output(['sh', '-c', shell, 'sh', str(config)], text=True)
        self.assertIn('/boot/vmlinuz-7.0.0-38-generic', result)
        self.assertIn('rootwait', result)
        self.assertIn('quiet splash', result)
        self.assertIn('crashkernel=512M', result)
        self.assertIn('console=ttyMSM0,115200n8', result)
        self.assertNotIn('separate_gpu_kms=1', result)
        self.assertIn('separate_gpu_kms=0', result)
        self.assertNotIn('deferred_probe_timeout=30', result)
        self.assertEqual(result.count('deferred_probe_timeout=120'), 1)

    def test_serial_console_preserves_existing_settings(self):
        config = self.root / 'grub.cfg'
        config.write_bytes(self.app.default()[0])
        for existing in ('console=tty0', 'console=ttyMSM0,9600n8 console=tty0'):
            shell = ('GRUB_CMDLINE_LINUX_DEFAULT="$2"; . "$1"; . "$1"; '
                     'printf "%s\\n" "$GRUB_TIMEOUT_STYLE" "$GRUB_TIMEOUT" '
                     '"$GRUB_CMDLINE_LINUX" "$GRUB_CMDLINE_LINUX_DEFAULT"')
            result = subprocess.check_output(
                ['sh', '-c', shell, 'sh', str(config), existing], text=True)
            self.assertTrue(result.startswith('menu\n5\n'))
            self.assertEqual(result.count('console=ttyMSM0'), 1)
            self.assertIn(existing, result)

    def test_legacy_migration_and_rollback_preserve_unknown_entries(self):
        name = '/etc/grub.d/42_rubikpi3_native'
        path = self.app.path(name)
        path.parent.mkdir(parents=True)
        path.write_text("menuentry 'native' --id rubikpi3-native {\n}\n")
        unrelated = self.app.path('/etc/grub.d/40_custom')
        unrelated.write_text('unrelated system')
        directory = self.app.path('/boot/dtb')
        directory.mkdir(parents=True)
        old = self.app.path(s.LEGACY_DTBS[0]); old.write_bytes(b'old dtb')
        with patch.object(s, 'run', return_value='thundercomm,rubikpi3'):
            changes = self.app.legacy_changes()
        with patch.object(s, 'run', side_effect=RuntimeError('update failed')):
            with self.assertRaises(RuntimeError):
                self.app.publish({**changes, s.DEFAULT: self.app.default()}, legacy=changes)
        self.assertTrue(path.exists())
        self.assertEqual(old.read_bytes(), b'old dtb')
        self.app.publish({**changes, s.DEFAULT: self.app.default()}, legacy=changes)
        self.assertFalse(path.exists())
        self.assertFalse(directory.exists())
        self.assertEqual(unrelated.read_text(), 'unrelated system')
        self.assertTrue(list(self.app.state.glob('*/etc/grub.d/42_rubikpi3_native')))

    def test_customized_legacy_entry_is_not_deleted(self):
        path = self.app.path('/etc/grub.d/42_rubikpi3_native')
        path.parent.mkdir(parents=True)
        path.write_text("menuentry 'other' --id another-system {}")
        with self.assertRaisesRegex(RuntimeError, 'Unexpected content'):
            self.app.legacy_changes()
        self.assertTrue(path.exists())

    def test_unrecognized_dtb_directory_contents_are_preserved(self):
        directory = self.app.path('/boot/dtb'); directory.mkdir(parents=True)
        (directory / 'other.dtb').write_bytes(b'other')
        with self.assertRaisesRegex(RuntimeError, 'Unrecognized files'):
            self.app.legacy_changes()

    def test_failure_building_modules_keeps_standard_firmware_boot(self):
        source = self.app.path('/sys/firmware/fdt')
        source.parent.mkdir(parents=True)
        source.write_bytes(b'fake fdt')
        def command(*args):
            if args[0] == 'python3':
                Path(args[3]).write_bytes(b'validated native dt')
            return ''
        with patch.object(self.app, 'preflight'), patch.object(self.app, 'ensure_usb'), \
             patch.object(self.app, 'build_modules', side_effect=RuntimeError('DKMS failed')), \
             patch.object(s, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'DKMS failed'):
                self.app.configure()
        self.assertIn('module_blacklist=', self.app.path(s.DEFAULT).read_text())
        self.assertFalse(self.app.path(s.DTB).exists())

    def dkms_registration(self, module, version, broken=False, active=False):
        entry = self.app.path(f'/var/lib/dkms/{module}/{version}')
        entry.mkdir(parents=True)
        source = self.app.path(f'/usr/src/{module}-{version}')
        if not broken:
            source.mkdir(parents=True)
            (source / 'dkms.conf').write_text(f'PACKAGE_NAME="{module}"\n')
        (entry / 'source').symlink_to(source)
        if active:
            (entry.parent / f'kernel-{self.app.kernel}-aarch64').symlink_to(
                f'{version}/{self.app.kernel}/aarch64')
        return entry

    def test_dkms_upgrade_retires_only_managed_old_versions_after_both_installs(self):
        self.app.manifest['dkms'] = dict.fromkeys(s.MANAGED_DKMS, '0.1.1')
        for module in s.MANAGED_DKMS:
            self.dkms_registration(module, '0.1.1', active=True)
        old = self.dkms_registration('rubikpi3-msm', '0.1.0')
        dangling = self.dkms_registration('rubikpi3-lt9611', '0.1.0', broken=True)
        unrelated = self.dkms_registration('other-driver', '0.1.0', broken=True)
        original = old.parent / 'original_module'
        original.mkdir()
        (original / 'stock.ko').write_bytes(b'original')
        def command(*args):
            self.calls.append(args)
            if args[0] == 'modinfo':
                return f'/lib/modules/{self.app.kernel}/updates/dkms/{args[-1]}.ko'
            return ''
        with patch.object(s, 'run', side_effect=command):
            self.app.build_modules()
        builds = [i for i, c in enumerate(self.calls) if c[:2] == ('dkms', 'build')]
        installs = [i for i, c in enumerate(self.calls) if c[:2] == ('dkms', 'install')]
        removes = [i for i, c in enumerate(self.calls) if c[:2] == ('dkms', 'remove')]
        self.assertLess(max(builds), min(installs))
        self.assertLess(max(installs), min(removes))
        self.assertEqual([self.calls[i] for i in removes], [
            ('dkms', 'remove', '-m', 'rubikpi3-msm', '-v', '0.1.0', '--all')])
        self.assertFalse(dangling.exists())
        self.assertTrue(list(self.app.state.glob('retired-dkms-*/rubikpi3-lt9611/0.1.0')))
        self.assertTrue(unrelated.exists())
        self.assertEqual((original / 'stock.ko').read_bytes(), b'original')
        for module in s.MANAGED_DKMS:
            self.assertTrue(self.app.path(f'/var/lib/dkms/{module}/0.1.1').exists())

    def test_dkms_failure_never_retires_old_versions(self):
        self.app.manifest['dkms'] = dict.fromkeys(s.MANAGED_DKMS, '0.1.1')
        old = self.dkms_registration('rubikpi3-msm', '0.1.0', broken=True)
        for failure in ('build', 'install', 'modinfo'):
            with self.subTest(failure=failure):
                calls = []
                def command(*args):
                    calls.append(args)
                    if (args[:2] == ('dkms', failure) and 'rubikpi3-lt9611' in args) or args[0] == failure:
                        raise subprocess.CalledProcessError(1, args)
                    return '/lib/modules/test/updates/dkms/driver.ko' if args[0] == 'modinfo' else ''
                with patch.object(s, 'run', side_effect=command):
                    with self.assertRaises(subprocess.CalledProcessError):
                        self.app.build_modules()
                self.assertTrue(old.exists())
                self.assertFalse(any(c[:2] == ('dkms', 'remove') for c in calls))
                self.assertFalse(list(self.app.state.glob('retired-dkms-*')))
                if failure == 'build':
                    self.assertFalse(any(c[:2] == ('dkms', 'install') for c in calls))

    def test_dkms_upgrade_preserves_old_versions_used_by_other_kernels(self):
        self.app.manifest['dkms'] = dict.fromkeys(s.MANAGED_DKMS, '0.1.1')
        other_kernel = '7.0.0-37-generic'
        for module, broken in zip(s.MANAGED_DKMS, (False, True)):
            self.dkms_registration(module, '0.1.1', active=True)
            old = self.dkms_registration(module, '0.1.0', broken=broken)
            (old.parent / f'kernel-{other_kernel}-aarch64').symlink_to(
                f'0.1.0/{other_kernel}/aarch64')
        self.app.cleanup_modules(keep_current=True)
        self.assertFalse(any(c[:2] == ('dkms', 'remove') for c in self.calls))
        self.assertFalse(list(self.app.state.glob('retired-dkms-*')))
        for module in s.MANAGED_DKMS:
            directory = self.app.path(f'/var/lib/dkms/{module}')
            self.assertTrue((directory / '0.1.0').is_dir())
            self.assertTrue((directory / '0.1.1').is_dir())
            self.assertEqual((directory / f'kernel-{other_kernel}-aarch64').readlink(),
                             Path(f'0.1.0/{other_kernel}/aarch64'))

    def test_remove_cleans_all_managed_versions_and_preserves_active_broken_registration(self):
        for module in s.MANAGED_DKMS:
            for version in ('0.1.0', '0.1.1'):
                self.dkms_registration(module, version)
        unrelated = self.dkms_registration('other-driver', '0.1.0')
        self.app.remove()
        self.assertEqual({c[3:6:2] for c in self.calls if c[:2] == ('dkms', 'remove')},
                         {(m, v) for m in s.MANAGED_DKMS for v in ('0.1.0', '0.1.1')})
        self.assertTrue(unrelated.exists())
        active = self.dkms_registration('rubikpi3-msm', '0.0.9', broken=True, active=True)
        with self.assertRaisesRegex(RuntimeError, 'Preserving active DKMS'):
            self.app.cleanup_modules()
        self.assertTrue(active.exists())
        self.assertFalse(list(self.app.state.glob('retired-dkms-*')))


@unittest.skipUnless(shutil.which('dtc') and shutil.which('fdtget'), 'device-tree-compiler required')
class DeviceTree(unittest.TestCase):
    def test_native_vpu_transform_and_idempotence(self):
        # Synthetic fixture: no real board addresses, calibration or MACs.
        source = '''/dts-v1/;
/ { compatible = "thundercomm,rubikpi3";
    chosen { bootargs = "stale"; rng-seed = <1>; linux,uefi-system-table = <1>;
             framebuffer@0 { status = "okay"; }; };
    smmu: iommu { #iommu-cells = <2>; };
    venus: video-codec { compatible = "qcom,sc7280-venus";
                        iommus = <&smmu 0x2180 0x20>; };
    mdss: display { status = "disabled"; };
    dispcc: clocks { status = "disabled"; };
    lt9611_codec: bridge { status = "disabled"; };
    mdss_dsi: dsi { status = "disabled"; };
    mdss_dsi_phy: phy { status = "disabled"; };
    mdss_dp: dp { status = "okay"; };
    __symbols__ { apps_smmu = "/iommu"; };
};'''
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dts, dtb, result = tmp / 'in.dts', tmp / 'in.dtb', tmp / 'out.dtb'
            dts.write_text(source)
            subprocess.run(['dtc', '-q', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(dtb), str(dts)], check=True)
            for name in ('rubikpi3-native-display', 'rubikpi3-vpu'):
                args = ['python3', str(HERE / 'components' / name / 'prepare-dtb.py'), str(dtb), str(result)]
                if name.endswith('vpu'): args.append('--el2')
                subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
                shutil.copyfile(result, dtb)
            before = result.read_bytes()
            subprocess.run(['python3', str(HERE / 'components/rubikpi3-vpu/prepare-dtb.py'), str(result), str(result), '--el2'], check=True, stdout=subprocess.DEVNULL)
            self.assertEqual(before, result.read_bytes())
            def get(*args):
                return subprocess.check_output(['fdtget', str(result), *args], text=True).strip()
            self.assertEqual(get('/display', 'status'), 'okay')
            self.assertEqual(get('/dp', 'status'), 'disabled')
            self.assertNotIn('bootargs', get('-p', '/chosen'))
            self.assertNotIn('framebuffer', get('-l', '/chosen'))
            self.assertEqual(get('-t', 'x', '/video-codec/video-firmware', 'iommus').split()[-2:], ['21a2', '0'])
            self.assertEqual(get('-t', 'x', '/video-codec', 'iommus').split()[1::3], ['2180', '2184'])
            subprocess.run(['fdtput', '-t', 's', str(result), '/', 'compatible', 'wrong,board'], check=True)
            rejected = subprocess.run(['python3', str(HERE / 'components/rubikpi3-vpu/prepare-dtb.py'), str(result), str(result), '--el2'], capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)


if __name__ == '__main__':
    unittest.main()
