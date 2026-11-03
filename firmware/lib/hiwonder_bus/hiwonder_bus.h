#ifndef HIWONDER_BUS_H
#define HIWONDER_BUS_H
#include <stdint.h>
#define BUS_PACKET_MAX 16
#define BUS_MOVE_TIME_WRITE 1
#define BUS_MOVE_STOP 12
#define BUS_POS_READ 28
typedef struct {
    uint8_t data[BUS_PACKET_MAX], used;
    uint32_t last_byte_ms, good, bad;
    uint8_t id, command, parameter_count;
    uint8_t parameters[BUS_PACKET_MAX - 6];
} BusParser;
uint8_t Bus_Build(uint8_t *out, uint8_t id, uint8_t command, const uint8_t *parameters, uint8_t count);
uint8_t Bus_Move(uint8_t *out, uint8_t id, uint16_t position, uint16_t time_ms);
int Bus_Feed(BusParser *parser, uint8_t byte, uint32_t now_ms);
#endif
