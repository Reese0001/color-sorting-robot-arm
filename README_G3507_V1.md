# 三色方块分拣机械臂 第一版

硬件：K230 豪华版、MSPM0G3507 核心板与扩展板、BusLinker V2.5、两只 HTD-35H、一只 HTS-21H 夹爪、亚博 20 kg·cm 底座转向舵机和 25 kg·cm 第一关节舵机。

第一版采用固定抓取点与七个实物示教姿态。支持视觉识别、带校验串口通信、两路 PWM、三只总线舵机、平滑动作、位置反馈、手动分拣和自动状态机。上电只读位置，不自动运动。

## 从这里开始

首次使用先看 [从零开始：完整代码与接线操作入口](docs/从零开始.md)，再按以下详细教程执行。

1. [接线教程](docs/wiring_v1.md)：关节编号、引脚、电源、下载器。
2. [烧录与测试教程](docs/testing_v1.md)：从单模块到示教、保存参数、完整分拣。
3. [K230 标定说明](vision/k230/README.md)：颜色阈值和工作区域。
4. [通信协议](docs/protocol.md)：K230、调试终端与总线协议。
5. [验证记录](docs/validation_v1.md)：本地通过项目和待完成的实机测试。

## 编译和测试

```powershell
python tools/build_firmware.py
python -m pytest tests -q
python tools/test_firmware.py
```

环境安装和本机 SDK 头文件补齐方法见测试教程。输出 `build/mspm0/robot1.out` 和 `robot1.hex`。打包执行 `python tools/package_v1.py`，得到 `dist/robot1_v1.zip`。

## 当前目录

| 路径 | 用途 |
| --- | --- |
| firmware/mspm0/ | 本版 C 固件、HAL、配置及 SysConfig |
| vision/k230/ | 五色视觉程序与 UART 协议 |
| tools/ | 目标编译、C 模拟测试、电脑串口终端、打包 |
| tests/ | Python 回归和 C 控制核心测试 |
| docs/ | 接线、标定、测试与协议 |
| hardware/photos_preview/ | 用户提供硬件照片的本地预览 |

`firmware/src/`、`openmv/` 和 `platformio.ini` 为此前 STM32/PCA9685/OpenMV 参考文件，其中的 STM32/OpenMV 文件不参与本版构建。原 README 和协议已保存在 `docs/archive/`。不要把旧方案的引脚、脉宽或协议直接用于当前硬件。

## 使用边界

固件和本地模拟通过不代表实机已验证。机械姿态没有通用安全数值，必须先做单关节验证和实物示教。程序默认没有预填姿态；参数在 RAM 中，使用 DUMP 导出、POSE/GRIP 恢复。

本版无逆运动学、任意位置抓取、夹持力检测或 PWM 位置反馈。软件 STOP 保持动力，不是物理断电急停。具体限制及恢复步骤见测试教程。
