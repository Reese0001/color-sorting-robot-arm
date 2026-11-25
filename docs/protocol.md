# 第一版通信协议

## 端口

MSPM0 UART3 PA14/PA13 为电脑控制台；UART1 PB6/PB7 为 BusLinker；UART2 PA21/PA22 为 K230。均为 115200 8N1。UART 和电源接线见 wiring_v1.md。

## MSPM0 向 K230

```text
OBS,1\n
OBS,0\n
```

非零值表示一次新的观察批次，0 表示忙碌/停止。批次变更时 K230 清空跟踪与稳定计数。每次完成 HOME 后主控增加批次；K230 回传相同数值。

## K230 向 MSPM0

```text
V1,epoch,seq,cal,color,x,y,pixels,stable,640*XX\n
```

`XX` 是星号之前全部 ASCII 字节按位异或的两位大写十六进制数，不包括星号和换行。示例可用 `robot_link.encode_frame` 生成，不手填校验。

| 字段 | 含义 |
| --- | --- |
| epoch | 主控的观察批次，32 位无符号 |
| seq | 每发送一帧递增，32 位回绕 |
| cal | 人工标定标记，0/1 |
| color | RED/GREEN/BLUE/NONE/UNKNOWN |
| x,y | 640×480 图像的像素中心坐标 |
| pixels | 匹配像素数 |
| stable | 视觉稳定标记，0/1 |
| 640 | 固定图像宽度标识，本版高度固定 480 |

NONE 仅用于无候选且没有颜色冲突/杂乱诊断的场景；跟踪歧义等情况发送 UNKNOWN。
K230 识别到黄色或紫色时，本地显示 YELLOW 或 PURPLE，V1 串口发送 UNKNOWN。现有主控只配置了红、绿、蓝三个分拣投放位。
主控要求新批次内先有已标定的 NONE，再出现三个连续同色、稳定、位于固定抓取窗口的新序号帧。错误校验、旧批次、重复/倒退序号不触发动作。候选间隔超过 500 ms 重新累计。
没有有效视觉帧约 3 秒时，在等待观察阶段停止；动作周期已经锁定颜色，会先完成当前周期再检查视觉等待超时。

UART_ENABLED 默认 False，只打印控制台 DETECT 文本。联调时设 True；calibrate/preview 模式不会向主控提供可抓取目标。

## 电脑命令

| 命令 | 功能 |
| --- | --- |
| HELP / STATUS | 命令表、状态与当前位置 |
| ARM p1 p2 | 明确使能两路 PWM，并以反馈初始化总线当前位置 |
| JOG joint value ms | 单关节平滑移动，joint=1..5，ms=500..10000 |
| TEACH name | 记录当前位置为姿态 |
| POSE name p1 p2 b1 b2 grip | 加载一组姿态，仅保存不运动 |
| GRIP open closed | 配置夹爪打开/闭合位置，仅保存 |
| GOTO name | 移动到已记录姿态 |
| SORT RED / GREEN / BLUE | 手动执行一次完整周期，不依赖视觉 |
| AUTO | 先 HOME，再按视觉执行固定点分拣 |
| STOP | 中止动作、保持输出、锁定故障状态 |
| CLEAR | 在停止状态清故障，保持未使能，需要再次 ARM |
| DUMP | 导出 POSE/GRIP 文本，供人工保存 |

姿态名：HOME、APPROACH、PICK、LIFT、RED、GREEN、BLUE。运动/自动/周期运行中只允许状态、导出、帮助和停止；CLEAR 不会中断动作。
STOP 不卸载承重关节。重启后 PWM 不启用，需支撑结构。参数仅在 RAM 保存。

## BusLinker 直接舵机协议

使用幻尔直接舵机报文，不使用多路舵机控制器的动作组协议：

```text
55 55 ID LENGTH COMMAND PARAMS CHECKSUM
```

LENGTH=参数字节数+3，CHECKSUM 为 ID 到最后一个参数的字节和按位取反的低 8 位。位置和运动时间采用低字节在前。用到的命令为 1（定时移动）、12（停止）、28（读位置）。位置读回仅接受匹配 ID、命令和校验的响应。
每个运动插值更新的总线目标持续 40 ms；主控通常每 20 ms 更新目标，连续轨迹由主控控制。每 80 ms 查询一只舵机，轮询三个 ID；查询后先等有效位置应答，最长等待 20 ms，这期间暂停发送移动报文，避免半双工碰撞。STOP 也在这次应答结束或等待超时后发送，总线停止指令可能额外延迟最多约 20 ms。任一位置反馈超过 700 ms 未更新则停止。

协议依据：[幻尔 LeArm AI 底层舵机示例](https://docs.hiwonder.com/projects/LeArm_AI/en/latest/docs/5.Basic_Development_Course.html)及[幻尔命令定义](https://github.com/Hiwonder/MaxArm/blob/main/Arduino/sensor_applications/%E8%B6%85%E5%A3%B0%E6%B3%A2%E6%A3%80%E6%B5%8B%2B%E6%95%B0%E7%A0%81%E7%AE%A1%E6%98%BE%E7%A4%BA%E7%A8%8B%E5%BA%8F%E6%96%87%E4%BB%B6/Ultrasound_display/LobotSerialServoControl.h)。原 OpenMV 协议存于 archive/protocol_openmv.md，不用于本版。

