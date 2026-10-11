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

## 0.1.0 统一包验证 / Integrated package validation

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


## 0.2.0 标准 Ubuntu 启动 / Standard Ubuntu boot

2026-10-11：

- 12 项隔离测试通过，覆盖旧入口清理、备份/回滚、未知文件保护、普通 Ubuntu 参数组合。
- 设备实际安装 `rubikpi3-ubuntu-support 0.2.0` 成功，替换旧 GPU/桥/Wi-Fi 三个组件包。
- 两个 DKMS 实际重编译并安装；initramfs 含 MSM、LT9611、Renesas 与板级 Wi-Fi 固件。
- 原生/VPU 独立入口、旧默认配置和四个测试 DTB 已备份并移除。
- GRUB 语法校验通过：标准 Ubuntu 默认加载 `/boot/dtb-7.0.0-38-generic`，
  参数为 `msm.separate_gpu_kms=0 deferred_probe_timeout=120`，保留发行版其他参数。
- 本次生成的 DTB 与此前实测版本 SHA256 相同：
  `752d49fe651b4347bac81fc8b7a45a1b9688d4d25709c2f8e082865ce5a3afef`。
- 首次热重启已自动交给 Linux，但网络未恢复；当前只有屏幕控制台，尚无 Linux 串口日志。
  安装/生成配置成功不等于已完成本轮启动验收；已请求断电上电排查。

Actual installation succeeded, including rebuilding both DKMS modules and the
initramfs. The standard Ubuntu entry now carries the adapted DT and parameters;
legacy entries/DTBs were backed up and removed. The initial warm reboot handed
off to Linux, but networking did not return. Cold-start acceptance is pending.

### 串口复查 / Serial follow-up

2026-10-11：

- GRUB 长命令一次写入会丢字符；逐字限速发送后，内核路径和完整参数得到串口确认。
- 同一内核、initramfs、DTB，保留 `crashkernel`，增加串口/earlycon 并去掉
  `quiet splash` 的临时启动已进入 `graphical.target`；串口登录成功，GDM active，
  `/proc/fb` 为 `msmdrmfb`。尚需确认 HDMI 实际画面。
- 读取上一轮持久 journal，确认标准 Ubuntu 启动也已进入 GDM 和图形目标；
  不能把 SSH 不通或串口静默当成内核没有启动。
- 本轮 PCIe 两个控制器均报告 `Device not found`，只有 lo/wlan0，无 USB 以太网接口。
  GNOME 另有 `Page flip failed`，DPU 报资源分配 `-119`；显示和网络仍需分别排查。
- 已在设备更新普通 Ubuntu 启动配置：菜单显示 5 秒，启用 `ttyMSM0` 串口。
  本地 13 项隔离测试通过；此次配置尚未重启验收。

A paced GRUB command boot reached the graphical target with GDM active and
msmdrmfb; physical HDMI output remains unconfirmed. Persistent logs also confirm
the preceding stock Ubuntu entry reached the graphical target. Missing PCIe USB
networking and a GNOME page-flip failure require separate investigation. The device
now has a visible five-second menu and a serial console; reboot validation is pending.

### 普通启动项复测 / Standard entry retest

- 用户再次重启后确认 HDMI 先显示蓝色画面，随后进入登录界面。
- Boot ID `403c5ba9-c041-40f8-bef5-ee83aefbce56`：普通 Ubuntu 参数保留
  `quiet splash`、`crashkernel`，包含新加入的串口；GDM active，`msmdrmfb` 接管。
- PCIe0 在 27.83 秒建链 Gen2 x1，Renesas USB 在 37.18 秒启动，
  `cdc_ncm` 网卡在 51.97 秒注册；SSH 登录成功，网关 ping 3/3，无丢包。
- 内核启动到图形目标 59.867 秒，其中 initrd 43.848 秒；原生显示 52.45 秒接管，
  Plymouth 59.77 秒退出。此次蓝色画面后最终正常显示，不能归为启动卡死。
- 此次复测确认恢复，但前一轮 PCIe0 无链路的根因仍未解决，不能声明反复启动稳定。
  `Page flip failed/-119` 在可显示的启动中仍出现，不能单凭该条日志判定蓝屏根因。

The standard entry subsequently reached the login screen, with PCIe USB Ethernet,
SSH and gateway connectivity working. Kernel-to-graphical startup took 59.867 seconds,
including 43.848 seconds in initrd. The earlier intermittent PCIe0 link failure remains
unresolved; this successful boot is not evidence of repeated-boot reliability.

### 启动动画依赖 / Boot splash dependency

- 实际 initramfs 含 Plymouth DRM renderer、BGRT/spinner 主题，发行版配置启用
  `UseSimpledrm=1`；Plymouth 服务已启动，缺少动画不能只用启动耗时解释。
- initramfs 含 MSM、LT9611 和显示时钟驱动，但缺少 `display-connector.ko`。
  LT9611 在解析出单 B 输入后查找下游 connector 失败，反复延迟探测；
  切换根文件系统后 connector 驱动加载，才完成原生显示初始化。
- 两种 initramfs 打包配置均补入 `display_connector`，它是 DT 图中的依赖，
  不会通过 `modules.dep` 自动带入。启动动画恢复仍需重启实测。
- 早期 EFI simpledrm 的显示保活仍需验证：native DT 移除了带时钟/电源依赖的
  framebuffer 节点，6.28 秒发生 unused-clock 清理。UEFI 的 DPU underflow 色为蓝色，
  与症状相符，但没有现场 underflow 寄存器记录，不能认定为已证实的直接原因。

The actual initramfs included Plymouth and its theme but omitted display_connector,
a DT graph dependency of LT9611. Both initramfs packaging paths now explicitly include
it. Early scanout preservation and visible splash recovery still require boot testing.

## 0.2.1 显示器熄屏恢复 / Display blanking recovery

2026-10-11，Ubuntu 7.0.0-38-generic，原生 1920×1080 显示：

- 旧驱动复现：通过 Mutter 将 PowerSaveMode 从 3 切回 0 后，SSH 仍可用，
  HDMI 保持 disabled，DPU 资源分配返回 `-119`。没有整机 suspend 记录。
- 原来的 1080p 路径使用 LM2/LM3，恢复 CTM/GAMMA 时要求两个 DSPP；SC7280
  只有 LM0 上的一套 DSPP。MSM 补丁仅对本板单接口、无 DSC/CWB、宽度不超过
  硬件 mixer 上限的情况固定使用单 mixer，保留色彩管理。
- 临时 1024×768 验证已分配 LM0/DSPP0，但屏幕仍无信号，LT9611 报
  `power on failed`。桥的 sleep 序列修改 I²C 地址而 wake 未恢复，是第二个故障。
  回移[内核邮件列表的修复](https://lore.kernel.org/all/20260127-rubikpi-next-20260116-bugfix-v1-1-46e3396533ac@thundersoft.com/)，
  去掉地址和地址引脚改写，保留 MIPI/PHY 省电。
- 两个 DKMS 均升为 0.1.1；固定源补丁应用及真实 ARM64 编译成功。
  设备从统一包 0.2.0 升级至 0.2.1 成功，旧登记已备份，新模块进入 initramfs。
- 17 项隔离测试通过，新增跨版本升级的失败保护、失效登记归档、保留其他内核
  使用的旧版本；包内容检查包括版本、补丁有效负载及当前维护脚本。
- 重启和反复熄屏验收结果另列于下方；这里不代表整机 suspend/resume 已通过。

The failure was reproduced through Mutter DPMS while SSH remained available.
DPU color-resource allocation and LT9611 sleep-time I²C address changes were
independent failures. Both fixes compiled on ARM64 and the 0.2.0 → 0.2.1 target
upgrade succeeded. Seventeen isolated tests cover the package lifecycle, including
retaining older DKMS versions used by other kernels. Whole-system suspend/resume
is a separate, unvalidated path; see subsequent hardware results below.

### 1080p 实机验收 / Hardware acceptance

- Boot ID `8c4985c6-b02c-4847-8305-ca15ea1a1edf`，启动后自动恢复
  `1920×1080@60`，桌面使用原生 MSM；临时 1024×768 未保留。
- 加载中与磁盘模块的 srcversion 一致：MSM `F998AD10974B25C62CC7601`，
  LT9611 `A376279C12D164EB2874EC3`。
- 连续五轮 Mutter DPMS off/on：每轮 HDMI 从 disabled 恢复 enabled，
  CRTC active，LM0 + DSPP0，保持 1080p60。未再出现资源分配 `-119` 或
  LT9611 `power on failed`；用户确认画面、鼠标和窗口操作正常。
- 两轮关闭时仍记录 `enc34 timeout pending`；均随后恢复，未在本轮导致黑屏。
  该关闭阶段的超时尚未修复，不把此次测试描述为“日志完全无错误”。
- 最终维护脚本再次配置成功，包校验无差异，运行中与安装模块的 srcversion 仍一致。
  保留原来的 300 秒自动熄屏设置，未禁用熄屏，也未修改整机休眠策略。
- 用户确认启动阶段仍有蓝色画面再进入系统；此问题不在本次 DPMS 验收通过范围。
  本轮 5.96 秒注册 EFI simpledrm，6.006 秒清理 unused clocks/domains，
  44.04 秒 MSM 注册，47.38 秒 msmdrmfb 接管，56.57 秒才从根文件系统加载 GPU 固件。
  早期 framebuffer 的 clock/power 保活和 initramfs GPU 固件仍需单独验证。

Five 1080p60 blank/unblank cycles restored an active HDMI CRTC using LM0/DSPP0;
the user confirmed normal desktop, pointer and window output. Resource allocation
and bridge power-on failures no longer occurred. Two disable-time encoder timeout
messages remain recorded, although recovery succeeded. The final package reconfiguration
and installed-file verification passed without changing the five-minute blanking policy.
The startup blue screen persists and whole-system suspend/resume is not validated.

自然 300 秒空闲后，系统进入 PowerSaveMode=3、HDMI disabled；用户随后确认
设备键盘、鼠标均可正常唤醒显示器。自然空闲熄屏后的恢复验收通过。
After the unchanged 300-second idle interval, PowerSaveMode=3 and HDMI disabled
were observed. The user then confirmed successful physical keyboard/mouse wake
from natural display blanking, completing this display-recovery check.

## 0.2.2 启动画面交接 / Boot display handoff

2026-10-11：

- 相同原生显示配置临时加入 `clk_ignore_unused pd_ignore_unused` 后，用户确认
  蓝屏消失，但只有文字。Plymouth 日志明确记录检测到串口后强制 details 模式。
- Boot ID `fc975ae7-b0b6-4c5d-8a05-2b56252e1c93`：保留上述诊断参数，加入
  `plymouth.ignore-serial-consoles`。日志确认 4.61 秒打开 simpledrm、5.52 秒启动
  spinner 动画、7.47 秒打开 MSM、9.12 秒完成原生 1920×1080 scanout。
  GDM 正常启动；这轮物理动画尚未得到用户确认。
- 第一轮取消全局保活的零地址 framebuffer 模板测试未通过：Boot ID
  `cd4e70a8-9847-4a5a-a7aa-61f132bf677b` 的 live DT 仍有 disabled `framebuffer@0`，
  没有 early simpledrm，原生 MSM 到 33.25 秒才注册。这份候选包未安装。
- 定位到 UEFI 的 DT fixup 容量协商错误：Ubuntu GRUB 先以 size=0 查询，再只重试
  一次；旧固件先返回原树大小，第二次才要求显示修补额外空间，未完成模板更新。
  新包要求固件报告 `flange,display-fixup-version >= 1`；缓存 DT 会清除此属性，
  每次启动须由当前固件重新写入，避免固件降级后误用旧能力标记。
- 设备树测试覆盖有/无旧 framebuffer、动态 provider phandle、重复转换及坏输入
  不覆盖输出。启动配置测试覆盖串口保留、禁用 splash、重复生成和旧固件拒绝。
- 新固件、零模板资源交接与最终 deb 的实机结果以之后记录为准；不把源码测试
  或图形日志等同于无蓝屏的物理验收。

The keep-resources A/B removed the visible blue screen, while Plymouth forced text
because of the serial console. Ignoring serial consoles enabled the graphical theme
and successful simpledrm-to-MSM rendering in logs. The first resource-template test
exposed a firmware buffer-size negotiation bug: GRUB's single retry was insufficient
for the old two-stage size response. That candidate was not installed. The package
now requires a fresh firmware capability marker and removes cached copies from its DT.
Final firmware/package boot and visible-screen acceptance are recorded separately.

### 新固件候选启动 / Fixed-firmware candidate boot

2026-10-12，Boot ID `57d495b1-b88d-403b-a924-c35205728578`：

- UEFI DEBUG 构建成功，ELF SHA256
  `92ac348c7efb7b4627608c20011d8b500efaac84c64b841ea7b18e93a7668b58`。
  两个 UEFI 分区先完整备份，仅写新 ELF 前缀，整分区读回确认前缀一致、尾部未变。
- 串口确认初始树和 GRUB 提供的模板均执行 `DtFixupDisplay`。live DT 有
  `flange,display-fixup-version=1`，`framebuffer@DD700000` 为 okay，地址/尺寸来自
  本次 GOP；四个 GCC 时钟和两个 TBU 电源域引用完整。
- 未使用 `clk_ignore_unused` 或 `pd_ignore_unused`。1.480 秒注册 DT simpledrm，
  1.485 秒执行 unused cleanup；8.207 秒原生 MSM 注册，8.758 秒 msmdrmfb 接管。
- Plymouth 日志确认 simpledrm 和 MSM 均创建 1920×1080 像素显示并设置 scanout，
  动画主题已加载；GDM active。物理动画和无蓝屏仍等待用户确认。
- 固件侧 14 个含真实 DT 的 libfdt 用例通过 ASan/UBSan；新增可复用仓库测试用
  合成 DT 覆盖 10 个场景，普通/ASan/UBSan 均通过。包侧 21 项隔离测试通过。

Both initial and GRUB-loaded DTs were fixed on hardware. DT simpledrm registered
before unused-resource cleanup and then handed off to native MSM without global
keepalive parameters. Plymouth created graphical scanout on both drivers and GDM
started. Physical animation/no-blue-screen acceptance remains pending.

### 0.2.2 安装 / Package installation

- 设备从 0.2.1 实际升级到 0.2.2，只升级此包，无新增/移除其他包；两个 DKMS
  均重建成功，initramfs/GRUB 刷新完成，`dpkg --verify` 无差异。
- 安装文件 SHA256 为
  `62f6cde09fde2b68423ae9a016e7ff44bf939fad501ec916a9beb203a7e96d2b`。
- 普通 Ubuntu 项使用的 DTB SHA256 为
  `00933cf2fc8d748da03688a1bbb0c7d8bede1ddd17c5d174d96d87c60283e09b`，
  与候选启动相同。保存文件不含能力标记，帧缓冲地址为零，依赖当次 UEFI 修补。
- 默认项自动包含一次 `plymouth.ignore-serial-consoles`，保留串口与 `quiet splash`；
  不含 `clk_ignore_unused`、`pd_ignore_unused` 或 `plymouth.debug`。
  临时诊断入口、单次选择和候选 DTB 已移除。

The 0.2.1 → 0.2.2 upgrade rebuilt both DKMS modules and refreshed initramfs/GRUB;
installed-file verification passed. Only the support package changed. The ordinary
Ubuntu entry uses the tested candidate DT and graphical splash policy. Temporary
entries, one-shot selection and global keepalive/debug options have been removed.

### 普通 Ubuntu 项重启 / Standard Ubuntu reboot

Boot ID `fdedc69f-4a5e-414f-bc95-f68da8efccf8`：普通默认 Ubuntu 项自动启动，
无单次选择、全局保活或 debug 参数。live DT 的能力标记为 1，当前 GOP framebuffer
为 okay。GDM active，HDMI connected/enabled，桌面 framebuffer 为 `msmdrmfb`。
内核到 graphical.target 用时 24.689 秒。USB 以太网连接正常、SSH 可用，wlan0 已枚举
（未连接无线网络）。运行中与磁盘 MSM/LT9611 srcversion 一致，包文件校验无差异。
用户随后确认启动时仍短暂闪蓝，之后画面恢复。全程无蓝屏的目标尚未达成；
动画是否完整显示仍未得到单独确认。尚未捕获闪蓝与原生驱动接管的准确时间对应，
不能把这次短暂闪蓝直接归因于某一次时钟切换或桥复位。

The ordinary default entry rebooted successfully without one-shot selection or
keepalive/debug flags. GDM, native MSM HDMI and USB Ethernet are active; wlan0 is
present. Loaded/disk module versions and package checksums match. Kernel-to-graphical
startup took 24.689 seconds. The user subsequently observed a brief blue flash,
followed by restored output. A completely blue-free boot is not yet achieved;
the full visible animation has not been separately confirmed. The flash has not
been timed against native-driver handoff, clock changes or bridge reset.
