/* MSPM0G3507 DriverLib setup. Hand-maintained; no SysConfig overwrite needed. */
#include "board.h"
#include "app_config.h"
#include "k230_protocol.h"
#include <ti/driverlib/dl_uart_main.h>
#include <ti/driverlib/dl_gpio.h>
#include <ti/driverlib/dl_timera.h>
#include <ti/driverlib/m0p/dl_sysctl.h>
#include <string.h>

typedef struct {
    volatile uint8_t bytes[128];
    volatile uint8_t head, tail;
    volatile uint32_t losses;
    uint32_t seen;
} RxQueue;
static RxQueue queues[2];
static volatile uint32_t ticks;
volatile uint32_t g_uart_errors[3];
static uint8_t pwm_running;

static void power_wait(void)
{
    volatile unsigned i;
    for (i = 0; i < 128; ++i) __NOP(); /* more than 16 bus clocks */
}

static void uart_init(UART_Regs *u)
{
    const DL_UART_ClockConfig clock = {DL_UART_CLOCK_BUSCLK, DL_UART_CLOCK_DIVIDE_RATIO_1};
    const DL_UART_Config config = {DL_UART_MODE_NORMAL, DL_UART_DIRECTION_TX_RX,
        DL_UART_FLOW_CONTROL_NONE, DL_UART_PARITY_NONE, DL_UART_WORD_LENGTH_8_BITS,
        DL_UART_STOP_BITS_ONE};
    DL_UART_setClockConfig(u, &clock);
    DL_UART_init(u, &config);
    DL_UART_setOversampling(u, DL_UART_OVERSAMPLING_RATE_16X);
    /* 32MHz/(16*115200) = 17 + 23/64. Actual baud about 115212. */
    DL_UART_setBaudRateDivisor(u, 17, 23);
    DL_UART_enableFIFOs(u);
    DL_UART_setRXFIFOThreshold(u, DL_UART_RX_FIFO_LEVEL_ONE_ENTRY);
    DL_UART_enableInterrupt(u, DL_UART_INTERRUPT_RX | DL_UART_INTERRUPT_OVERRUN_ERROR |
        DL_UART_INTERRUPT_FRAMING_ERROR | DL_UART_INTERRUPT_PARITY_ERROR | DL_UART_INTERRUPT_BREAK_ERROR);
    DL_UART_enable(u);
}

void Board_PWMOff(void)
{
    /* Force the pins low even when the counter stopped in the high phase. */
    DL_GPIO_clearPins(GPIOA, DL_GPIO_PIN_15 | DL_GPIO_PIN_16);
    DL_GPIO_initDigitalOutput(IOMUX_PINCM37);
    DL_GPIO_initDigitalOutput(IOMUX_PINCM38);
    DL_GPIO_enableOutput(GPIOA, DL_GPIO_PIN_15 | DL_GPIO_PIN_16);
    DL_Timer_stopCounter(TIMA1);
    pwm_running = 0;
}

int Board_PWM(uint16_t pan, uint16_t tilt)
{
    if (!MOTION_OUTPUT_ENABLE || pan < PWM_MIN_US || pan > PWM_MAX_US ||
        tilt < PWM_MIN_US || tilt > PWM_MAX_US) return 0;
    if (!pwm_running) {
        DL_Timer_setCaptCompUpdateMethod(TIMA1, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMER_CC_0_INDEX);
        DL_Timer_setCaptCompUpdateMethod(TIMA1, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMER_CC_1_INDEX);
    }
    /* Down-counting edge-aligned PWM: high at LOAD, low at compare. */
    DL_Timer_setCaptureCompareValue(TIMA1, PWM_PERIOD_US - 1U - pan, DL_TIMER_CC_0_INDEX);
    DL_Timer_setCaptureCompareValue(TIMA1, PWM_PERIOD_US - 1U - tilt, DL_TIMER_CC_1_INDEX);
    if (!pwm_running) {
        DL_Timer_setCaptCompUpdateMethod(TIMA1, DL_TIMER_CC_UPDATE_METHOD_ZERO_EVT, DL_TIMER_CC_0_INDEX);
        DL_Timer_setCaptCompUpdateMethod(TIMA1, DL_TIMER_CC_UPDATE_METHOD_ZERO_EVT, DL_TIMER_CC_1_INDEX);
        DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM37, IOMUX_PINCM37_PF_TIMA1_CCP0);
        DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM38, IOMUX_PINCM38_PF_TIMA1_CCP1);
        DL_Timer_setTimerCount(TIMA1, PWM_PERIOD_US - 1U);
        DL_Timer_startCounter(TIMA1); pwm_running = 1;
    }
    return 1;
}

void Board_Init(void)
{
    const DL_Timer_ClockConfig timer_clock = {DL_TIMER_CLOCK_BUSCLK, DL_TIMER_CLOCK_DIVIDE_1, 31};
    const DL_Timer_PWMConfig pwm = {PWM_PERIOD_US, DL_TIMER_PWM_MODE_EDGE_ALIGN, false, DL_TIMER_STOP};
    /* Reset defaults use SYSOSC; avoid any dependency on an external crystal. */
    DL_SYSCTL_setMCLKDivider(DL_SYSCTL_MCLK_DIVIDER_DISABLE);
    DL_SYSCTL_setSYSOSCFreq(DL_SYSCTL_SYSOSC_FREQ_BASE);
    DL_SYSCTL_setULPCLKDivider(DL_SYSCTL_ULPCLK_DIV_1);
    DL_GPIO_reset(GPIOA); DL_GPIO_enablePower(GPIOA);
    DL_UART_reset(UART0); DL_UART_reset(UART1); DL_UART_reset(UART2);
    DL_UART_enablePower(UART0); DL_UART_enablePower(UART1); DL_UART_enablePower(UART2);
    DL_Timer_reset(TIMA1); DL_Timer_enablePower(TIMA1); power_wait();
    Board_PWMOff();
    /* Debug UART0 PA10/11; K230 UART1 PA17/18; bus bridge UART2 PA21/22. */
    DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM21, IOMUX_PINCM21_PF_UART0_TX);
    DL_GPIO_initPeripheralInputFunction(IOMUX_PINCM22, IOMUX_PINCM22_PF_UART0_RX);
    DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM39, IOMUX_PINCM39_PF_UART1_TX);
    DL_GPIO_initPeripheralInputFunction(IOMUX_PINCM40, IOMUX_PINCM40_PF_UART1_RX);
    DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM46, IOMUX_PINCM46_PF_UART2_TX);
    DL_GPIO_initPeripheralInputFunction(IOMUX_PINCM47, IOMUX_PINCM47_PF_UART2_RX);
    uart_init(UART0); uart_init(UART1); uart_init(UART2);
    DL_Timer_setClockConfig(TIMA1, &timer_clock);
    DL_Timer_initPWMMode(TIMA1, &pwm);
    DL_Timer_setCCPDirection(TIMA1, DL_TIMER_CC0_OUTPUT | DL_TIMER_CC1_OUTPUT);
    DL_Timer_enableClock(TIMA1);
    NVIC_SetPriority(UART1_INT_IRQn, 0);
    NVIC_SetPriority(UART0_INT_IRQn, 1); NVIC_SetPriority(UART2_INT_IRQn, 1);
    NVIC_EnableIRQ(UART0_INT_IRQn); NVIC_EnableIRQ(UART1_INT_IRQn); NVIC_EnableIRQ(UART2_INT_IRQn);
    SysTick_Config(CPU_HZ / 1000U);
}
uint32_t Board_Millis(void) { return ticks; }
void SysTick_Handler(void) { ++ticks; }

static void queue_put(RxQueue *q, uint8_t b)
{
    uint8_t next = (uint8_t)((q->head + 1U) & 127U);
    if (next == q->tail) { ++q->losses; return; }
    q->bytes[q->head] = b; q->head = next;
}
static void uart_rx(UART_Regs *u, unsigned which)
{
    uint32_t flags = DL_UART_getRawInterruptStatus(u, DL_UART_INTERRUPT_OVERRUN_ERROR |
        DL_UART_INTERRUPT_FRAMING_ERROR | DL_UART_INTERRUPT_BREAK_ERROR | DL_UART_INTERRUPT_PARITY_ERROR);
    DL_UART_clearInterruptStatus(u, 0xffffffffU);
    if (flags) {
        ++g_uart_errors[which];
        if (which == 1) K230_RxError(); else ++queues[which == 0 ? 0 : 1].losses;
    }
    while (!DL_UART_isRXFIFOEmpty(u)) {
        uint32_t data = u->RXDATA; /* Read once: RXDATA also contains error flags. */
        if (data & (DL_UART_ERROR_OVERRUN | DL_UART_ERROR_BREAK | DL_UART_ERROR_PARITY | DL_UART_ERROR_FRAMING)) {
            if (which == 1) K230_RxError(); else ++queues[which == 0 ? 0 : 1].losses;
        } else if (which == 1) K230_IRQHandler((uint8_t)data);
        else queue_put(&queues[which == 0 ? 0 : 1], (uint8_t)data);
    }
}
void UART0_IRQHandler(void) { uart_rx(UART0, 0); }
void UART1_IRQHandler(void) { uart_rx(UART1, 1); }
void UART2_IRQHandler(void) { uart_rx(UART2, 2); }
int Board_Read(unsigned port, uint8_t *b)
{
    RxQueue *q;
    if (port > PORT_BUS || !b) return 0;
    q = &queues[port];
    if (q->losses != q->seen) { uint32_t seen = q->losses; q->tail = q->head; q->seen = seen; return -1; }
    if (q->tail == q->head) return 0;
    *b = q->bytes[q->tail]; q->tail = (uint8_t)((q->tail + 1U) & 127U); return 1;
}
int Board_Write(unsigned port, const uint8_t *data, unsigned length)
{
    UART_Regs *u = port == PORT_DEBUG ? UART0 : UART2;
    uint32_t start = ticks;
    unsigned i;
    if (port > PORT_BUS || !data || (port == PORT_BUS && !BUS_PROTOCOL_CONFIRMED)) return 0;
    for (i = 0; i < length; ++i) {
        while (DL_UART_isTXFIFOFull(u)) if ((uint32_t)(ticks - start) >= 25U) return 0;
        DL_UART_transmitData(u, data[i]);
    }
    return 1;
}
void Board_Print(const char *s) { (void)Board_Write(PORT_DEBUG, (const uint8_t *)s, strlen(s)); }
