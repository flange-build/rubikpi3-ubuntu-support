# 显示撕裂 / Display tearing

## 中文

2026-10-10，Ubuntu 26.04.1、`7.0.0-38-generic`、MSM DKMS 0.1.0、
Mesa 26.0.8、Mutter 50.1。用户观察：移动窗口或鼠标时出现撕裂，随后自行恢复。

实机证据：

- `card0` 为 `simpledrm`，输出 `Unknown-1`、1920×1080；fb0 为 `simpledrmdrmfb`。
- GNOME Shell 打开 `card0` 和 MSM 的 `renderD128`，渲染加速与输出设备分离。
- `DRM_IOCTL_WAIT_VBLANK`（relative sequence 0）在 `card0` 返回
  `EOPNOTSUPP`（95）；没有可用的硬件垂直同步等待。
- GNOME 使用软件光标，记录过 `Invalid sequence for VSYNC frame info`。
  本轮日志未发现 GPU hang、IOMMU fault 或恢复重置；这不能排除全部渲染问题。
- 项目设备树关闭 `mdss`、`dispcc` 和 LT9611，保留 UEFI 初始化的显示路径。

[Linux v7.0 sysfb 源码](https://github.com/torvalds/linux/blob/v7.0/drivers/gpu/drm/sysfb/drm_sysfb_modeset.c)
通过 CPU 将变化区域拷贝到固件的显示帧缓冲，没有原生显示控制器同步换帧。
结合实机缺失 vblank 的结果，当前最有力的解释是扫描输出与更新画面不同步。
尚未通过原生 KMS 的 A/B 对照证明它是唯一原因。

根本修复方向是启用并验证原生 MSM DPU → DSI → LT9611，包含板级单路 B 输入、
时钟/电源、IOMMU 和 UEFI 显示资源交接。这不是简单取消设备树的 disabled：
该路径此前存在黑屏问题。仅修改 GPU 的 EL2 补丁或设置应用 VSync 无法为
`simpledrm` 增加硬件同步。此次排查未更改运行中的图形配置。

## English

On 2026-10-10, Ubuntu 26.04.1 / `7.0.0-38-generic`, MSM DKMS 0.1.0,
Mesa 26.0.8 and Mutter 50.1 showed transient tearing during pointer/window motion.
The image recovered after movement stopped.

GNOME opened both simpledrm `card0` (1920×1080, Unknown-1) and MSM `renderD128`.
`DRM_IOCTL_WAIT_VBLANK` with relative sequence zero returned `EOPNOTSUPP` (95)
on card0. GNOME used a software cursor and logged an invalid VSYNC frame-info
sequence. No GPU hang, IOMMU fault or recovery reset appeared in the captured log;
this does not rule out every rendering issue.

The device tree disables native MDSS/DISPCC/LT9611 and retains UEFI scanout.
The upstream sysfb implementation copies damaged regions into that framebuffer.
Unsynchronized scanout updates are therefore the leading explanation, although
an A/B comparison against native KMS has not established them as the sole cause.

A full fix needs native DPU → DSI → LT9611 support, including the board's single
B input and clock/power/IOMMU/UEFI handover. Simply enabling those nodes previously
caused a black display. The GPU EL2 workaround and application VSync settings
cannot provide hardware synchronization to simpledrm. No live graphics settings
were changed during this investigation.
