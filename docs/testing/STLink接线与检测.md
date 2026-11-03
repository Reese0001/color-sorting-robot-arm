> 2026-11-03：USB BSL 已完成烧录、CRC 和应用实测。下文保留早期通道排查记录；当前入口见 [USB 下载说明](USB_BSL下载准备.md)。

# ST-Link/V2 与 MSPM0G3507 接线及检测

更新于 2026-11-02。当前仅检测下载通道，尚未烧录程序。

## 已确认与尚未确认

- 用户提供紫色、10 针、标有 ST-LINK/V2 的下载器照片。照片不能确认内部硬件真伪。
- Windows 实测识别 `STM32 STLink`，`VID_0483 / PID_3748`，设备状态 OK。
- OpenOCD 实测读到 **V2J37S7 / API v2**。版本满足 direct SWD 及 MSPM0 初始化使用 AP4 的要求，但不代表目标板已连接成功。
- 已准备 OpenOCD `0.12.0+dev-gf13e839`（2026-10-29），来自 OpenOCD 官方 GitHub 镜像的自动构建，下载归档 SHA256 与 GitHub 发布的 digest 一致；未升级或改写 ST-Link 固件。
- 配置离线解析通过。用户接好三根线后，100kHz 连接失败：`STLINK_JTAG_GET_IDCODE_ERROR` / `init mode failed (unable to connect to the target)`。当前没有读到目标 DAP ID、芯片信息或 MAIN Flash；不能据此断定芯片损坏、锁定或下载器绝对不兼容。
- 暂停继续烧录，下一步核对实际接线照片、引脚方向及主控供电。

之前板载 USB 的 COM8/BSL 曾读取成功，随后发生 USB 设备描述符错误 Code 43。SWD 是另一路下载通道；即使 SWD 成功，也不表示 USB 串口已修好。

## 只接三根信号线

**先拔掉主控 USB 和 ST-Link，再接杜邦线。** 以下编号来自用户这只下载器的外壳印字，不适用于所有 ST-Link。按实际信号标识找针，不要只凭照片左右方向猜。

| 紫色 ST-Link 引脚 | MSPM0 核心板丝印 | 用途 |
|---|---|---|
| **2 / SWDIO** | **A19 / PA19** | SWD 数据 |
| **6 / SWCLK** | **A20 / PA20** | SWD 时钟 |
| **4 / GND** | **GND** | 共地；不能接 3V3 |

连接完成后，ST-Link 插电脑 USB，核心板仍由自身 USB-C 供电。主控电源灯应亮；若有万用表，应测主控 3V3 对 GND。下载器上报的约 3.2V 在这种外形的下载器上可能来自内部，**不能代替测量主控电压**。

- **7/8 的 3.3V、9/10 的 5V 均不接。** 不把两份电源并联。
- **1 / RST、5 / SWIM 先不接。** 该 RST 可能属于 STM8 SWIM，照片不足以证明它是可用的 ARM nRESET。
- 核心板 A19/A20 的字样被遮挡或没有可插排针时，先核对实物引出点；不要往芯片引脚临时搭线，不要把 UART A10/A11 当 SWD。
- 电池、舵机、K230 暂不连接。紫色金属外壳和裸露插针不要放在通电 PCB 的焊点上。
- 这条 SWD 路线不需要先按 BSL。需要复位配合时再按具体检测步骤操作，不连续按键猜时序。

## 电脑上已配置的入口

| 文件 | 作用 |
|---|---|
| `tools/检查STLink下载器.bat` | 读取下载器版本；未接主控时出现 target-connect error 属预期，版本通过不等于主控通过 |
| `tools/检测STLink主控连接_不烧录.bat` | 尝试 SWD 初始化、读取 MAIN Flash 信息和 CPU ID；不擦除、不编程 |
| `tools/stlink_probe.ps1 -Mode Offline` | 仅验证配置，不打开下载器 |
| `tools/openocd/mspm0_stlink.cfg` | ST-Link direct SWD、100kHz、MSPM0 目标；关闭远程调试服务端口 |
| `tools/openocd/logs/` | 每次检测日志 |
| `tools/downloads/openocd_f13e839/SOURCE.json` | 下载来源、提交号、归档校验值 |

目标检测虽然不改写 Flash，但 TI 的 OpenOCD 初始化会通过调试寄存器唤醒/复位主控，不能将它描述为完全没有状态变化的只读操作。检测脚本没有程序镜像参数，不执行 `program`、`erase`、`mspm0_factory_reset` 或 `mspm0_mass_erase`。

待识别芯片后，再为已检查的 MAIN-only HEX 配置烧录和读回校验。现有 Keil 工程及 HEX 保持原样，动作输出仍关闭。不要在 Keil 中套用 STM32 的 ST-Link Flash 算法，也不要用 STM32CubeProgrammer 给 TI 芯片烧录。

## 资料

- [TI MSPM0 调试与编程工具：OpenOCD](https://software-dl.ti.com/msp430/esd/MSPM0-SDK/latest/docs/english/tools/doc_guide/doc_guide-srcs/debug_program.html#openocd)
- [OpenOCD ST-Link 驱动及固件要求](https://openocd.org/doc-release/html/Debug-Adapter-Configuration.html)
- [OpenOCD 官方下载说明](https://openocd.org/pages/getting-openocd.html)
- [本次源码提交](https://github.com/openocd-org/openocd/tree/f13e839c56fa88d9db321c7543a9b0d72c5fc4f4)
- [TI MSPM0G3507 数据手册：PA19/SWDIO、PA20/SWCLK](https://www.ti.com/lit/ds/symlink/mspm0g3507.pdf)
