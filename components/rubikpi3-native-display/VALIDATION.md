# 原生 HDMI 实机验证 / Native HDMI validation

## 简体中文

2026-10-10，在本项目 UEFI 启动的 RubikPi3 上测试已安装到 UFS 的
Ubuntu 26.04.1 ARM64，内核 `7.0.0-38-generic`。
`rubikpi3-msm-dkms` 和 `rubikpi3-lt9611-dkms` 均为 `0.1.0`。
最终测试启动 ID：`434b9f79-1116-4b54-951b-701d72e35ad0`。

| 检查 | 结果 |
| --- | --- |
| 普通 Ubuntu initramfs 启动 | 成功；两个 DKMS 模块自动加载 |
| 显示所有权 | `msmdrmfb`，原生 MSM 接管，桌面阶段无 simpledrm 设备 |
| KMS | `HDMI-A-1`，活动模式 1920×1080 @ 60 Hz |
| 统一 GPU/KMS | `separate_gpu_kms=N` |
| 硬件垂直同步 | 60 次 vblank 间隔耗时 0.999770 秒，测得 60.014 Hz |
| GPU | EGL renderer `FD643`；128 次清屏/像素读回通过，包含 2 秒空闲间隔 |
| USB / 网络 | Renesas 控制器及 USB 网卡自动加载，SSH 恢复连接；`wlan0` 存在 |
| 默认启动项 | `rubikpi3-native`；GRUB 配置语法检查通过，菜单等待 5 秒，保留原 Ubuntu 项 |
| 实际 HDMI 图像与拖动撕裂 | 等待用户确认；不能由 vblank 或渲染测试推断画面无异常 |

初次测试中，GPU SMMU 依赖在默认探测期限后才就绪；设置
`deferred_probe_timeout=120` 后原生链路成功绑定。USB 缺失的原因是
Renesas 固件缺失；从本机 `usb_fw` 分区只读复制并加入 initramfs 后恢复。
固件文件为 `renesas_usb_fw.mem`，13012 字节，SHA256：
`177560c224c73d040836b17082348036430ecf59e8a32d7736ce2b80b2634f97`。

**仍有启动警告：** GDM 启动阶段出现一次 DPU `invalid DSPP_-1`、
`unable to find appropriate mixers`、资源分配 `-119` 和 GNOME
`Page flip failed: ... No XENIX semaphores available`。随后 KMS 有活动帧缓冲，
硬件 vblank 和 GPU 测试通过；该启动时资源分配问题尚未修复，也尚不能确认
它是否影响实际画面。没有以此验证热插拔、休眠恢复、HDMI 音频、其他显示模式、
USB-C DP 或其他内核版本。`wlan0` 存在不代表无线联网已经验证。

本次未刷写 UEFI，安装器兼容 DTB 保持原状。原生默认项设置后未额外重启；
实机启动验证使用的是相同原生入口、内核、DTB 和普通 initramfs。
原始日志保存在设备 `~/native-display-20261010/`，以及开发主机的同名诊断目录；
串口日志可能包含登录输入，不应直接提交仓库。

## English

Tested on 2026-10-10: RubikPi3 with this project's UEFI, UFS-installed Ubuntu
26.04.1 ARM64, kernel `7.0.0-38-generic`, MSM and LT9611 DKMS packages `0.1.0`.
Final test boot ID: `434b9f79-1116-4b54-951b-701d72e35ad0`.

The standard Ubuntu initramfs loaded both DKMS modules. Native MSM owned
`msmdrmfb` and `HDMI-A-1` at 1920×1080 @ 60 Hz, with
`separate_gpu_kms=N` and no remaining desktop simpledrm device. Sixty hardware
vblank intervals took 0.999770 seconds (60.014 Hz). EGL reported `FD643` and
passed 128 clears/pixel readbacks, including a two-second idle interval.
USB Ethernet and SSH recovered automatically; wlan0 was enumerated, without a
wireless connectivity test. Physical HDMI appearance and tearing during window
motion still await user confirmation.

The native entry is now the GRUB default, with a five-second menu and the
original Ubuntu entry retained. GRUB syntax validation passed. Default selection
was not followed by another reboot; the identical entry, kernel, DTB and standard
initramfs had already booted successfully. UEFI was not flashed.

`deferred_probe_timeout=120` allowed late GPU SMMU dependencies to bind. Missing
Renesas USB firmware was restored from the board's read-only-mounted usb_fw
partition and included in initramfs; its size and checksum are listed above.

A startup DPU resource allocation warning remains unresolved: invalid DSPP on
LM2/LM3, unavailable mixers, error -119, and a GNOME atomic page-flip failure.
Subsequent active KMS state, hardware vblank and GPU tests passed, but these do
not establish correct physical output. Hotplug, suspend/resume, HDMI audio,
other modes, USB-C DP and other kernels were not validated. Logs remain in the
device and host diagnostic directories; serial logs may contain login input and
must not be committed without sanitization.
