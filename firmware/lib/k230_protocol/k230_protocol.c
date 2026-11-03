/* Portable receiver: ISR queues bytes; main context validates whole frames. */
#include "k230_protocol.h"
#include <string.h>
K230_Vision g_vision;
static volatile uint8_t rb[K230_RB_SIZE];
static volatile uint16_t head, tail;
static volatile uint32_t loss_count;
static uint32_t handled_loss;
static char line[K230_FRAME_MAX];
static uint8_t length, collecting, fresh;
static int hex(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
static int number(const char *s, int32_t min, int32_t max, int32_t *out)
{
    uint32_t n = 0;
    int negative = 0;
    if (*s == '-') { negative = 1; ++s; }
    if (!*s) return 0;
    while (*s) {
        if (*s < '0' || *s > '9' || n > 307200U) return 0;
        n = n * 10U + (uint32_t)(*s++ - '0');
    }
    if (n > 307200U) return 0;
    *out = negative ? -(int32_t)n : (int32_t)n;
    return *out >= min && *out <= max;
}
static int parse(char *s, uint8_t len, uint32_t now)
{
    char *star, *f[13], *p;
    int hi, lo;
    unsigned i, n;
    uint8_t sum = 0;
    int32_t v[3];
    K230_Slot slots[3];
    if (len && s[len - 1] == '\r') s[--len] = 0;
    star = strchr(s, '*');
    if (!star || star - s + 3 != len) return 0;
    hi = hex(star[1]); lo = hex(star[2]);
    if (hi < 0 || lo < 0) return 0;
    for (p = s; p < star; ++p) sum ^= (uint8_t)*p;
    if (sum != (uint8_t)((hi << 4) | lo)) return 0;
    *star = 0; p = s;
    for (n = 0; n < 13; ++n) {
        f[n] = p; p = strchr(p, ',');
        if (!p) { ++n; break; }
        *p++ = 0;
    }
    if (n != 13 || p || strcmp(f[0], "T")) return 0;
    if (!number(f[1], 0, 65535, &v[0]) || !number(f[2], 0, 180, &v[1]) ||
        !number(f[3], 0, 180, &v[2])) return 0;
    for (i = 0; i < 3; ++i) {
        int32_t x, y, pixels;
        if (!number(f[4+i*3], -1, 639, &x) || !number(f[5+i*3], -1, 479, &y) ||
            !number(f[6+i*3], 0, 307200, &pixels)) return 0;
        if (!((x == -1 && y == -1 && pixels == 0) || (x >= 0 && y >= 0 && pixels > 0))) return 0;
        slots[i].cx = (int16_t)x; slots[i].cy = (int16_t)y;
        slots[i].px = (uint32_t)pixels; slots[i].valid = pixels > 0;
    }
    memcpy(g_vision.slot, slots, sizeof(slots));
    g_vision.seq = (uint16_t)v[0]; g_vision.pan = (uint8_t)v[1]; g_vision.tilt = (uint8_t)v[2];
    g_vision.last_rx_ms = now; ++g_vision.frames_ok; fresh = 1;
    return 1;
}
void K230_Init(void)
{
    unsigned i;
    memset(&g_vision, 0, sizeof(g_vision));
    for (i = 0; i < 3; ++i) g_vision.slot[i].cx = g_vision.slot[i].cy = -1;
    head = tail = 0; loss_count = handled_loss = 0;
    length = collecting = fresh = 0;
}
void K230_RxError(void) { ++loss_count; }
void K230_IRQHandler(uint8_t byte)
{
    uint16_t next = (uint16_t)((head + 1U) % K230_RB_SIZE);
    if (next == tail) { K230_RxError(); return; }
    rb[head] = byte; head = next;
}
void K230_Poll(uint32_t now)
{
    if (fresh && (uint32_t)(now - g_vision.last_rx_ms) >= K230_TIMEOUT_MS) fresh = 0;
    while (head != tail || handled_loss != loss_count) {
        char c;
        if (handled_loss != loss_count) {
            uint32_t seen = loss_count;
            tail = head; length = collecting = fresh = 0;
            g_vision.rx_dropped += seen - handled_loss;
            handled_loss = seen; ++g_vision.frames_bad; continue;
        }
        c = (char)rb[tail]; tail = (uint16_t)((tail + 1U) % K230_RB_SIZE);
        if (c == '@') { length = 0; collecting = 1; }
        else if (collecting && c == '\n') {
            line[length] = 0;
            if (!parse(line, length, now)) ++g_vision.frames_bad;
            collecting = length = 0;
        } else if (collecting) {
            if (c == 0 || length >= K230_FRAME_MAX - 1) {
                collecting = length = 0; ++g_vision.frames_bad;
            } else line[length++] = c;
        }
    }
}
uint8_t K230_Online(uint32_t now)
{
    return (uint8_t)(fresh && (uint32_t)(now - g_vision.last_rx_ms) < K230_TIMEOUT_MS);
}
int8_t K230_PickTarget(uint32_t now)
{
    unsigned i;
    uint32_t max = 0;
    if (!K230_Online(now)) return -1;
    for (i = 0; i < 3; ++i) if (g_vision.slot[i].valid && g_vision.slot[i].px > max) max = g_vision.slot[i].px;
    for (i = 0; i < 3; ++i)
        if (g_vision.slot[i].valid && g_vision.slot[i].px * 100U >= max * K230_TIE_RATIO) return (int8_t)i;
    return -1;
}
const char *K230_ColorName(uint8_t i)
{
    static const char * const names[] = {"RED", "GREEN", "BLUE"};
    return i < 3 ? names[i] : "NONE";
}
