# 验证记录 / Validation

日期 / Date: 2026-10-10

- Thundercomm RubikPi3 / AP6256 (BCM4345/9, SDIO 02D0:A9BF).
- Ubuntu 26.04.1 ARM64, `7.0.0-38-generic`, dracut initramfs.
- `rubikpi3-wifi-firmware` 0.1.0, firmware 7.84.17.1 (r871554).

## 打包及生命周期 / Packaging and lifecycle

- 构建前检查三份厂商文件的固定 SHA256；故意损坏的输入被拒绝，未生成包。
  Pinned source checksums validated; deliberately corrupted input rejected before output.
- 包内仅有三个板级固件文件；活动样例 `macaddr=` 已删除，校准数据保持不变。
  Three board-specific firmware files, no active sample MAC, unchanged calibration.
- 安装成功，`dpkg -V` 无差异；三个固件进入现有内核的 initramfs。
  Installation and package verification passed; all three files present in initramfs.
- 卸载成功，固件与两类钩子从根文件系统移除；重建的 initramfs 不再包含 BCM43456 固件。
  Removal cleaned package files/hooks and regenerated initramfs without BCM43456 firmware.
- 重新安装成功。所有维护脚本及 initramfs 更新退出状态为 0。
  Reinstallation passed; maintainer scripts and initramfs generation returned success.
- 早期手工通用固件和 dracut 配置已移至备份目录，不参与本包验证。
  Earlier manual generic firmware and dracut configuration were moved to backup.

## 重启验证 / Reboot verification

重启后 `wlan0` 自动出现，固件为 7.84.17.1，原有永久 MAC 保持不变，
`addr_assign_type=0`。扫描得到 15 个 AP，包含 2.4 GHz 与 5 GHz。
不再出现必需固件缺失或 HT Avail timeout；可选 txcap_blob 缺失仍有提示。
GDM active，MSM DKMS 保持 installed，有线 SSH 正常。

After reboot, wlan0 appeared automatically with firmware 7.84.17.1 and the same
permanent MAC (`addr_assign_type=0`). A scan found 15 APs across both bands.
Required-firmware errors and HT Avail timeouts were absent; the optional txcap_blob
message remained. GDM was active, MSM DKMS stayed installed and Ethernet SSH worked.

Boot ID: `ae99bca6-75ec-4fa2-af16-379ef6e8be4d`.

Tested package SHA256:
`c42d1cf35a1349a772d9ac125f950f04707cdcb6781d4dc82b456d0b266c3bed`.

## 覆盖范围 / Coverage

当前实测为 dracut。initramfs-tools 钩子已做 shell 语法检查，但未在运行
initramfs-tools 的 RubikPi 系统上验证。未覆盖后续内核、AP 关联/吞吐量、
休眠恢复或蓝牙；Wi-Fi 固件不替换内核模块。

Runtime coverage is dracut. The initramfs-tools hook passed shell syntax checks
but has not been tested on a RubikPi installation using initramfs-tools.
Future kernels, AP association/throughput, suspend/resume and Bluetooth are not
covered. No kernel module is replaced by this firmware package.
