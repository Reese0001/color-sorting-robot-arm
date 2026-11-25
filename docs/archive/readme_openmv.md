# 三色方块自动分拣机械臂

一个可复现的课程设计/毕业设计项目：机械臂末端安装 OpenMV 摄像头，识别红、绿、蓝三种方块，并由 STM32 精准控制舵机，将方块放入对应颜色的分拣区。

## 功能

- OpenMV 基于 LAB 色彩空间识别红、绿、蓝色块
- 通过面积、长宽比和像素数过滤噪声
- UART 向 STM32 发送颜色、中心坐标和面积
- STM32 状态机自动完成待机、抓取、搬运、释放、复位
- PCA9685 以 50 Hz PWM 驱动 4 个舵机
- 采用缓入缓出插值，减少抖动和机械冲击
- 每个舵机可独立校准角度与脉宽
- 串口命令支持单步调试、手动分拣和急停

## 系统结构

```text
红/绿/蓝方块
      │ 图像
      ▼
OpenMV 摄像头 ── UART 115200 ── STM32F103C8T6 ── I²C ── PCA9685
                                                     │
                                              4 路舵机机械臂
```

机械臂采用预标定点位分拣。摄像头固定在机械臂末端或抓取区上方；方块进入固定抓取窗口后，OpenMV 连续识别到同一颜色 5 帧，STM32 执行抓取动作，再放到红、绿、蓝三个指定区域。

## 推荐硬件

| 模块 | 推荐型号 | 数量 |
| --- | --- | ---: |
| 视觉模块 | OpenMV H7 / H7 Plus | 1 |
| 主控 | STM32F103C8T6 最小系统板 | 1 |
| PWM 驱动 | PCA9685 16 路舵机驱动板 | 1 |
| 舵机 | MG996R（底座/大臂/小臂）+ MG90S（夹爪） | 4 |
| 电源 | 5~6 V、至少 5 A 舵机独立电源 | 1 |
| 机械结构 | 4 自由度机械臂套件 | 1 |

> 舵机电源不要直接取自主控板。舵机电源、STM32、OpenMV 必须共地。

## 接线

| 设备 | 引脚 | 连接 |
| --- | --- | --- |
| OpenMV | P4 / UART3 TX | STM32 PA10 / USART1 RX |
| OpenMV | P5 / UART3 RX | STM32 PA9 / USART1 TX（可选） |
| STM32 | PB6 / I²C1 SCL | PCA9685 SCL |
| STM32 | PB7 / I²C1 SDA | PCA9685 SDA |
| STM32 | 3.3 V | PCA9685 VCC（逻辑电源） |
| 舵机电源 | 5~6 V | PCA9685 V+ |
| 全部模块 | GND | 共地 |

## 快速开始

### 1. 标定 OpenMV 颜色阈值

1. 在 OpenMV IDE 中打开 `openmv/color_tracking.py`。
2. 使用 **Tools → Machine Vision → Threshold Editor** 分别框选三种方块。
3. 将得到的 LAB 阈值填入脚本中的 `COLOR_THRESHOLDS`。
4. 保持实际运行时的光照、背景和曝光设置不变。

### 2. 上传 OpenMV 程序

连接 OpenMV，在 IDE 中运行脚本。串口会输出：

```text
BLOCK,RED,81,62,2450
```

字段依次为消息类型、颜色、中心 X、中心 Y、色块面积。未识别到有效方块时发送 `NONE`。

### 3. 编译 STM32 固件

安装 [PlatformIO](https://platformio.org/)，在仓库根目录执行：

```bash
pio run
pio run --target upload
pio device monitor
```

### 4. 校准舵机和点位

先拆下舵机连杆，使用串口命令逐个设置到 90°，再装回机械结构。修改 `firmware/src/config.h` 中：

- `SERVO_CALIBRATIONS`：每个舵机的最小/最大脉宽及安全角度
- `POSE_HOME`：待机位
- `POSE_PICK`：抓取位
- `POSE_RED/GREEN/BLUE`：三个投放位

串口调试命令：

```text
HELP
HOME
SORT RED
SORT GREEN
SORT BLUE
SERVO 0 90
STOP
```

## 分拣流程

1. 机械臂回到待机位并等待稳定识别。
2. OpenMV 连续 5 帧识别到同色方块，且中心位于抓取窗口内。
3. STM32 移动到抓取位，闭合夹爪。
4. 抬起方块并移动到对应颜色的投放位。
5. 打开夹爪，机械臂返回待机位。

## 目录

```text
.
├── docs/
│   └── protocol.md          # 通信协议与调试说明
├── firmware/
│   └── src/                 # STM32 控制程序
├── openmv/
│   └── color_tracking.py    # OpenMV 颜色识别
├── platformio.ini
└── README.md
```

## 安全注意事项

- 首次运行时不要安装夹爪负载，并准备随时断开舵机电源。
- 必须设置合理的舵机软限位，禁止让舵机持续顶住机械限位。
- 电源线建议串联保险丝；大电流舵机附近增加 1000 µF 电容。
- 按 `STOP` 或发送串口命令 `STOP` 可中止当前动作。

## 可选 K210 方案

K210 可用 MaixPy 的 `find_blobs()` 替代 OpenMV 脚本，并保持相同 UART 文本协议，STM32 端无需修改。建议先完成 OpenMV 版本，再迁移至 K210。

## License

MIT
