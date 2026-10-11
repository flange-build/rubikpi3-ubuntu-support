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
        self.app.publish({s.NATIVE: (b'native', 0o755), s.RECOVERY: (b'recovery', 0o755),
                          s.DTB: (b'dtb', 0o644), s.DEFAULT: self.app.default(s.NATIVE_ID)})

    def test_configure_repeat_upgrade_and_remove(self):
        self.install_boot()
        self.install_boot()
        self.app.publish({s.NATIVE: (b'new native', 0o755)})
        self.app.remove()
        self.app.remove()  # retrying prerm is safe
        self.assertFalse(self.app.path(s.DTB).exists())
        self.assertFalse(self.app.path(s.NATIVE).exists())
        self.assertEqual(self.app.path(s.RECOVERY).read_bytes(), b'recovery')
        self.assertIn(s.RECOVERY_ID, self.app.path(s.DEFAULT).read_text())

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
                self.app.publish({s.NATIVE: (b'bad upgrade', 0o755)})
        self.assertEqual(self.app.path(s.NATIVE).read_bytes(), b'native')
        self.assertEqual(self.app.path('/boot/grub/grub.cfg').read_bytes(), old_cfg)
        self.assertEqual(self.app.load_state(), state)

    def test_first_grub_failure_leaves_no_partial_entry(self):
        with patch.object(s, 'run', side_effect=RuntimeError('generation failed')):
            with self.assertRaises(RuntimeError):
                self.install_boot()
        self.assertFalse(self.app.path(s.DEFAULT).exists())
        self.assertFalse(self.app.path(s.NATIVE).exists())

    def test_modified_file_preserved(self):
        self.install_boot()
        self.app.path(s.NATIVE).write_text('admin edit')
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            self.install_boot()
        self.assertEqual(self.app.path(s.NATIVE).read_text(), 'admin edit')

    def test_missing_recovery_prevents_removing_working_native_profile(self):
        self.install_boot()
        self.app.path(s.RECOVERY).unlink()
        with self.assertRaisesRegex(RuntimeError, 'Recovery entry is missing'):
            self.app.remove()
        self.assertTrue(self.app.path(s.NATIVE).is_file())
        self.assertIn(s.NATIVE_ID, self.app.path(s.DEFAULT).read_text())

    def test_untracked_file_and_symlink_rejected(self):
        target = self.app.path(s.NATIVE)
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
        self.assertEqual(self.app.path(s.USB).read_bytes(), source.read_bytes())
        self.app.path(s.USB).write_bytes(b'other firmware')
        with self.assertRaises(RuntimeError):
            self.app.ensure_usb()
        self.assertEqual(self.app.path(s.USB).read_bytes(), b'other firmware')

    def test_boot_entries_for_separate_boot_filesystem(self):
        def command(*args):
            if args[0] == 'findmnt': return 'abcd-1234'
            if args[0] == 'grub-probe': return 'ffff-5555'
            if args[0] == 'grub-mkrelpath': return args[1].removeprefix('/boot')
            raise AssertionError(args)
        with patch.object(s, 'run', side_effect=command):
            native, recovery = self.app.boot_entries()
        self.assertIn(b'devicetree /dtb/rubikpi3-ubuntu-support.dtb', native)
        self.assertIn(b'root=UUID=abcd-1234', native)
        self.assertIn(b'--set=root ffff-5555', native)
        self.assertNotIn(b'devicetree ', recovery)
        self.assertIn(b'module_blacklist=', recovery)
        self.assertIn(b'linux /vmlinuz-7.0.0-38-generic', recovery)

    def test_failure_building_modules_keeps_recovery_default(self):
        source = self.app.path('/sys/firmware/fdt')
        source.parent.mkdir(parents=True)
        source.write_bytes(b'fake fdt')
        def command(*args):
            if args[0] == 'python3':
                Path(args[3]).write_bytes(b'validated native dt')
            return ''
        with patch.object(self.app, 'preflight'), patch.object(self.app, 'ensure_usb'), \
             patch.object(self.app, 'boot_entries', return_value=(b'native', b'recovery')), \
             patch.object(self.app, 'build_modules', side_effect=RuntimeError('DKMS failed')), \
             patch.object(s, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'DKMS failed'):
                self.app.configure()
        self.assertIn(s.RECOVERY_ID, self.app.path(s.DEFAULT).read_text())
        self.assertFalse(self.app.path(s.NATIVE).exists())


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
