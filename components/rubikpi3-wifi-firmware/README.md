# RubikPi3 Wi-Fi 固件包

**简体中文** | [English](README.en.md)

将已验证的 AP6256 / BCM43456 固件封装为 `rubikpi3-wifi-firmware`，用于
Thundercomm RubikPi3 的内核自带 `brcmfmac` 驱动。这是固件 `.deb`，无需 DKMS、
内核头文件或编译器；内核升级后文件仍保留，initramfs 钩子会继续打包固件。
新内核兼容性仍需验证。本包不更改 UEFI、GRUB、GPU 或蓝牙。

## 构建

从 [RubikPi 主线指南第 4.3 节](https://community.rubikpi.ai/t/mainline-linux-running-mainline-linux-on-rubik-pi-3/439)
的 [厂商固件分享](https://pan.thundersoft.com/web/share.html?hash=KchzIWzgSnU)
取得以下三个原始文件，并放在同一个目录。构建脚本离线验证 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `brcmfmac43456-sdio.bin` | `ddf83f2100885b166be52d21c8966db164fdd4e1d816aca2acc67ee9cc28d726` |
| `brcmfmac43456-sdio.clm_blob` | `2dbd7d22fc9af0eb560ceab45b19646d211bc7b34a1dd00c6bfac5dd6ba25e8a` |
| `brcmfmac43456-sdio.txt` | `44e0bb322dc1f39a4b0a89f30ffdd28bc93f7d7aaf534d06d229fe56f6198194` |

```sh
python3 build-package.py /path/to/vendor-firmware --output dist
```

构建主机需要 Python 3 和 `dpkg-deb`，可使用 x86_64 主机。输出为
`dist/rubikpi3-wifi-firmware_0.1.0_all.deb`（仅包含数据和脚本）。
固件二进制不纳入 Git；原始下载没有附带明确的再分发许可，发布生成包前需取得厂商许可。
打包脚本为 GPL-2.0-only，不改变固件的许可。

## 安装与验证

```sh
sudo apt install ./dist/rubikpi3-wifi-firmware_0.1.0_all.deb
sudo reboot
nmcli device status
nmcli device wifi list --rescan yes
sudo journalctl -k -b | grep -E 'brcmfmac|brcmf_|mmc'
```

三个文件安装在 `/usr/lib/firmware/brcm/`，名称均为
`brcmfmac43456-sdio.thundercomm,rubikpi3.{bin,clm_blob,txt}`。
内核根据设备树 `thundercomm,rubikpi3` 选择板级固件，避免覆盖发行版通用文件。
NVRAM 仅删除厂商样例中的活动 `macaddr=` 行，使用平台提供的地址；其余校准数据不变。
不要将其他开发板的 NVRAM 校准文件替换进来。

安装和卸载会更新所有已有 initramfs；包同时提供 dracut 配置和 initramfs-tools
钩子，实机验证范围见 [验证记录](VALIDATION.md)。脚本不会在线卸载驱动、重启设备、
连接接入点或更改 NetworkManager 配置。

若曾使用本项目早期手工修复，先备份三个手工固件及
`/etc/dracut.conf.d/91-rubikpi3-wifi-firmware.conf`，再移走该旧配置。
安装包可能接管同名的板级 `.txt`；不要在未备份时覆盖自己的校准文件。
手工通用 `.bin` / `.clm_blob` 不由本包管理，确认不属于其他软件包后可移到备份目录。
在软件包安装和 initramfs 更新成功前不要重启。

## 卸载

```sh
sudo apt remove rubikpi3-wifi-firmware
sudo reboot
```

卸载移除本包的固件和钩子，并重新生成 initramfs。若发行版仍未提供对应固件，
下一次启动 Wi-Fi 将不可用；可以通过以太网重新安装此包。卸载不会自动恢复手工备份。
Wi-Fi 固件无需出现在 `dkms status` 中；该命令只列出 GPU 等实际 DKMS 模块。
