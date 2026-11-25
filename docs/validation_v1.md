# 第一版验证记录

## 2026-11-13 PWM 引脚调整

- 按用户要求，J1 从 PB8 改为 PB18/TIMA1 CCP1，J2 从 PB9 改为 PB19/TIMG8 CCP1。两个独立定时器均使用 1MHz 计数、20000 周期，ARM 前不启动；HAL 同步更新两个定时器的通道1。
- TI SysConfig 校验和 TI Arm Clang 编译、链接通过；生成配置确认两路引脚及初始停止状态。实物 PWM 波形、扩展板连线、舵机方向及限位待测。
- 本节更新取代下方历史记录中的 PB8/PB9 分配。

日期：2026-11-06。实物上电、波形和抓取试验尚未执行。

## 2026-11-13 实物接口适配

- 照片中未见 PA10/PA11 外部引出，将 CONSOLE 改为 UART3 PA14 TX / PA13 RX；K230、BusLinker 和 PWM 分配保持原配置。
- TI SysConfig 引脚校验与 TI Arm Clang 目标编译、链接通过，生成新的 robot1.out / robot1.hex；生成头文件确认 CONSOLE=UART3，TX=GPIOA14，RX=GPIOA13。
- 接线、协议、从零开始、测试教程与 console.py 帮助同步更新；实物 UART 电平、板内连线、供电与舵机运动仍待现场验证。

## 2026-11-09 重新验证与交付

- 基于现有完整代码补充 `docs/从零开始.md`，包含代码入口、信号接线图和完整操作顺序；未修改控制或视觉算法。
- 重新执行 TI SysConfig、TI Arm Clang 目标编译和链接成功，重新生成 OUT/HEX/MAP。
- Python 回归：45 项通过。现有 `.pytest_cache` 写入权限导致一条缓存警告，不影响测试结果。
- 使用 Zig 编译并执行实际 `robot.c` 的主机模拟：通过，包括运动、限位、启动、停止恢复、反馈故障、手动/自动周期、重放/批次检查及相机超时。
- 本次测试依赖安装在 `build/python_deps`，未改变系统 Python 包。此机器重跑时先设置 PowerShell 环境变量 `$env:PYTHONPATH = "$PWD/build/python_deps"`；C 测试另设 `$env:ZIG_GLOBAL_CACHE_DIR = "$PWD/build/zig_cache"`。其他机器可按测试教程正常安装依赖。
- 交付 ZIP 包含完整项目源码、教程、测试与本次编译固件。实机接线、上电、波形与抓取仍未验证。

## 原始验证范围

| 检查 | 状态 | 范围 |
| --- | --- | --- |
| TI SysConfig 引脚分配 | 通过 | 三 UART、TIMA0 两 PWM、PA2 按键、SWD、WWDT |
| TI Arm Clang 4.0.4 目标编译与链接 | 通过 | 真实 MSPM0G3507 Cortex-M0+ 固件，生成 OUT/HEX/MAP |
| Python 回归 | 45 项通过 | 视觉筛选、跟踪、取样、模式切换、串口封包与观察指令解析 |
| C 核心主机模拟 | 通过 | 编译实际 robot.c；限位、平滑轨迹、STOP/CLEAR、反馈超时、到位超时、三色目的地、手动及自动周期、校验、重放与观察批次、相机断连、半双工应答期间禁止发送 |
| K230 上板 | 待测 | 固件 API、实景阈值、帧率、UART 引脚 |
| MSPM0 上板 | 待测 | 时钟、UART 电平、PWM 极性/脉宽、K1、WWDT |
| 整机动作 | 待测 | 关节方向、限位、电源能力、姿态路径、夹持效果 |

构建发现全局 SDK 缺少 13 个头文件；已由构建脚本从 TI 官方 SDK 同版本提交 `e249e2bd63bcc912176a30a45a6a5dcea951168b` 补齐到 `build/sdk_overlay`。保留原版权声明，不修改全局 SDK。换机器可使用完整 SDK 或 `--repair-sdk` 重建独立补充目录。

C 模拟中的舵机按测试条件返回位置，不包含真实力矩、机械碰撞、UART 电气和图像识别。测试通过不表示整机已验收；按 `testing_v1.md` 逐项填写实测结果。

