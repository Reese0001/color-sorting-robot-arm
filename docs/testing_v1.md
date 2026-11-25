# 第一版烧录 标定 示教和测试教程

第一版完成固定抓取点的红绿蓝分类。观察姿态、抓取点和三种颜色的投放点通过实物示教获得，不包含任意位置抓取或逆运动学。软件已做电脑端测试及 TI 目标编译，未执行实机测试。

## 1 编译与烧录

PowerShell 在项目根目录执行：

```powershell
cd D:\DevProject\robot1
python tools/build_firmware.py
```

依赖默认位置：TI SDK `C:/TI/mspm0_sdk_2_10_00_04`、SysConfig `C:/TI/sysconfig_1.26.2`、TI Arm Clang `D:/DevTools/ti/ccs2050/ccs/tools/compiler/ti-cgt-armllvm_4.0.4.LTS/bin/tiarmclang.exe`。
路径不同时用 `--sdk`、`--sysconfig`、`--compiler` 参数指定。本机原 SDK 缺失若干头文件，首次在新目录构建可运行：

```powershell
python tools/build_firmware.py --repair-sdk
```

该选项只从 TI 官方 SDK 2.10.00.04 固定提交下载缺失头文件到 `build/sdk_overlay`，不修改全局 SDK。
成功生成 `build/mspm0/robot1.out`、`robot1.hex` 和 `robot1.map`；代码仅使用 `firmware/mspm0`，不要执行旧 `pio run`。

保持舵机动力电源断开，按接线教程连接兼容 MSPM0 的 SWD 探针。在 UniFlash 新建 MSPM0G3507 会话，选择实际探针，加载 `robot1.out` 或 `robot1.hex`，执行擦写和验证，再复位运行。不要改芯片保护/锁定选项。程序不烧写标定参数或启动自动动作。

## 2 调试终端

使用独立的 3.3V USB-TTL 接 PA14/PA13/GND，在设备管理器查 COM 号：

```powershell
python -m pip install pyserial
python tools/console.py COM7
```

这里 COM7 仅为示例。输入 `HELP` 和 `STATUS`，应看到 `armed=0 moving=0 auto=0 cycle=0 fault=0`。此时 `online=0` 表示总线尚未接好，不是自动运动。
终端输入 `QUIT` 或按 Ctrl+C 会发送 STOP 后退出。串口窗口中命令使用大写，字段之间一个空格，每条以换行结束。

先按扩展板 K1，应出现 `STOP K1`。松开后输入 `CLEAR`，恢复到未使能状态。必须确认这一步再接机械负载。

## 3 K230 单独标定

将 `vision/k230/three_color_blocks.py` 和 `robot_link.py` 复制到 K230 的 `/sdcard/` 根目录，保留已有 `libs` 目录。
在 CanMV IDE 停止原程序，再运行 `three_color_blocks.py`；第一次不覆盖板上的开机 `main.py`。

按照 `vision/k230/README.md` 完成三种颜色的取样和识别测试。要让摄像头处于预定 HOME 观察姿态、对准工作台，排除绿色机械臂。首次可以先粗调观察姿态，待机械臂示教后重新标定。
确认识别后设 `CALIBRATED = True`、`MODE = "detect"`。连接通信线并设 `UART_ENABLED = True`，重新运行。

本版固件默认抓取窗口中心是画面 `(320,240)`，容差 ±25 像素。将固定抓取位置标在桌上，在 HOME 姿态下让方块中心投影到这个窗口。需要修改窗口时编辑 `robot_config.h` 中 `PICK_X/Y`、`PICK_TOL_X/Y` 后重新编译。
这一步建立的是固定点对应关系；不能把画面里任意位置的方块直接交给当前机械臂抓取。

## 4 总线舵机检查

按接线教程把 J3、J4、J5 的 ID 分别设置为 1、2、3，全部为位置模式并启用舵机控制。读取位置可以在 MCU 未 ARM 时进行，不会发送移动命令。
给 BusLinker 和舵机供电后输入 `STATUS`，应看到三个位置数值和 `online=1`。超过 700 ms 没有任一舵机反馈，就不能 ARM。
若一直 `online=0`，先排查 ID 冲突、总线电源、TX/RX、电平、USB 与 MCU 同时占用，不要不断发送 ARM。

## 5 首次使能与单关节小步调试

固件初始软限位：J1/J2 为 1200～1800 µs，J3/J4/J5 为 200～800。它们是保守的起步范围，不是实测机械限位；也不保证你当前安装姿态在范围内。
先支撑机械臂、卸下 PWM 舵机连杆或确保其能自由运动，总线位置必须在配置范围内。确认 1500 µs 是两只 PWM 舵机可接受的位置后才输入：

```text
ARM 1500 1500
STATUS
JOG 1 1520 1000
```

`ARM` 后两路 PWM 从无信号开始输出指定脉宽，可能立即运动；总线舵机当前位置由反馈读取，不在 ARM 时自动回中。
`JOG 1 1520 1000` 表示 J1 在 1000 ms 内从当前命令位置平滑移动到 1520 µs。J2 同理；J3/J4/J5 的值是总线位置单位。
总线单关节调试要以 `STATUS` 读到的位置为起点，每次只增加或减少 5～10 单位，不直接照抄一个不相关的目标。

运动时按 K1 或发送 STOP，必须停止后续轨迹。之后 `CLEAR`，再次 ARM 时使用 PWM 当前已知的脉宽，不要盲目回到 1500。
`CLEAR` 不能中断运动，运动中必须先 STOP。STOP 保持动力；切电前支撑承重关节。

记录每个关节的正方向和不碰限位的范围，再修改 `robot_config.h` 的边界。两路 PWM 当前共用一组起步边界，若实际范围不同，先取两者都安全的交集；不要为了一个关节扩大后让另一个越界。

## 6 示教七个姿态和夹爪开闭

将机械臂组装到经调试的姿态。逐步用 JOG 调到以下姿态，每次等待 `DONE motion`，确认实际位置和路径没有碰撞，再输入 TEACH：

| 命令 | 应记录的姿态 |
| --- | --- |
| `TEACH HOME` | 摄像头朝向固定抓取点、机械臂待机 |
| `TEACH APPROACH` | 接近方块上方 |
| `TEACH PICK` | 夹爪到达方块两侧，尚未夹紧 |
| `TEACH LIFT` | 抓取后抬高，便于搬运 |
| `TEACH RED` | 红色投放区 |
| `TEACH GREEN` | 绿色投放区 |
| `TEACH BLUE` | 蓝色投放区 |

TEACH 读取两路 PWM 的当前命令值和三只总线舵机的反馈位置。PWM 没有位置传感反馈，必须人工核实。
通过 JOG 5 分别找到夹爪合适的打开和闭合位置，然后输入 `GRIP 打开值 闭合值`，两值均为原始位置单位。夹紧值应能夹持方块，不持续顶住机械限位。
TEACH 保存的夹爪值在自动序列中会被 GRIP 开闭值覆盖；单独 GOTO 使用姿态中原始保存的五个值。

`GOTO HOME` 等命令用于验证单姿态。自动阶段默认每段运动 1800 ms、结束后等待 400 ms，并检查总线关节是否到达目标；超时会 STOP。按顺序验证 APPROACH→PICK→LIFT→各投放点→LIFT→HOME，每一段的中间路径也必须无碰撞。

## 7 保存和恢复示教数据

第一版参数只保存在 RAM，掉电丢失，不写 Flash。输入：

```text
DUMP
```

把终端输出的所有 `POSE ...` 和 `GRIP ...` 行复制到你自己的 UTF-8 文本文件，例如 `poses_measured.txt`。这是实测数据，不要用示例数值代替。
重启后可以逐条粘贴，或使用：

```powershell
python tools/console.py COM7 --restore poses_measured.txt
```

工具只重放 POSE/GRIP 行，不重放 ARM/JOG/AUTO；检查每行是否收到 OK。恢复后仍需单独 ARM，并确认机械臂当前位置及场地没有改变。

## 8 手动完整分拣

七个姿态、夹爪开闭全部记录且 ARM 后，依次运行：

```text
SORT RED
SORT GREEN
SORT BLUE
```

一次只发一条，等待 `DONE cycle` 再发下一条。首轮空载，确认动作顺序；再在固定抓取位置放方块。
流程是接近→下降→夹紧→抬起→投放→打开→抬起中转姿态→HOME。程序不会检测夹爪内是否真的抓到方块，也没有力传感反馈。

## 9 自动分拣

K230 识别和串口已运行、全部点位已示教、ARM 完成后输入 `AUTO`。
机械臂先回 HOME，主控向 K230 发送新的 OBS 批次，等待至少 1.5 秒让相机画面稳定。
先让工作区无有效方块，再将一个方块放到桌面标记的抓取位置。主控要求：已标定、目标稳定、位于抓取窗口、连续 3 个同色有效新帧。

抓取过程中主控不接受新的目标触发。完成后回 HOME，换一个 OBS 批次，重新要求一次空场景，再识别下一块。这是半自动上料的固定点分拣，批次切换和空场景要求用于防止同一结果反复触发。
如相机工作区里还有其他待分拣方块，也可能无法获得空场景；第一版一次上料一个方块。

## 10 必做故障试验

| 操作 | 预期结果 |
| --- | --- |
| 上电不发 ARM | 无 PWM 周期输出，无总线移动命令，仅位置查询 |
| 未示教直接 AUTO | 拒绝 |
| 输入超出边界的 JOG/POSE | 拒绝 |
| 任意动作中 STOP/K1 | 轨迹停止，保持输出，不继续下一阶段 |
| STOP 后直接 AUTO/ARM | 拒绝，必须 CLEAR 后恢复 |
| 拔掉一只总线舵机反馈链路 | 反馈超时后停止；注意总线拔插应使用信号隔离测试，不带载拔电源 |
| 舵机被阻挡不能到达 | 运动期限加约 2.5 秒后停止；不要用手强行卡住关节，使用模拟/无负载小范围验证 |
| 在 HOME 等待时停止 K230 程序 | 约 3 秒无有效帧后停止；首次观察含 1.5 秒静置宽限 |
| 抓取中停止 K230 | 已锁定的动作周期继续，回 HOME 后等待超时停止 |
| 错校验、重复序号、旧 OBS 批次 | 不触发抓取 |
| CPU 主循环停滞 | 约 250 ms 硬件看门狗复位，回到未使能状态；PWM 消失，承重结构需要支撑 |

每项记录通过/失败及视频或日志。编译成功、本地模拟通过，都不能替代这些实物验收。

## 11 本地测试重跑

```powershell
python -m pip install pytest ziglang pyserial
python -m pytest tests -q
python tools/test_firmware.py
python tools/build_firmware.py
```

Python 测试覆盖视觉与串口封包。C 测试编译并执行实际控制核心，模拟舵机反馈、完整动作周期与异常；不连接任何真实硬件。

