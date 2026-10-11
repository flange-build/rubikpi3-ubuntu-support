# RubikPi3 原生 HDMI

**简体中文** | [English](README.en.md)

用于已安装的 Ubuntu ARM64：由 Linux MSM DPU → DSI0 → LT9611 B 输入 → HDMI
接管显示，Adreno 提供渲染。原生输出应出现 `HDMI-A-1`、`msmdrmfb` 和硬件 vblank。
UEFI 自带的安装器兼容设备树不变；启动时可能短暂出现 EFI 帧缓冲，原生 MSM 随后移除它。

本目录包含 LT9611 的单 B 输入、熄屏后 I²C 地址保持补丁及板级 DTB 生成工具。
GPU 仍需 [MSM EL2 DKMS](../rubikpi3-msm-dkms/README.md)。当前仅针对
Ubuntu `7.0.0-38-generic`；不能把“已编译”当作其他内核、显示模式或热插拔已通过验证。

## 构建和安装桥驱动

从 Ubuntu `linux-source-7.0.0=7.0.0-38.38` 提取
`drivers/gpu/drm/bridge/lontium-lt9611.c` 后执行：

```sh
python3 build-package.py /path/to/lontium-lt9611.c --output dist
sudo apt install ./dist/rubikpi3-lt9611-dkms_0.1.1_arm64.deb
dkms status
modinfo -n lontium_lt9611
```

脚本检查原始 C 文件 SHA256：
`3371c76faaf71804e4da817e5767a7256216f708c4613f1fcc0f40ea117c1461`。
构建主机需 Python 3、patch、dpkg-deb 和 `/usr/share/common-licenses/GPL-2`；
目标设备需当前内核 headers。GPL-2.0-only；原文件保留原作者版权。

补丁保留设备树真实的 `port@1` 接线，将唯一 B 输入作为主 DSI，并设置
`0x8250=0x14`、`0x8303[6]=1`；A 输入及 A+B 双输入的原有路径保持不变。
寄存器设置与本项目已验证的 UEFI LT9611 B 输入配置一致。
熄屏补丁回移[上游提交的修复](https://lore.kernel.org/all/20260127-rubikpi-next-20260116-bugfix-v1-1-46e3396533ac@thundersoft.com/)，
保留 MIPI/PHY 省电操作，去掉会导致唤醒后通信失败的 I²C 地址与 GPIO 改写。

若此前手工安装过 `updates/rubikpi3-native/lontium-lt9611.ko`，先移到备份目录，
再运行 `depmod` 和安装 DKMS 包，避免两个模块竞争。不要在线卸载 MSM 或显示桥驱动。

## 准备本机设备树和启动项

UEFI 须提供 `/chosen/flange,display-fixup-version = <1>` 或更新能力，确保 GRUB
加载的帧缓冲模板会在本次启动正确填充；旧版固件须先升级并重启。

```sh
sudo cp /sys/firmware/fdt ./firmware-original.dtb
sudo python3 prepare-dtb.py firmware-original.dtb /boot/dtb/rubikpi3-native.dtb
```

该工具要求本项目固件提供的 RubikPi3 FDT（含符号），保留内存、MAC、ICE/GPI
启动修复及供电设置，启用 HDMI 链路、禁用尚未验证的 USB-C DP。旧帧缓冲替换为
零地址的 disabled 模板，保留显示时钟/电源引用；UEFI DT fixup 按本次 GOP 填充，
供 simpledrm 持有资源直到原生 MSM 接管。上次启动的 EFI 地址/熵会删除。
生成的 DTB 属于本机，不应复制到其他设备。

可使用本目录的安装工具自动生成独立 GRUB 启动项，并安排下一次单次测试启动：

```sh
sudo python3 install-boot-profile.py
sudo reboot
# 确认画面、USB、GPU 正常后，将此启动项设为默认：
sudo python3 install-boot-profile.py --make-default
```

工具在 `/var/lib/rubikpi3-native-display/` 备份原文件，自动识别根分区 UUID、
生成本机 DTB、更新 dracut initramfs，保留原 Ubuntu 启动项。默认项配置位于
`/etc/default/grub.d/99-rubikpi3-native.cfg`，菜单显示 5 秒方便回退。
原生启动项固定使用本次选择的内核；内核升级后应明确指定 `--kernel` 重新测试，
不会未经验证自动切换到新的 ABI。该安装工具当前要求 dracut。

Linux 从 EL2 启动时，可增加 `--vpu-el2` 创建同时启用原生 HDMI 和 VPU 的独立入口。
安装前请阅读 [VPU 文档](../rubikpi3-vpu/README.md)，了解固件要求、已验证的编码参数和回退方式。

独立 GRUB 启动项加载此 DTB 和已更新的 Ubuntu initramfs，并使用
`msm.separate_gpu_kms=0 deferred_probe_timeout=120`。前者启用统一的渲染与显示设备；
后者避免内核默认等待时间到期时 GPU SMMU 的依赖尚未加载。根分区 UUID、内核路径
必须使用本机值。先通过 `grub-reboot` 单次测试，确认后再设为默认，保留原 Ubuntu 启动项。

板载 Renesas USB 控制器还需要 `/usr/lib/firmware/renesas_usb_fw.mem`。本机从
只读挂载的 `usb_fw` 分区复制，SHA256 为
`177560c224c73d040836b17082348036430ecf59e8a32d7736ce2b80b2634f97`。
它没有包含在 DKMS 包中；应在启动镜像内包含它，否则 USB 键鼠和网卡可能不出现。

## 检查与回退

```sh
cat /sys/class/graphics/fb0/name
ls /sys/class/drm
sudo journalctl -k -b | grep -E 'lt9611|msm_dpu|dpu|fault|timeout'
```

应看到 `msmdrmfb`、`HDMI-A-1` 和 GNOME 使用 MSM。仍须实际移动窗口检查画面；
仅枚举连接器不能证明 HDMI 图像正确。实机结果和限制见本仓库 `VALIDATION.md`。

回退时先选原 Ubuntu 启动项（固件 DTB + `separate_gpu_kms=1`），确认恢复后再
移走 `/etc/default/grub.d/99-rubikpi3-native.cfg` 和 `/etc/grub.d/42_rubikpi3_native`，
运行 `sudo update-grub`，再卸载 `rubikpi3-lt9611-dkms`。卸载会恢复原版桥驱动并更新 initramfs，但不会自动
删除自行创建的 GRUB 启动项；原版桥驱动不支持此板的单 B 输入。
