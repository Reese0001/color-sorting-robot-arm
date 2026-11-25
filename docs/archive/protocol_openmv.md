# OpenMV 与 STM32 通信协议

## 串口参数

- 波特率：115200
- 数据位：8
- 停止位：1
- 校验：无
- 行结束符：`\n`

## 消息

### 识别到方块

```text
BLOCK,<color>,<center_x>,<center_y>,<pixels>\n
```

示例：

```text
BLOCK,RED,81,62,2450
```

`color` 只能是 `RED`、`GREEN` 或 `BLUE`；坐标基于 160×120 的 QQVGA 图像。

### 未识别到方块

```text
NONE
```

## 抗误识别策略

STM32 只有在以下条件全部满足时才启动分拣：

1. 颜色是协议允许值；
2. 方块中心位于 `config.h` 定义的抓取窗口；
3. 连续 `REQUIRED_STABLE_FRAMES` 帧颜色一致；
4. 最后一帧未超过 `DETECTION_TIMEOUT_MS`。

## 调试建议

- 先用 USB-TTL 观察 OpenMV 输出，再连接 STM32。
- 若颜色串扰，优先固定白平衡和增益，再重新标定 LAB 阈值。
- 若中心坐标变化大，使用纯色哑光背景并避免镜面反光。
- UART 两端必须共地，且 OpenMV/STM32 信号电平均为 3.3 V。
