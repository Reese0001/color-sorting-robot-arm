#include "diag.h"
#include "ti_msp_dl_config.h"
#include "text.h"
#include <string.h>

enum { LINE = 22, HISTORY = 5, RING = 256 };
typedef struct {
    uint8_t data[RING];
    volatile unsigned head, tail;
    volatile uint32_t count, dropped;
} Receiver;
static Receiver camera, bus;
static volatile uint32_t ticks;
uint32_t millis(void) { return ticks; }
void SysTick_Handler(void) { ticks++; }

static void receive(UART_Regs *uart, Receiver *r)
{
    for (unsigned quota = 0; quota < 32 && !DL_UART_Main_isRXFIFOEmpty(uart); quota++) {
        uint8_t b = DL_UART_Main_receiveData(uart);
        unsigned next = (r->head + 1) % RING;
        r->count++;
        if (next == r->tail) { r->dropped++; continue; }
        r->data[r->head] = b;
        __DMB();
        r->head = next;
    }
}
void CAMERA_INST_IRQHandler(void) { receive(CAMERA_INST, &camera); }
void BUS_INST_IRQHandler(void) { receive(BUS_INST, &bus); }

static int pop(Receiver *r)
{
    if (r->tail == r->head) return -1;
    int b = r->data[r->tail];
    r->tail = (r->tail + 1) % RING;
    return b;
}
static bool transmit(UART_Regs *uart, const uint8_t *p, size_t n)
{
    uint32_t start = millis();
    for (size_t i = 0; i < n; i++) {
        while (DL_UART_Main_isTXFIFOFull(uart))
            if (millis() - start >= 8) return false;
        DL_UART_Main_transmitData(uart, p[i]);
    }
    return true;
}

static char history[HISTORY][LINE];
static void event(const char *text)
{
    memmove(history, history + 1, (HISTORY - 1) * LINE);
    char *row = history[HISTORY-1];
    number_line(row, LINE, "", millis()/1000 % 10000, "S ");
    append(row + strlen(row), row + LINE-1, text);
}

/* Only the position-read command (0x1C) is sent to the servo bus. */
static uint8_t pending, sequenceId, frame[8];
static unsigned frameUsed;
static uint32_t issued, positionTime[3];
static int position[3] = {-1,-1,-1};
static void poll_bus(uint32_t now)
{
    int b;
    while ((b = pop(&bus)) >= 0) {
        if (frameUsed < 2 && b != 0x55) { frameUsed = 0; continue; }
        if (frameUsed == 2 && b == 0x55) continue;
        frame[frameUsed++] = (uint8_t)b;
        if ((frameUsed == 3 && (!pending || frame[2] != pending)) ||
            (frameUsed == 4 && frame[3] != 5) ||
            (frameUsed == 5 && frame[4] != 0x1c)) frameUsed = 0;
        if (frameUsed != sizeof frame) continue;
        frameUsed = 0;
        unsigned sum = 0;
        for (unsigned i=2; i<8; i++) sum += frame[i];
        int pos = frame[5] | ((int)frame[6] << 8);
        if ((sum & 255) == 255 && pos <= 1000 && now - issued < 150) {
            unsigned index = pending - 1;
            position[index] = pos;
            positionTime[index] = now;
            pending = 0;
        }
    }
    if (now - issued < 160) return;
    issued = now;
    pending = sequenceId = sequenceId % 3 + 1;
    frameUsed = 0;
    uint8_t query[] = {0x55,0x55,pending,3,0x1c,(uint8_t)~(pending+3+0x1c)};
    if (!transmit(BUS_INST, query, sizeof query)) pending = 0;
}

static char expected[LINE];
static uint32_t challenge, challengeTime, ackTime, cameraTime;
static bool ackSeen, rxSeen;
static void poll_camera(uint32_t now)
{
    static char buffer[LINE];
    static unsigned length;
    static bool drop;
    int b;
    while ((b = pop(&camera)) >= 0) {
        cameraTime = now;
        rxSeen = true;
        if (b == '\r') continue;
        if (b == '\n') {
            buffer[length] = 0;
            if (length && !drop && strcmp(buffer, expected) == 0 && expected[0]) {
                ackTime = now;
                ackSeen = true;
                expected[0] = 0;
            }
            drop = false;
            length = 0;
        } else if (length < sizeof buffer - 1 && b >= 32 && b <= 126) {
            buffer[length++] = (char)b;
        } else drop = true;
    }
    if (now - challengeTime < 1000) return;
    challengeTime = now;
    char request[LINE];
    challenge++;
    number_line(request, sizeof request, "PING ", challenge, "\n");
    number_line(expected, sizeof expected, "PONG ", challenge, "");
    if (!transmit(CAMERA_INST, (const uint8_t *)request, strlen(request))) expected[0] = 0;
}

static void refresh(const char *rangeLine)
{
    static char previousRange[LINE];
    static int lastLink = -1;
    static bool lastServo[3];
    uint32_t now = millis();
    char line[LINE];
    number_line(line, LINE, "UP ", now/1000, " S");
    oled_line(1, line);
    oled_line(3, rangeLine);
    const char *rangeState = rangeLine;
    if (strstr(rangeLine, " MM")) rangeState = "TOF DATA OK";
    if (strcmp(rangeState, previousRange)) {
        append(previousRange, previousRange + LINE-1, rangeState);
        event(rangeState);
    }
    int link = (ackSeen && now - ackTime < 2500) ? 2 :
               (rxSeen && now - cameraTime < 2500) ? 1 : 0;
    const char *state[] = {"K230 WAIT", "K230 RX ONLY", "K230 LINK OK"};
    if (link != lastLink) { event(state[link]); lastLink = link; }
    oled_line(4, state[link]);
    number_line(line, LINE, "RX ", camera.count, " BYTES");
    oled_line(5, line);
    for (unsigned i = 0; i < 3; i++) {
        bool live = position[i] >= 0 && now - positionTime[i] < 1500;
        if (lastServo[i] != live) {
            number_line(line, LINE, "ID", i+1, live ? " ONLINE" : " LOST");
            event(line);
            lastServo[i] = live;
        }
        number_line(line, LINE, "ID", i+1, live ? " POS " : " NO REPLY");
        if (live) decimal(line + strlen(line), line + LINE-1, (unsigned)position[i]);
        oled_line(6+i, line);
    }
    for (unsigned i=0; i<HISTORY; i++) oled_line(11+i, history[i]);
}

int main(void)
{
    SYSCFG_DL_init();
    SysTick_Config(CPUCLK_FREQ/1000);
    NVIC_EnableIRQ(CAMERA_INST_INT_IRQN);
    NVIC_EnableIRQ(BUS_INST_INT_IRQN);
    oled_init();
#ifdef PAN_KEY_PORT
    oled_line(0, "G3519 A08 SERVO TEST");
    oled_line(2, "K1 S1 / K2 S2 / 9600");
    oled_line(9, "A08 WAIT KEY");
#else
    oled_line(0, "G3519 WIRING TEST");
    oled_line(2, "PWM OFF / READ ONLY");
#endif
    oled_line(10, "RECENT LOG");
    event("BOOT");
    char rangeLine[LINE] = "TOF PROBE";
    refresh(rangeLine);
    uint32_t scan = 0, display = 0, beat = 0, drops = 0;
    for (;;) {
        uint32_t now = millis();
#ifdef PAN_KEY_PORT
        const char *servoLog = servo24_update(now);
        if (servoLog) {
            oled_line(9, servoLog);
            event(servoLog);
        }
#endif
        poll_camera(now);
        poll_bus(now);
        if (now - scan >= 40) { scan = now; range_update(rangeLine, LINE); }
        if (now - display >= 200) {
            display = now;
            uint32_t lost = camera.dropped + bus.dropped;
            if (lost != drops) { event("UART RX DROP"); drops = lost; }
            refresh(rangeLine);
        }
        if (now - beat >= 500) {
            beat = now;
            DL_GPIO_togglePins(HEART_PORT, HEART_LED_PIN);
        }
    }
}
