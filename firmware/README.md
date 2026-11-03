# MSPM0G3507 基础工程

实物首次接线与下载，请先看 [实物接线与首次烧录](../docs/testing/实物接线与首次烧录.md)。`robot bench v2.1` 于 2026-11-03 经板载 USB BSL 烧录并校验，UART 收发及三色七步模拟实测通过。ST-Link/SWD 尚未验证。

打开 `keil/robot_mspm0.uvprojx`，选择 `MSPM0G3507_Bench`，按 **F7** 编译。

- 主控：MSPM0G3507，Cortex-M0+，MAIN Flash 128KB，RAM 32KB。
- 时钟：内部 SYSOSC 32MHz；不依赖主控板外部晶振。
- UART0 调试、UART1 K230、UART2 幻尔转换板；全部 115200、8N1。
- TIMA1 两路云台 PWM，50Hz；默认停止并输出低电平。
- 动作/总线开关：`include/app_config.h`，均默认 0。
- 接口初始化：`src/board_mspm0.c`；通信与调试入口：`src/main.c`。
- 关节/姿态参数：`src/robot_config.c`，未知值保持未标定；纯模拟流程：`src/robot_workflow.c`。
- `START RED/GREEN/BLUE` 可演练七步流程，支持暂停、继续、中止、复位和故障注入，完全不调用舵机输出。
- 官方 TI DriverLib/CMSIS 源文件子集在 `vendor/mspm0_sdk/`，可离线编译，来源固定为提交 `20807db79aa17b49f87ab8ec87f6b6d63ee2cb32`。

没有调用 SysConfig 构建钩子；板级配置是人工维护的 C 文件。以后使用 SysConfig 时应对照当前串口/PWM引脚生成，不能拿其他例程的 `ti_msp_dl_config.c` 直接覆盖。

## 本机环境及限制

本次在现有 **Keil MDK 5.24a / Arm Compiler 6.7** 完成源码编译、链接和 HEX 生成，0 错误、0 警告。已补入官方设备包 `TexasInstruments.MSPM0G1X0X_G3X0X_DFP 1.3.1`，未升级或覆盖现有编译器。

TI 官方 MSPM0 Keil 流程要求 **MDK 5.38a+、Arm Compiler 6.16+**。当前旧版能够编译此工程，不代表下载/调试兼容性已经验证。实际调试前应升级到官方支持的组合并确认调试器；不要直接沿用旧 STM32 的 ST-Link 配置。参考 [TI 官方说明](https://dev.ti.com/tirex/content/mspm0_sdk_1_00_00_04/docs/english/quickstart_guides/doc_guide/doc_guide-srcs/quickstart_guide_keil.html)。

工程不启动调试、不自动下载、不自动执行外部脚本。链接地址为 Flash `0x00000000`、RAM 非校验别名 `0x20200000`，与 TI 示例一致；不配置 NONMAIN/BCR/BSL 区域。启动文件来自 TI，栈由 256B 扩大为 2048B，保留原版权。

生成文件在 `keil/Objects/robot_mspm0.hex` 和 `.axf`；这些产物不入 Git。请先按 [无舵机测试步骤](../docs/testing/MSPM0首次联调.md)验证，再决定下一阶段动作调试。

主控板没到时，双击 `tools/打开无舵机演练.bat` 可运行共享 C 逻辑的电脑窗口。
详见 [演练说明](../docs/testing/无舵机演练使用说明.md)。本轮新增 134 项流程检查；默认动作和总线开关仍为 0。
