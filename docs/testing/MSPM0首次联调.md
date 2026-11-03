> **2026-11-03 实测通过：16KiB Flash CRC、应用串口、三色七步模拟。** 当前只接核心板 USB，COM8 / 115200 / 8N1；舵机输出关闭。见 [实测记录](2026-11-03恢复烧录记录.md)。

# MSPM0 首次联调（无舵机）

**2026-11-03 更新：板载 CH340 COM8 已完成下载和应用收发。** 先看 [USB BSL 下载准备](USB_BSL下载准备.md) 和 [实物接线与首次烧录](实物接线与首次烧录.md)。Keil 环境版本限制及可选 SWD 接线在后者说明。

## 已验证

2026-10-29：主控方案改为 MSPM0G3507，完成 Keil 源码工程。Arm Compiler 6.7 编译及链接通过（0 错误、0 警告），生成 HEX；协议模块在本机 GCC 执行 **65 项断言检查通过**。

2026-11-03 已完成本板烧录、整段及分段 CRC、UART PING/STATUS、三色七步模拟流程。尚未测量 PWM 波形或驱动舵机。

2026-10-29 基础版 Keil GUI 编译记录：Code=10900B、RO-data=648B、RW-data=0B、ZI-data=2880B；
MAIN Flash 从 `0x00000000` 开始，RAM 使用 `0x20200000` 别名，向量表起始地址正确。
编译记录位于 `firmware/keil/Objects/robot_mspm0.build_log.htm`，映射文件位于 `firmware/keil/Listings/robot_mspm0.map`。

2026-11-01 对 `robot bench v2.1` 全量重新编译：**0 错误、0 警告**，Code=14228B、RO-data=2084B、RW-data=0B、ZI-data=2928B。本机再次通过 65 项协议断言、134 项流程断言和共享 DLL 三色路线演练。这些是当时的电脑侧结果；11 月 3 日新增板端验证见上文。

## 现在可以做的测试

1. 打开 `firmware/keil/robot_mspm0.uvprojx`，按 F7 编译。当前 USB BSL 使用项目自建下载脚本，不是 Keil 的 Load 按钮。重新编译后要先复核固件再更新下载工具固定哈希。
2. 保持 `MOTION_OUTPUT_ENABLE=0`、`BUS_PROTOCOL_CONFIRMED=0`，不接舵机动力电源。确认实际主控板支持表中 PA 引脚且无板载冲突后再烧录。
3. 程序已烧录并启动，关闭其他串口工具后，用板载 COM8 打开 115200、8N1，应收到每秒一次 STATUS；只按 RST 可看到启动版本。无需另接 USB-TTL。
4. 发送 `PING`、`HELP`、`STATUS`，回车换行。未接 K230 时应显示 `online=0 target=NONE motion=0 armed=0 bus=0`。
5. 暂时不用 K230 时，可用第二个 3.3V USB-TTL 的 TX 接 PA18、GND 共地，发送模拟帧。不要把两个发送器同时接到 PA18。

```powershell
python tools/k230_sender.py --scene red
# 上面只打印一帧，不打开串口。
# 确认实际 COM 端口、接线后再运行：
python tools/k230_sender.py --port COM5 --scene red --count 50
```

发送功能需要 `pyserial`；工具缺少依赖时会直接报错，不会自行安装或打开其他端口。`COM5` 只是示例，应替换成实际适配器端口。

## 预期结果

| 输入 | 调试串口应看到 |
|---|---|
| 持续合法红色帧 | online=1、target=RED、坐标(320,240)，ok 增长 |
| `--scene green` / `blue` | 对应 GREEN / BLUE |
| `--scene none` | online=1、target=NONE；旧目标不再有效 |
| `--bad-checksum` | bad 增长，坏帧不续在线时间 |
| 停止发送超过 500ms | online=0、target=NONE；状态每秒打印，显示可能晚于500ms |
| 发送 ARM/PWM/MOVE | 报锁定错误，舵机信号仍不输出动作 |

之后把模拟发送器换成 K230 GPIO9。核对实际 K230 通信口后，将视觉脚本中的 `UART_ENABLED` 改 True，再用真实目标测试。当前图像中的 pan/tilt 仍是占位角度。

## 舵机到货后

先提供/核对：主控及扩展板正反面和接口图、幻尔转换板型号、两台25kg舵机型号、电源模块规格。四个总线舵机逐个设置不同 ID，逐个确认限位；云台先用示波器/逻辑分析仪核实 20ms 周期与脉宽，再接负载。仅在这些完成后修改开关、逐台手动测试。

相机随机械臂运动，最终自动寻找/抓取还需要观察姿态、关节零位和方向、连杆长度、夹爪开闭范围、相机标定和坐标转换。现在代码仅显示候选目标，没有将像素坐标直接换成关节角。
