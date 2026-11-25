# Robot1 方块分拣机械臂

课堂使用 **MSPM0G3519 + K230**。先下载资源包，完整解压后打开 `00_先读我.txt`。只需要打印讲义时，可直接下载六页手册；第 6 页是小组调试记录单。

**[下载课堂调试资源包](dist/Robot1机械臂课堂调试资源包.zip?raw=1)** · [打开调试手册](output/pdf/Robot1机械臂同学调试手册.pdf) · [查看核心板排针图](output/mspm0g3519/grouped_pinout.png)

## G3519 实验顺序

| 实验 | 文件与观察结果 |
| --- | --- |
| 核对 OLED 与测距 | OLED 时钟接 **A22** 时选 [成组接线只读固件](output/mspm0g3519/grouped_wiring_readonly.hex)，接 **A12** 时选 [只读固件](output/mspm0g3519/wiring_test.hex)。移动纸板，记录两次 `TOF … MM`。 |
| 验证 K230 双向串口 | 在 CanMV IDE 临时运行 [回显脚本](firmware/g3519_wiring_test/k230_link_test.py)，在主控屏幕确认 `K230 LINK OK`。 |
| 标定方块颜色 | 按 [K230 视觉说明](vision/k230/README.md) 运行 [五色识别脚本](vision/k230/three_color_blocks.py)。[A4 标定纸](output/pdf/K230_A4_calibration_map.pdf) 按实际大小打印。 |
| 读取关节与夹爪 | 参照手册第 5 页逐只读 ID。总线按键点动和 24 路 PWM 专测固件见 [固件目录](output/mspm0g3519/)，程序实现见 [G3519 源码](firmware/g3519_wiring_test/)。 |

首次调试保持舵机动力断开，曾冒烟的云台支路停用。新夹爪 ID、双向串口以及整机抓放仍需在当前设备上确认。课堂资源包附有烧录图解、幻尔上位机和实物照片；TI UniFlash、CanMV IDE 需另行安装。

## 其他主控工程

| 硬件与项目 | 使用入口 |
| --- | --- |
| MSPM0G3507 固定点分拣 V1 | [接线、构建和七姿态示教](README_G3507_V1.md)，主控在 `firmware/mspm0/`。 |
| MSPM0G3507 Keil 台架 v2.1 | [代码导航](docs/代码导航.md) 和下面的台架快照，主控在 `firmware/keil/` 与 `firmware/src/*.c`。 |
| STM32F103 / OpenMV 早期实验 | [归档说明](docs/archive/readme_openmv.md)，PlatformIO 使用 `firmware/src/*.cpp`。 |

各工程的引脚和串口协议不同。请先看板卡丝印，再进入对应教程。

## G3507 Keil 台架记录（2026-11-03）

源码整理快照：2026-11-03。主控已烧录并运行 **robot bench v2.1**，整段/分段 CRC、调试串口和三色七步模拟通过。实际舵机动作、整臂标定、视觉到抓取闭环尚未完成。

### 台架文档

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

### 台架目录

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

台架快照的文件清单见 `PACKAGE_MANIFEST.json`，第三方来源见 [许可说明](THIRD_PARTY_NOTICES.md)。
