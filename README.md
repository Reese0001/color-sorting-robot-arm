# 红绿蓝分拣机械臂：MSPM0G3507 + K230

源码整理快照：2026-11-03。主控已烧录并运行 **robot bench v2.1**，整段/分段 CRC、调试串口和三色七步模拟通过。实际舵机动作、整臂标定、视觉到抓取闭环尚未完成。

## 先打开这几份文件

- [每个环节的重要代码](docs/代码导航.md)
- [软件与运行方式](docs/软件与运行方式.md)
- [GitHub 上传说明](docs/GitHub上传说明.md)
- [通信协议](docs/通信协议.md) 和 [接线说明](hardware/wiring/MSPM0G3507接线.md)
- [实物验收记录](docs/testing/2026-11-03恢复烧录记录.md)

| 想做什么 | 打开什么 | 使用软件/实际运行位置 |
|---|---|---|
| 查看或修改主控代码 | `firmware/keil/robot_mspm0.uvprojx` | Keil5 编辑/编译；固件运行在 MSPM0 |
| 查看摄像头识别代码 | `vision/k230/color_detection.py` | CanMV IDE K230；程序运行在 K230 |
| 电脑上演练流程 | `tools/打开无舵机演练.bat` | Python 3 + MinGW GCC；运行在电脑 |
| 复测已烧录的主控 | `tools/板端三色流程自检_不动舵机.bat` | PowerShell 7；需要主控 USB |
| 重新下载主控固件 | `tools/USB直接烧录_自动等待BSL.bat` | Python 3 + PowerShell 7/.NET；USB BSL |
| 运行离线测试 | `python tools/run_pc_checks.py` | 电脑上的 Python + GCC，不连接板子 |

## 文件夹

```text
firmware/
  keil/       Keil 工程、启动汇编、链接文件、已实测 HEX
  src/        主控入口、外设驱动、模拟流程、关节配置
  include/    接口和参数头文件
  lib/        K230 协议解析、幻尔总线协议
  vendor/     必要 TI/CMSIS 源码及许可
vision/k230/  相机自检、阈值标定、颜色识别
  archive_k230_pwm/  旧 K230 控云台试验，非当前入口
tools/        电脑模拟、串口、烧录、测试工具
tests/        C/Python 离线测试
docs/         代码导航、软件说明、协议、验收记录
hardware/     接线说明
```

当前默认 `MOTION_OUTPUT_ENABLE=0`、`BUS_PROTOCOL_CONFIRMED=0`。`START RED/GREEN/BLUE` 是模拟流程，不会驱动机械臂。不要只把两个开关打开就当作标定完成。

K230 源码本次只收录，未写入或运行 K230。当前识别主线使用 `@T` 协议，主控为 MSPM0；某些旧脚本注释中的 STM32 是早期名称，不能照其旧引脚接线。

这是便于查看和上传 GitHub 的源码目录，没有自动上传。原工作区继续保留，后续选择一个目录统一开发，避免双份混改。打包信息在 `PACKAGE_MANIFEST.json`，第三方说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
