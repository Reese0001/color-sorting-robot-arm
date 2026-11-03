#include "hiwonder_bus.h"
#include <string.h>
uint8_t Bus_Build(uint8_t *out, uint8_t id, uint8_t cmd, const uint8_t *p, uint8_t n)
{
    unsigned i;
    uint8_t sum;
    if (!out || id > 253 || n > BUS_PACKET_MAX - 6 || (n && !p)) return 0;
    out[0] = out[1] = 0x55; out[2] = id; out[3] = n + 3; out[4] = cmd;
    sum = (uint8_t)(id + n + 3 + cmd);
    for (i = 0; i < n; ++i) { out[5+i] = p[i]; sum += p[i]; }
    out[5+n] = (uint8_t)~sum;
    return n + 6;
}
uint8_t Bus_Move(uint8_t *out, uint8_t id, uint16_t position, uint16_t time_ms)
{
    uint8_t p[4];
    if (position > 1000 || time_ms > 30000) return 0;
    p[0] = (uint8_t)position; p[1] = (uint8_t)(position >> 8);
    p[2] = (uint8_t)time_ms; p[3] = (uint8_t)(time_ms >> 8);
    return Bus_Build(out, id, BUS_MOVE_TIME_WRITE, p, 4);
}
int Bus_Feed(BusParser *s, uint8_t b, uint32_t now)
{
    unsigned i;
    uint8_t sum = 0, total;
    if (s->used && (uint32_t)(now - s->last_byte_ms) > 20) { s->used = 0; ++s->bad; }
    s->last_byte_ms = now;
    if (s->used < 2) {
        if (b == 0x55) s->data[s->used++] = b;
        else s->used = 0;
        return 0;
    }
    s->data[s->used++] = b;
    if (s->used == 4 && (b < 3 || b > BUS_PACKET_MAX - 3)) { s->used = 0; ++s->bad; return 0; }
    if (s->used < 4) return 0;
    total = s->data[3] + 3;
    if (s->used < total) return 0;
    s->used = 0;
    for (i = 2; i < total; ++i) sum += s->data[i];
    if (sum != 0xff || s->data[2] > 253) { ++s->bad; return 0; }
    s->id = s->data[2]; s->command = s->data[4]; s->parameter_count = total - 6;
    memcpy(s->parameters, s->data + 5, s->parameter_count); ++s->good;
    return 1;
}
