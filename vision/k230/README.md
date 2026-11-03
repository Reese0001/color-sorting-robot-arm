# K230 视觉代码

用 **CanMV IDE K230** 打开，实际运行在 K230 板子；不是电脑 Python，也不是 Keil 工程。

1. `camera_check.py`：相机与显示自检。
2. `auto_calibrate.py`：真实物品/现场光照采样，得到 LAB 阈值；现场效果待验证。
3. `color_detection.py`：识别红绿蓝、稳定判断、像素坐标和 `@T` 串口帧。默认 UART_ENABLED=False。

当前接收主控为 **MSPM0G3507**。预留 UART1：主控 PA18=RX、PA17=TX；K230 GPIO9/10 仍须对照实际板型确认，不能沿用旧 STM32 PA2/PA3 接线。参见 [接线表](../../hardware/wiring/MSPM0G3507接线.md) 和 [通信协议](../../docs/通信协议.md)。

本次只复制现有 Python 文件，未修改其字节内容，也未连接 K230。文件里的某些 STM32 注释及扫描提示来自旧阶段，不能作为当前硬件接线依据。

`archive_k230_pwm/` 保存旧的扫描/引脚试探代码，仅供追溯，不运行。当前方案由 MSPM0 驱动云台，扫描、相机标定和自动抓取闭环还未实现。
