# RubikPi3 VPU 硬件编解码

**简体中文** | [English](README.en.md)

已在 RubikPi3、Ubuntu 26.04.1 ARM64、`7.0.0-38-generic`、Linux EL2/VHE 下验证
H.264 与 H.265 的 720p、1080p 编码和解码。使用系统原版 Venus 驱动和系统固件，
VPU 不需要 DKMS。GPU 和原生 HDMI 仍使用各自的 DKMS 包。

## 修复内容

EL2 下 Linux 负责 VPU 固件的 IOMMU 映射。原设备树没有描述固件流，驱动进入
TrustZone PAS 路径，初始化固件返回 `-22`。实验性 SHM bridge 补丁让认证通过，
但随后视频保护地址配置返回 `-5`，该补丁未安装。

最终方案采用[上游 SC7280 配置](https://github.com/torvalds/linux/blob/v7.0/arch/arm64/boot/dts/qcom/sc7280-chrome-common.dtsi)：

```dts
&venus {
    iommus = <&apps_smmu 0x2180 0x20>, <&apps_smmu 0x2184 0x20>;
    status = "okay";
    video-firmware {
        iommus = <&apps_smmu 0x21a2 0>;
    };
};
```

`video-firmware` 使原版驱动选择由 Linux 映射固件并直接启动 VPU 的路径。
这只适用于本文的 EL2 启动方式，不支持受保护视频会话；不能将同一 DTB 用于 EL1/Gunyah。
没有替换 TrustZone、刷写 UEFI 或修改系统固件文件。

## 安装

先按[原生 HDMI 文档](../rubikpi3-native-display/README.md)安装 GPU/桥驱动和 USB 固件，
保留本目录与 `rubikpi3-native-display` 的相邻位置。确保 UEFI 配置让 Linux 从 EL2 启动。

```sh
sudo python3 ../rubikpi3-native-display/install-boot-profile.py --vpu-el2
# 下一次启动自动选择新项；验证成功后再设置为默认：
sudo python3 ../rubikpi3-native-display/install-boot-profile.py --vpu-el2 --make-default
```

安装器检查当前启动日志中的 EL2 标记和系统 Venus 固件是否存在，备份原文件，
创建独立入口 **Ubuntu - RubikPi3 native HDMI + VPU (EL2) (7.0.0-38-generic)**，
ID 为 `rubikpi3-native-vpu`。原来的原生 HDMI 入口保留。内核升级后需要重新验证，
该入口固定使用安装时选择的内核。

只生成 DTB 时，可对本机原生显示 DTB 执行：

```sh
python3 prepare-dtb.py native-hdmi.dtb native-hdmi-vpu.dtb --el2
```

工具校验板型及已有流映射，保留其他硬件配置，清理上次启动的 EFI/initrd 地址与熵。
生成文件仅属于这台设备，不应复制给其他板子。

## 使用和验证

```sh
sudo apt install --no-install-recommends ffmpeg v4l-utils
v4l2-ctl --list-devices
gst-inspect-1.0 v4l2h264enc
python3 test-codecs.py ./vpu-results --size 1920x1080
```

还需 GStreamer 的 `gst-launch-1.0`、`videotestsrc` 和 video4linux2 插件。
若新设备出现后旧插件缓存未发现编码器，可以使用新缓存重新扫描：
`GST_REGISTRY=/tmp/rubikpi-vpu-registry.bin gst-inspect-1.0 video4linux2`。
SSH 用户需要视频节点访问权限；桌面登录通过 ACL 授权，不能假定所有远程用户都有权限。

**不要固定 video0/video1 的角色**：它们在不同启动中可能交换。
测试脚本显式使用 GStreamer 的硬件编码 element 和 FFmpeg 的硬件解码器，
验证帧数、分辨率，并将每一帧解码后的 YUV420P 像素与软件解码比较。

已验证的 H.264 编码示例：

```sh
gst-launch-1.0 -e videotestsrc num-buffers=90 \
  ! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 \
  ! v4l2h264enc extra-controls="controls,video_bitrate=6000000,h264_level=12" \
  ! 'video/x-h264,profile=high,level=(string)4.1' \
  ! filesink location=test.h264
```

必须指定与分辨率匹配的 Profile/Level。当前固件在未限制参数的 1080p 编码测试中
触发过 fatal error；显式 H.264 High / HEVC Main、Level 4.1 后测试通过。

## 实机结果与限制

2026-10-11，启动 ID `24c6103a-21f2-4978-b68b-1d36db52ef71`：

| 路径 | 720p / 90 帧 | 1080p / 90 帧 |
| --- | --- | --- |
| H.264 硬件编码 → 硬件解码 | 通过，全部像素与软件解码一致 | 通过，全部像素与软件解码一致 |
| HEVC 硬件编码 → 硬件解码 | 通过，全部像素与软件解码一致 | 通过，全部像素与软件解码一致 |

输入帧率为 30 fps，这些是功能测试，不是长时间吞吐量基准。编码使用 GStreamer，
解码使用 FFmpeg `h264_v4l2m2m` / `hevc_v4l2m2m`。
原始码流缺少可靠时间戳，比较时使用 `-fps_mode passthrough` 防止 FFmpeg 丢弃帧。

Ubuntu FFmpeg 8.0.1 的 `h264_v4l2m2m` **编码**在本机仍会段错误，指定 Level 也未解决；
当前使用 GStreamer 编码。没有验证 4K、10-bit、VP8/VP9/MPEG-2、长期负载、
休眠恢复或浏览器自动加速，枚举出的格式不代表已经全部可用。

一次热重启曾导致 PCIe 未枚举 USB 控制器，用户再次重启后 USB 网卡恢复；
这是尚未解决的重启稳定性问题。诊断日志与测试视频保留在设备
`~/vpu-check-20261011/`，不包含在仓库中。

## 回退

GRUB 选择原来的 **Ubuntu - RubikPi3 native HDMI**。取消 VPU 默认项时，将
`/etc/default/grub.d/99-rubikpi3-native.cfg` 中 `GRUB_DEFAULT` 改为
`rubikpi3-native`，执行 `sudo update-grub`。要删除 VPU 入口，移走
`/etc/grub.d/43_rubikpi3_native_vpu` 后再更新 GRUB；无需卸载 VPU 模块。
