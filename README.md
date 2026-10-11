# RubikPi3 Ubuntu 支持包

**简体中文** | [English](README.en.md)

把官方 Ubuntu 上已验证的 RubikPi3 适配集中为一个
`rubikpi3-ubuntu-support_0.1.0_arm64.deb`。包含内核代码补丁，也包含固件选择、
设备树生成、模块参数、initramfs 和 GRUB 部署逻辑。
构建不依赖 EDK2 源码或构建产物。

当前范围为 **Ubuntu 26.04 ARM64、7.0.0-38-generic、RubikPi3、EL2/VHE**，
需要能正确启动官方 Ubuntu 的 edk2-flange UEFI（含带符号的板级 FDT，Secure Boot 关闭）。
不是任意 Ubuntu 版本、任意固件的通用安装包；不会刷写 UEFI、TrustZone 或 UFS 分区。
完整清单和 UEFI 分工见 [PATCHES.md](PATCHES.md)。

## 包含内容

| 功能 | 包内实现 |
| --- | --- |
| Adreno GPU | MSM EL2 SECVID 补丁，源码 DKMS，使用发行版 Mesa |
| 原生 HDMI | LT9611 单 B 输入 DKMS、启用 DPU/DSI/桥的本机 DTB |
| VPU | EL2 固件流 IOMMU 描述，使用发行版原版 Venus，无 VPU DKMS |
| AP6256 Wi-Fi | 板级固件/CLM/NVRAM，移除样例 MAC，使用原版 brcmfmac |
| Renesas USB | 校验并部署本机 USB 固件，加入启动镜像 |
| 启动集成 | dracut/initramfs-tools 钩子，固定已验证内核，独立默认和恢复项 |

`components/` 包含四组补丁、工具和实验记录，支持按组件独立构建。
统一构建只复用它们的有效负载，不嵌套安装 deb、不运行旧维护脚本。

## 构建一个 deb

构建主机可为 x86_64，需要 Python 3.11+、dpkg-deb、patch、tar/bzip2 支持及系统 GPL-2 文本。
内核模块在目标 ARM64 设备安装时编译。准备：

1. Ubuntu `linux-source-7.0.0_7.0.0-38.38_all.deb`，脚本检查固定 SHA256。
2. [Wi-Fi 原始文件](components/rubikpi3-wifi-firmware/README.md)三个，保留原始文件名。
3. 设备 `usb_fw` 分区提供的 `renesas_usb_fw.mem`，已验证设备也可从
   `/usr/lib/firmware/renesas_usb_fw.mem` 取出；脚本检查固定 SHA256。

```sh
python3 build-package.py /path/to/linux-source-7.0.0_7.0.0-38.38_all.deb \
  --wifi-firmware /path/to/vendor-wifi \
  --usb-firmware /path/to/renesas_usb_fw.mem \
  --output dist
```

输出一个 deb 和 SHA256 文件。源码、固件从本地输入构建，构建脚本不下载文件。
生成包包含厂商固件，仅供当前本地安装；现有原始下载未附明确再分发授权，不能把
打包脚本的 GPL 当作固件授权。发布二进制包前需确认相应固件许可，详见 [copyright](copyright)。
不会把本机 DTB、MAC、EFI 内存地址、密码或 SSH 配置放进包里。

## 安装

先以官方 Ubuntu 的 `7.0.0-38-generic` 内核启动本机，然后：

```sh
sudo apt install ./dist/rubikpi3-ubuntu-support_0.1.0_arm64.deb
sudo rubikpi3-support status
sudo reboot
```

APT 安装明确的内核/headers、DKMS、系统 Qualcomm 图形固件和 Mesa 等依赖。
本包替代旧 `rubikpi3-msm-dkms`、`rubikpi3-lt9611-dkms`、`rubikpi3-wifi-firmware`，
不能同时安装；也与已知不适合该主线方案的 `qcom-adreno1`、`kgsl-dkms` 冲突。
首次安装需要取得依赖，单个 deb 不代表所有 Ubuntu 依赖都已离线打包。

安装会检查板型、Ubuntu 版本、当前内核、EL2/VHE、头文件、系统固件和模块来源。
先生成并验证本机 DTB，再建立 firmware display recovery 启动项，构建两个 DKMS，
更新 initramfs，最后将 **Ubuntu - RubikPi3 native HDMI + GPU + VPU (EL2)** 设为默认。
GRUB 显示 5 秒。只清理旧 RubikPi3 的单次启动选择，不清理其他系统的启动选择。
脚本不会在线卸载驱动或自动重启。失败会让 dpkg 配置失败，可修复原因后用
`sudo dpkg --configure -a` 重试；不要忽略安装错误直接重启。

持久配置和备份放在 `/var/lib/rubikpi3-support/`。安装前的板级 Wi-Fi 文件备份在
`/var/lib/rubikpi3-pre-unpack.*`。旧手工 native/VPU 项不会被删掉。
本包生成的文件若被管理员修改，后续操作会报告路径并停止，避免静默覆盖。
不同内容的 USB 固件或手工 `.ko` 覆盖也必须先处理。

## 验证和内核升级

```sh
uname -r
dkms status
cat /sys/class/graphics/fb0/name
nmcli device status
v4l2-ctl --list-devices
sudo apt install ffmpeg v4l-utils gstreamer1.0-tools gstreamer1.0-plugins-good
python3 /usr/share/rubikpi3-support/test-codecs.py ./vpu-results --size 1920x1080
```

硬件验证范围和包测试范围分别记录在 [VALIDATION.md](VALIDATION.md)。
维护者可执行 `python3 -m unittest discover -s tests -v` 和
`python3 tests/check-deb.py dist/rubikpi3-ubuntu-support_0.1.0_arm64.deb` 复查包逻辑。
安装成功不等于完成硬件验收。当前编码使用 GStreamer 并明确指定 Profile/Level，
FFmpeg 硬件编码存在段错误，详情见 [VPU 文档](components/rubikpi3-vpu/README.md)。

本包只构建 `7.0.0-38-generic` 的 DKMS，并把默认启动项固定到该内核。
APT 可安装更新内核，但不会自动把该项切换到未经验证的 ABI；新增内核需更新
manifest、源码校验、DKMS 限制、维护脚本并重新验证、发布支持包。
不承诺跨 ABI 兼容，也不自动修改或禁用 Ubuntu 的更新源。

## 回退与卸载

在 GRUB 选择 **Ubuntu - RubikPi3 firmware display recovery**：不加载本包 DTB，
使用 UEFI 提供的安装器兼容显示并禁止 GPU/桥/VPU 模块，保留恢复所需的 USB。
该路径依赖 edk2-flange 固件的兼容 FDT，首版统一包尚需实机启动验收。

```sh
sudo apt remove rubikpi3-ubuntu-support
```

卸载先将默认项改为 firmware display recovery，再移除本包 native 项和两个 DKMS，
重建 initramfs。Wi-Fi 固件随包移除，发行版未提供等效固件时 Wi-Fi 将不可用。
为避免旧手工默认项引用已卸载的驱动，**恢复项、恢复默认配置、备份及已部署的 USB
固件在 remove/purge 后保留**；这不是逐字恢复所有历史手工配置。
确认其他启动项可用后，可手工移走 `/etc/grub.d/41_rubikpi3_firmware_recovery` 和
`/etc/default/grub.d/zz-rubikpi3-support.cfg`，再执行 `sudo update-grub`。
不卸载 Mesa、Ubuntu 固件或内核，不恢复旧实验驱动。
