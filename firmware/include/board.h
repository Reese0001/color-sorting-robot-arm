#ifndef BOARD_H
#define BOARD_H
#include <stdint.h>
enum { PORT_DEBUG = 0, PORT_BUS = 1 };
void Board_Init(void);
uint32_t Board_Millis(void);
int Board_Read(unsigned port, uint8_t *byte); /* -1 means stream lost: resync */
int Board_Write(unsigned port, const uint8_t *data, unsigned length);
void Board_Print(const char *text);
int Board_PWM(uint16_t pan_us, uint16_t tilt_us);
void Board_PWMOff(void);
extern volatile uint32_t g_uart_errors[3];
#endif
