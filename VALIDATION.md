# 验证 / Validation

## 已有实机依据 / Existing hardware evidence

RubikPi3，Ubuntu 26.04.1 ARM64，7.0.0-38-generic，EL2/VHE：

- GPU：MSM DKMS + Mesa，既有渲染读回测试通过，见组件 VALIDATION。
- HDMI：LT9611 单 B 输入 + native DT，1080p60、硬件 vblank；见组件 VALIDATION。
- Wi-Fi：brcmfmac 板级固件包，见组件 VALIDATION；不等同所有频段/休眠验证。
- VPU：2026-10-11，H.264 / HEVC，720p / 1080p，各 90 帧硬件编码/解码，
  输出与软件解码逐帧像素一致。编码需明确 Profile/Level，FFmpeg 硬件编码仍段错误。

这些结果来自此前分组件部署，不是首版统一包已经完成安装/卸载/重启实测的证明。
These results come from the component deployments, not an integrated-package
installation/removal/reboot acceptance test.

## 统一包验证 / Integrated package validation

2026-10-11：

- 使用本地固定 Ubuntu 源码、三份原始 Wi-Fi 文件和已校验 Renesas 固件，实际构建单个 deb。
- 解包校验全部 md5sums、维护脚本执行权限及 shell 语法；两个 DKMS 均限制到 ABI 38。
- 确认有效负载没有嵌套 deb、预编译 ko、本机 DTB 或 NVRAM 样例 MAC。
- 10 项隔离测试通过：真实 dtc/fdtget/fdtput 转换与幂等、单独 /boot 路径、
  重复配置/升级/移除、管理员改动保护、GRUB 失败回滚、DKMS 失败保留恢复默认项、
  USB 固件保护及恢复项丢失时阻止移除仍可用的 native 项。
- RubikPi3 上只读预检通过：板型、Ubuntu 26.04、7.0.0-38-generic、EL2/VHE、
  headers、Venus/USB 固件、模块来源满足当前包要求。
- 设备 `apt-get -s install` 通过：安装一个支持包，替换旧 GPU/桥/Wi-Fi 三包，
  未提出删除桌面或内核；没有执行真正的包替换。

Built the actual deb from pinned inputs; checked payload checksums, script syntax,
ABI restrictions and absence of board-specific DTBs/prebuilt modules/sample MACs.
Ten isolated lifecycle/DT tests passed. Read-only target preflight and APT dependency
simulation passed, replacing exactly the three old component packages.

未对当前运行设备实际执行统一包安装、卸载或重启验收；因此这些维护流程、
新的 firmware recovery 项以及 initramfs-tools 分支仍需实机验收。
现有分组件系统使用 dracut。隔离测试通过不能代替实际 DKMS 编译和重启检查。
No claim of real installation, removal, recovery boot, new-kernel support or
UEFI-mode implementation is made unless explicitly recorded below.
