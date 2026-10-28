# STM32 侧协议模块 —— 集成说明

把 K230 发来的三色全景帧解析成结构体，并给出「该夹哪一块」的结论。
不依赖 `printf`、不依赖浮点、不用动态内存，只用 `string.h`。

## 文件

| 文件 | 说明 |
| --- | --- |
| `k230_protocol.h` | 数据结构 + API 声明 + 可调参数 |
| `k230_protocol.c` | 拼帧状态机 + XOR 校验 + 抓取决策 |

## 一、加进 Keil 工程

1. 把两个文件复制到工程目录（建议 `Hardware/k230/`）。
2. Keil 里右键 `Target` → **Add Group**，命名 `k230`。
3. 右键该组 → **Add Existing Files** → 选中 `k230_protocol.c`。
4. **Options for Target → C/C++ → Include Paths** 里加上 `k230` 目录。

不需要改任何编译选项，C99 和 C89 都能过。

## 二、USART2 初始化

K230 只发不收，所以 STM32 侧只需要 RX。用 USART2 是因为 PA2/PA3 不占用定时器通道
（PA9 是 TIM1_CH2，如果 HTD-35H 总线舵机用了 PA9 就不能选 USART1）。

```c
#include "stm32f10x.h"
#include "k230_protocol.h"

void K230_UART_Init(void)
{
    GPIO_InitTypeDef  GPIO_InitStructure;
    USART_InitTypeDef USART_InitStructure;
    NVIC_InitTypeDef  NVIC_InitStructure;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2, ENABLE);

    /* PA2 = USART2_TX（本版可不接），PA3 = USART2_RX */
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_2;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_3;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;   /* RX 必须浮空或上拉 */
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    USART_InitStructure.USART_BaudRate            = 115200;
    USART_InitStructure.USART_WordLength          = USART_WordLength_8b;
    USART_InitStructure.USART_StopBits            = USART_StopBits_1;
    USART_InitStructure.USART_Parity              = USART_Parity_No;
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStructure.USART_Mode                = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART2, &USART_InitStructure);

    /* 只开 RXNE 中断。错误中断（ORE/NE/FE/PE）不开，
     * 靠下面 K230_Poll 里读 SR 清标志，避免错误中断把 CPU 拖死。 */
    USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);

    NVIC_InitStructure.NVIC_IRQChannel                   = USART2_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 1;
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&NVIC_InitStructure);

    USART_Cmd(USART2, ENABLE);
}
```

**优先级建议**：不要设成最高。K230 每 100 ms 才发一帧，不着急；
设太高会打断舵机 PWM 更新和定时器节拍。

## 三、中断服务函数

```c
void USART2_IRQHandler(void)
{
    if (USART_GetITStatus(USART2, USART_IT_RXNE) != RESET) {
        uint8_t byte = (uint8_t)USART_ReceiveData(USART2);
        K230_IRQHandler(byte);          /* 只入队，不解析 */
    }
    /* 溢出/噪声错误：读一次 DR 清掉，不做处理 */
    if (USART_GetFlagStatus(USART2, USART_FLAG_ORE) != RESET) {
        (void)USART_ReceiveData(USART2);
    }
}
```

`K230_IRQHandler()` 里只做一件事：把字节塞进环形缓冲。
执行时间几十个周期，不解析、不校验、不调 `malloc`。

## 四、主循环

```c
#include "k230_protocol.h"

int main(void)
{
    /* ... 你的时钟、舵机、延时初始化 ... */
    K230_Init();
    K230_UART_Init();

    while (1) {
        uint32_t now = millis();        /* 你自己的毫秒时基 */

        K230_Poll(now);                 /* 解析缓冲，越快调用越好 */

        int8_t target = K230_PickTarget(now);
        if (target >= 0) {
            /* target = 0/1/2，对应红/绿/蓝 */
            /* 交给抓取状态机 */
        }

        delay_ms(5);                    /* 5~10ms 一次足够 */
    }
}
```

### 时基从哪来

用 SysTick 做一个毫秒计数器就行，别在 `K230_Poll` 里调 `delay`：

```c
static volatile uint32_t g_ms = 0;

void SysTick_Handler(void)
{
    g_ms++;
}

uint32_t millis(void)
{
    return g_ms;
}
```

`g_ms` 是 `volatile`，主循环里读一次存到局部变量再传给 `K230_Poll` / `K230_PickTarget`，
保证两个函数看到的是同一个时刻。

## 五、怎么读数据

```c
if (K230_Online(now)) {
    K230_Slot *r = &g_vision.slot[K230_SLOT_RED];
    if (r->valid) {
        /* r->cx, r->cy 是 640x480 画面里的像素坐标，左上角为原点 */
        /* r->px 是像素数，可粗略当"占屏面积"，越大越近 */
    }
}
```

`g_vision.seq` 可以检测丢帧：连续两帧 `seq` 差大于 1 说明中间丢了。

## 六、联调自检

第一次跑通时，用这两个计数器判断链路是否正常：

```c
/* 放在主循环里，配合 Keil 的 Watch 窗口或串口打印 */
g_vision.frames_ok    /* 应该在稳定增长，约 10 次/秒 */
g_vision.frames_bad   /* 应该一直是 0 或极少 */
```

| 现象 | 可能原因 |
| --- | --- |
| `frames_ok` 一直是 0 | 接线错（TX/RX 反了）、波特率不对、没共地、K230 的 `UART_ENABLED` 还是 `False` |
| `frames_ok` 涨但 `frames_bad` 也涨 | 波特率有偏差、线太长受干扰、校验算法不一致 |
| 偶尔涨一下就停 | 环形缓冲溢出（`K230_RB_SIZE` 调大）或主循环 `K230_Poll` 调用太慢 |
| `frames_ok` 正常但 `K230_PickTarget` 总返回 -1 | `K230_Online()` 用的是不同的 `now_ms`，或者 K230 那边三色都是 `-1`（没稳定目标） |

## 七、接抓取状态机

`K230_PickTarget()` 只回答「现在该夹哪一块」，不管机械臂怎么动。
状态机建议这样接：

```text
IDLE ──(PickTarget>=0 且连续 N 次一致)──→ ALIGNING
ALIGNING ──(对准完成)──→ GRASPING
GRASPING ──(夹爪闭合)──→ LIFTING
LIFTING ──(抬升到位)──→ PLACING
PLACING ──(放置完成)──→ IDLE
```

两个必须遵守的约束：

1. **只有 IDLE 状态才读 `K230_PickTarget()`**。机械臂运动期间摄像头跟着动，
   画面里的像素坐标毫无意义，此时读到的目标必须丢弃。
2. **进 ALIGNING 前把目标锁死**。不要每帧重新决策 —— 木块在视野里抖一下就可能换目标，
   机械臂会左右摇摆。锁定后只有在 `K230_Online()` 变 0 或超时才放弃。

`K230_PickTarget()` 内部的 5% 容差（`K230_TIE_RATIO`）就是为了压住这种抖动，
但它只能处理「两个木块一样大」的情况，「同一块木块像素数在阈值附近波动」还得靠状态机锁目标。

## 八、可调参数

都在 `k230_protocol.h` 顶部：

| 宏 | 默认 | 说明 |
| --- | --- | --- |
| `K230_FRAME_MAX` | 80 | 单帧最大字节数。典型帧 40~55 字节，不够就调大 |
| `K230_RB_SIZE` | 256 | 环形缓冲。主循环卡顿超过 250 ms 才可能溢出 |
| `K230_TIMEOUT_MS` | 500 | 超过这么久没收到合法帧就判离线。K230 每 100 ms 发一帧，留 5 倍余量 |
| `K230_TIE_RATIO` | 95 | 并列容差百分比。调高更倾向选最大的，调低更倾向红绿蓝顺序 |

## 九、单元测试

工作区里有一套离线单元测试（34 项，用 PC 上的 gcc 跑，不需要板子），
覆盖拼帧、校验、越界、9 种决策组合、超时边界、`seq=65535` 和 `px=307200` 边界值。
改完 `k230_protocol.c` 后建议重跑一遍再提交。

```bash
gcc -std=c99 -Wall -Wextra -o test test_main.c k230_protocol.c && ./test
```

测试用的假头文件 `stm32f10x.h` 和 `test_main.c` 在 WorkBuddy 工作区 `c_test/` 目录，
不放进 GitHub 仓库（避免和真实工程的头文件冲突）。
