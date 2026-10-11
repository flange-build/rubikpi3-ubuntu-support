# 补丁清单与 UEFI / Ubuntu 分工

**简体中文** | [English](PATCHES.en.md)

此处的“补丁”包含代码、设备描述、固件文件及安装逻辑。下表区分已经验证的实现
与可以迁入 UEFI 的候选，不能把源码推断写成实机结果。

| 补丁/逻辑 | 当前 deb 实现 | UEFI 能否承担 |
| --- | --- | --- |
| MSM 的 EL2 SECVID 路径 | `rubikpi3-msm-dkms/patches/0001-*`，限板型和 VHE | **有 DT 替代候选**，见下文；尚未完成原版 MSM 实机验证 |
| MSM 外部构建 trace include | `0002-out-of-tree-trace-includes.patch` | 仅 DKMS 构建适配；去掉 MSM DKMS 后一起消失 |
| LT9611 单 DSI B 输入 | `rubikpi3-native-display/patches/0001-*` | **仍需内核支持**。解析真实 port@1，并设置 B 数据/字节时钟寄存器；仅把 DT port 改成 0 不等价 |
| DPU 单 mixer 色彩资源 | `rubikpi3-msm-dkms/patches/0003-*`；本板单接口、无 DSC/CWB 且宽度符合硬件上限时不拆分 mixer，保留 CTM/GAMMA | **内核运行时负责**；UEFI 无法代替每次 atomic commit 的资源分配 |
| LT9611 熄屏后的 I²C 通信 | `rubikpi3-native-display/patches/0002-*`；移除 sleep 路径的地址/GPIO 改写 | **内核负责**；固件初始化不能阻止 Linux 在熄屏时再次改坏地址 |
| DPU、DISPCC、DSI、PHY、LT9611 节点 | 本机 `prepare-dtb.py` 启用 | **可迁入 UEFI 原生显示模式**，但需与兼容模式分开 |
| simple-framebuffer 删除、DP 暂停 | 原生配置删除旧 framebuffer；禁用未验证 USB-C DP | **可按显示模式由 UEFI 提供**；不能让安装器默认依赖未安装的桥驱动 |
| Venus 数据流/固件流 | `0x2180/0x2184` 数据流、`0x21a2` 固件子节点，原版驱动 | **可迁入 EL2 DT fixup**；EL1/Gunyah 不可无条件套用 |
| Wi-Fi firmware/CLM/NVRAM | 板名专用文件；删除样例 MAC | Linux `request_firmware` 文件仍需要 deb；MAC/供电/SDIO 描述适合 UEFI DT |
| Renesas USB firmware | 校验固件，放标准路径和 initramfs | UEFI 可初始化供启动使用，但 Linux 重置/重载可能再次请求，**包中仍保留** |
| `msm.separate_gpu_kms=0` | 原生入口参数，覆盖旧兼容配置 | Linux 模块参数；由包管理比固件强塞 cmdline 更清楚 |
| `deferred_probe_timeout=120` | 原生入口参数，等待依赖 | Linux 加载时序临时措施；应进一步研究依赖/模块顺序，不能认定仅改 UEFI 可消除 |
| `separate_gpu_kms=1` | 复用旧 GPU 包的 modprobe 配置，支持旧兼容入口；新入口显式覆盖 | 兼容显示的 Linux 策略，不是硬件属性 |
| initramfs 与 DKMS hooks | depmod、驱动/固件入镜像、安装/卸载刷新 | **Ubuntu 负责** |
| GRUB 默认项、固定 ABI、回退配置 | 使用标准 Ubuntu 入口，维护脚本管理配置和备份 | **Ubuntu 负责**，UEFI 不应管理 apt/kernel 生命周期 |
| stale EFI/initrd 地址和 entropy | 保存 DT 时删除，由本次启动重新产生 | 使用 UEFI 每次生成新 FDT 后可减少静态 DT 快照需求 |
| GStreamer codec cache、Profile/Level、FFmpeg 崩溃 | 提供显式参数测试工具和记录；不假装修改上游用户态 | **用户态问题**，不适合 UEFI 修复 |

相对路径均以 `components/` 为根。原有 GPU、显示、Wi-Fi 验证记录与 VPU 文档保留。
不包含未成功的 PAS/SHM Venus 实验，不加入桌面软件配置、用户密码、网络凭据或磁盘分区操作。

## GPU：可以尝试移除 DKMS 的准确理由

已检查固定 Ubuntu `7.0.0-38.38` 的
`drivers/gpu/drm/msm/adreno/adreno_gpu.c`：
`zap_shader_load_mdt()` 查找 `zap-shader` 子节点，若节点不可用则返回 `-ENODEV`。
同版本 `a6xx_gpu.c` 在初始化时收到该结果会写 `RBBM_SECVID_TRUST_CNTL=0`。
这与当前板级补丁强制返回 `-ENODEV` 的结果一致，是**源码层面的替代依据**。

因此 UEFI 可在**确认 EL2/VHE 所需访问权限成立**时，将 GPU 的 `zap-shader`
设为 `status = "disabled"`，让原版 MSM 自己完成每次初始化的直接切换。
这不是“UEFI 开机写一次 GPU 寄存器”：GPU 复位、恢复和运行时电源管理仍由 Linux 驱动执行。
EL2 启动本身不应被当作所有安全寄存器均可写的通用保证。

首版包保留已验证补丁。去掉它之前，需要原版 MSM + 候选 DT 完成冷/热启动、
GPU 渲染读回、窗口拖动、GPU reset 和休眠/恢复验证；之后才能移除 MSM DKMS
及其外部构建补丁。不要只用 `lsmod` 或一个 renderer 名称判定成功。

## 建议的 UEFI 模式

1. **安装器兼容**：维持现有 simple-framebuffer、必要时钟/电源保持及 ICE/GPI 规避。
   官方安装镜像还没有 LT9611 B 输入补丁，不能默认切换成原生输出。
2. **已安装系统原生**：启用真实 DPU/DSI/桥描述，停止插入兼容 framebuffer；
   在实际 EL2 模式下添加 Venus 固件流，并在验证后加入 GPU zap-shader 策略。
3. **EL1/Gunyah**：保留该模式自己的 PAS/安全固件描述，不复用 EL2 direct 配置。

固件模式未来应提供版本化 DT 标记，包检查模式/版本后决定是否仍需本地 DTB，
不能只凭一个属性跳过硬件依赖验证。这是设计方向，本次**没有修改或刷写 UEFI**。

edk2-flange 中的 `edk2-qualcomm/Platform/Thundercomm/RubikPi3/DeviceTree/` 已处理 ICE、GPI、
simpledrm 供电/时钟以及 LT9611 GPIO 接管；本包保留这些板级状态，不重复向内核塞全局
`clk_ignore_unused`、`pd_ignore_unused` 或 ICE 黑名单。
ADSP/CDSP 预加载、启动前 GRUB 故障及热重启 PCIe USB 丢失并未由此包证明修复。

## 依据

- 固定 Ubuntu 内核源包及包内保留的 `SOURCE` 和 `applied-patches`，是驱动分析依据。
- [上游 SC7280 Chrome DT](https://github.com/torvalds/linux/blob/v7.0/arch/arm64/boot/dts/qcom/sc7280-chrome-common.dtsi)
  提供已实测 Venus IOMMU 描述。
- 维护脚本按 [Debian 维护脚本约定](https://www.debian.org/doc/debian-policy/ch-maintainerscripts.html)
  区分 configure/remove/upgrade，并让配置错误返回非零；旧包替代关系参照
  [Debian 软件包关系](https://www.debian.org/doc/debian-policy/ch-relationships.html)。
