# RubikPi3 Wi-Fi firmware package

[简体中文](README.md) | **English**

`rubikpi3-wifi-firmware` packages the validated AP6256 / BCM43456 firmware for
Thundercomm RubikPi3 and the kernel's existing `brcmfmac` driver. This is a firmware
`.deb`: no DKMS, kernel headers or compiler is required. Firmware remains installed
across kernel upgrades and initramfs hooks include it in newly generated images.
Compatibility with future kernels still needs validation. UEFI, GRUB, GPU and
Bluetooth configuration are unchanged.

## Build

Obtain the original `brcmfmac43456-sdio.bin`, `.clm_blob` and `.txt` files from the
[vendor share](https://pan.thundersoft.com/web/share.html?hash=KchzIWzgSnU) linked in
section 4.3 of the [RubikPi mainline guide](https://community.rubikpi.ai/t/mainline-linux-running-mainline-linux-on-rubik-pi-3/439).
Keep them in one directory. The builder checks the pinned SHA256 values listed in
the [Chinese README](README.md) and in `build-package.py`; it does not download files.

```sh
python3 build-package.py /path/to/vendor-firmware --output dist
```

The build host needs Python 3 and `dpkg-deb`; x86_64 is supported. The output is
`dist/rubikpi3-wifi-firmware_0.1.0_all.deb`, containing data and scripts only.
Firmware binaries are not committed to Git. The downloads include no explicit
redistribution license; obtain vendor permission before publishing generated packages.
The packaging scripts' GPL-2.0-only license does not apply to the firmware.

## Install and check

```sh
sudo apt install ./dist/rubikpi3-wifi-firmware_0.1.0_all.deb
sudo reboot
nmcli device status
nmcli device wifi list --rescan yes
sudo journalctl -k -b | grep -E 'brcmfmac|brcmf_|mmc'
```

The files are installed under `/usr/lib/firmware/brcm/` as
`brcmfmac43456-sdio.thundercomm,rubikpi3.{bin,clm_blob,txt}`. The board identifier
selects them without replacing distribution-wide generic firmware. Only the active
sample `macaddr=` entry is removed from NVRAM so the platform can supply the address;
calibration values remain unchanged. Do not substitute another board's NVRAM.

Installation and removal regenerate all existing initramfs images. Both dracut
configuration and an initramfs-tools hook are included; see [validation](VALIDATION.md)
for the tested configuration. Maintainer scripts do not unload the running driver,
reboot, connect to an access point, or change NetworkManager settings.

If migrating from the project's manual fix, back up the three firmware files and
`/etc/dracut.conf.d/91-rubikpi3-wifi-firmware.conf`, then move that old configuration
out of the active directory. The package may take ownership of the same board `.txt`
path: back up custom calibration first. The manual generic `.bin` and `.clm_blob`
are not managed by this package; move them to backup only after checking they are
not owned by another package. Do not reboot until installation and initramfs updates succeed.

## Remove

```sh
sudo apt remove rubikpi3-wifi-firmware
sudo reboot
```

Removal deletes the packaged firmware and hooks and regenerates initramfs. Wi-Fi
will be unavailable after reboot if no other package supplies suitable firmware;
reinstall over Ethernet if needed. Manual backups are not restored automatically.
Firmware does not appear in `dkms status`, which lists actual DKMS modules such as MSM.
