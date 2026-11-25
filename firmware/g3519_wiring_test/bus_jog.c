#include "diag.h"
#include "text.h"
#include "ti_msp_dl_config.h"
#include <stdbool.h>
#include <string.h>

enum { POS_READ = 28, MOVE = 1, STOP = 12, MOVE_MS = 400, SETTLE_MS = 650 };
enum { LINE = 22, READ_MS = 100, RX_RING = 128 };
enum { RX_ERROR_BITS = UART_RXDATA_FRMERR_MASK | UART_RXDATA_PARERR_MASK |
                       UART_RXDATA_BRKERR_MASK | UART_RXDATA_OVRERR_MASK | UART_RXDATA_NERR_MASK };
typedef enum { UNTESTED, VALID, SILENT, ECHO, BAD_RX, TX_FAIL, POS_LIMIT, STOPPED } Reply;
static const char *const reply_name[] = {
    "WAIT", "POS", "NO RX", "ECHO ONLY", "BAD RX", "TX TIMEOUT", "LIMIT", "CANCELLED"
};
static const char *const joint[] = {"", "MID", "WRIST", "CLAW"};
static struct { Reply reply; int pos; } servo[4];
static uint32_t good_frames, outside_bytes, last_reply_ms, last_reply_id;
static volatile uint32_t ticks;
uint32_t millis(void) { return ticks; }
void SysTick_Handler(void) { ++ticks; }

/* IRQ owns head, the foreground owns tail. Keep raw UART error bits. */
static uint16_t rx_ring[RX_RING];
static volatile unsigned rx_head, rx_tail;
static volatile uint32_t rx_bytes, rx_errors, rx_dropped;
static uint8_t last_raw[8];
static unsigned raw_used;
void BUS_INST_IRQHandler(void)
{
    (void)DL_UART_Main_getPendingInterrupt(BUS_INST);
    while (!DL_UART_Main_isRXFIFOEmpty(BUS_INST)) {
        uint16_t sample = (uint16_t)BUS_INST->RXDATA;
        ++rx_bytes;
        if (sample & RX_ERROR_BITS) ++rx_errors;
        unsigned next = (rx_head + 1) % RX_RING;
        if (next == rx_tail) { ++rx_dropped; continue; }
        rx_ring[rx_head] = sample;
        __DMB();
        rx_head = next;
    }
}

static int pop_sample(void)
{
    if (rx_tail == rx_head) return -1;
    __DMB();
    int sample = rx_ring[rx_tail];
    __DMB();
    rx_tail = (rx_tail + 1) % RX_RING;
    memmove(last_raw, last_raw+1, sizeof last_raw-1);
    last_raw[sizeof last_raw-1] = (uint8_t)sample;
    if (raw_used < sizeof last_raw) ++raw_used;
    return sample;
}

static void drain_outside(void)
{
    for (unsigned n = 0; n < RX_RING && pop_sample() >= 0; ++n) ++outside_bytes;
}

static unsigned keys_down(void);
static unsigned pressed_id(unsigned keys, uint32_t now);
static unsigned queued_key;

static bool packet(unsigned id, unsigned cmd, const uint8_t *args, unsigned n)
{
    uint8_t bytes[10] = {0x55, 0x55, id, n+3, cmd};
    unsigned sum = id + n + 3 + cmd;
    for (unsigned i = 0; i < n; ++i) { bytes[5+i] = args[i]; sum += args[i]; }
    bytes[5+n] = (uint8_t)~sum;
    uint32_t start = millis();
    unsigned sent = 0;
    do {
        if (sent < n+6)
            sent += DL_UART_Main_fillTXFIFO(BUS_INST, bytes+sent, n+6-sent);
        if (sent == n+6) {
            /* Listen as the query leaves the FIFO, including any local echo. */
            if (cmd == POS_READ) return true;
            if (DL_UART_Main_isTXFIFOEmpty(BUS_INST) && !DL_UART_Main_isBusy(BUS_INST))
                return true;
        }
    } while (millis()-start < 5);
    return false;
}

/* A request echo has LEN=3. Only a distinct LEN=5 position reply with a
 * matching ID and checksum is a position reference for this button press. */
static Reply read_position(unsigned id, bool background)
{
    drain_outside();
    uint32_t start = millis(), before_drops = rx_dropped;
    if (!packet(id, POS_READ, NULL, 0)) return TX_FAIL;
    uint8_t window[8] = {0};
    uint8_t query[] = {0x55, 0x55, id, 3, POS_READ, (uint8_t)~(id+3+POS_READ)};
    unsigned count = 0, clean = 0;
    while (millis()-start < READ_MS) {
        unsigned keys = keys_down();
        if (keys & 8) {
            queued_key = 0;
            if (!background) return STOPPED;
        }
        unsigned press = pressed_id(keys, millis());
        if (background && press && !queued_key) queued_key = press;
        int sample = pop_sample();
        if (sample < 0) continue;
        ++count;
        if (sample & RX_ERROR_BITS) { clean = 0; continue; }
        ++clean;
        memmove(window, window+1, 7);
        window[7] = (uint8_t)sample;
        if (clean < 8 || window[0] != 0x55 || window[1] != 0x55 ||
            window[2] != id || window[3] != 5 || window[4] != POS_READ) continue;
        unsigned sum = id + 5 + POS_READ + window[5] + window[6] + window[7];
        if ((sum & 255) == 255 && before_drops == rx_dropped) {
            int pos = (int16_t)(window[5] | (window[6] << 8));
            servo[id].pos = pos;
            ++good_frames;
            last_reply_ms = millis()-start;
            last_reply_id = id;
            return pos < 0 || pos > 1000 ? POS_LIMIT : VALID;
        }
    }
    if (!count) return SILENT;
    return count == sizeof query && clean == count &&
        !memcmp(window+2, query, sizeof query) ? ECHO : BAD_RX;
}

static Reply probe(unsigned id, bool background)
{
    servo[id].reply = read_position(id, background);
    return servo[id].reply;
}

static bool move_to(unsigned id, int target)
{
    uint8_t args[] = {(uint8_t)target, (uint8_t)(target >> 8),
                      (uint8_t)MOVE_MS, (uint8_t)(MOVE_MS >> 8)};
    return packet(id, MOVE, args, sizeof args);
}

static char message[LINE] = "READY";
static void status(unsigned id, const char *text)
{
    number_line(message, LINE, "ID", id, " ");
    append(message+strlen(message), message+LINE-1, text);
    oled_line(10, message);
}

static unsigned keys_down(void)
{
    uint32_t a = DL_GPIO_readPins(KEYSA_PORT, KEYSA_K1_PIN | KEYSA_K4_PIN);
    uint32_t b = DL_GPIO_readPins(KEYSB_PORT, KEYSB_K2_PIN | KEYSB_K3_PIN);
    unsigned keys = 0;
    if (!(a & KEYSA_K1_PIN)) keys |= 1;
    if (!(b & KEYSB_K2_PIN)) keys |= 2;
    if (!(b & KEYSB_K3_PIN)) keys |= 4;
    if (!(a & KEYSA_K4_PIN)) keys |= 8;
    return keys;
}

static unsigned pressed_id(unsigned keys, uint32_t now)
{
    static unsigned previous;
    static uint32_t changed;
    static bool released;
    if (keys != previous) { previous = keys; changed = now; }
    if (now-changed < 30) return 0;
    if (!keys) { released = true; return 0; }
    if (!released) return 0;
    released = false;
    switch (keys) {
    case 1: return 1;
    case 2: return 2;
    case 4: return 3;
    default: return 0;
    }
}

static unsigned active;
static int origin, target;
static bool returning;
static uint32_t last_move;
static int distance(int a, int b) { return a > b ? a-b : b-a; }
static void cancel(const char *reason)
{
    bool sent = packet(active, STOP, NULL, 0);
    status(active, sent ? reason : "STOP TX FAIL");
    active = 0;
}

static void start_jog(unsigned id)
{
    Reply r = probe(id, false);
    if (r != VALID) { status(id, reply_name[r]); return; }
    if (keys_down() & 8) { status(id, "CANCELLED"); return; }
    origin = servo[id].pos;
    int step = id == 3 ? 8 : 12;
    target = origin <= 500 ? origin+step : origin-step;
    active = id;
    returning = false;
    if (!move_to(id, target)) { cancel("TX FAIL"); return; }
    last_move = millis();
    status(id, "JOG TX");
}

static void finish_step(void)
{
    Reply r = probe(active, false);
    if (r == STOPPED) { cancel("STOP TX"); return; }
    if (r != VALID) { cancel(r == POS_LIMIT ? "POS LIMIT" : "FEEDBACK LOST"); return; }
    if (keys_down() & 8) { cancel("STOP TX"); return; }
    int pos = servo[active].pos;
    if (returning) {
        if (distance(pos, origin) > 3) { cancel("RETURN UNVERIFIED"); return; }
        status(active, "BACK OK");
        active = 0;
        return;
    }
    /* Only reverse a verified small jog. A displaced, blocked or wrong
     * joint must not be commanded back to an old absolute coordinate. */
    if (distance(pos, target) > 3) { cancel("JOG UNVERIFIED"); return; }
    if (!move_to(active, origin)) { cancel("TX FAIL"); return; }
    returning = true;
    last_move = millis();
    status(active, "BACK TX");
}

static void display(void)
{
    char line[LINE];
    for (unsigned id = 1; id <= 3; ++id) {
        number_line(line, LINE, "ID", id, " ");
        char *end = line+LINE-1;
        char *p = append(line+strlen(line), end, joint[id]);
        p = append(p, end, " ");
        p = append(p, end, reply_name[servo[id].reply]);
        if (servo[id].reply == VALID || servo[id].reply == POS_LIMIT) {
            int pos = servo[id].pos;
            p = append(p, end, pos < 0 ? " -" : " ");
            decimal(p, end, pos < 0 ? -pos : pos);
        }
        oled_line(2+id, line);
    }
    number_line(line, LINE, "BUS RX ", rx_bytes, " BYTES");
    oled_line(7, line);
    number_line(line, LINE, "GOOD REPLIES ", good_frames, "");
    oled_line(8, line);
    number_line(line, LINE, "OUT ", outside_bytes, " ERR ");
    decimal(line+strlen(line), line+LINE-1, rx_errors+rx_dropped);
    oled_line(9, line);
    if (last_reply_id) {
        number_line(line, LINE, "LAST ID", last_reply_id, " ");
        char *end = line+LINE-1;
        char *p = decimal(line+strlen(line), end, last_reply_ms);
        append(p, end, " MS");
        oled_line(11, line);
    }
    static const char digits[] = "0123456789ABCDEF";
    char *p = append(line, line+LINE-1, "RAW ");
    for (unsigned i = sizeof last_raw-raw_used; i < sizeof last_raw; ++i) {
        *p++ = digits[last_raw[i] >> 4];
        *p++ = digits[last_raw[i] & 15];
    }
    *p = 0;
    oled_line(15, raw_used ? line : "RAW --");
}

int main(void)
{
    SYSCFG_DL_init();
    SysTick_Config(CPUCLK_FREQ/1000);
    NVIC_EnableIRQ(BUS_INST_INT_IRQN);
    oled_init();
    oled_line(0, "G3519 BUS JOG V2");
    oled_line(1, "A13 TX A14 RX 115200");
    oled_line(10, message);
    oled_line(12, "K1 MID   K2 WRIST");
    oled_line(13, "K3 CLAW  K4 STOP");
    uint32_t scan = 0, redraw = 0;
    unsigned next = 1;
    for (;;) {
        uint32_t now = millis();
        unsigned keys = keys_down();
        unsigned press = pressed_id(keys, now);
        unsigned id = queued_key ? queued_key : press;
        queued_key = 0;
        if (keys & 8) id = 0;
        if (active && (keys & 8)) cancel("STOP TX");
        else if (active && now-last_move >= SETTLE_MS) finish_step();
        else if (!active && id) start_jog(id);
        else if (!active && now-scan >= 140) {
            scan = now;
            probe(next, true);
            next = next%3 + 1;
        }
        drain_outside();
        if (now-redraw >= 200) { redraw = now; display(); }
    }
}
