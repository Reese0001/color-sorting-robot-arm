#ifndef G3519_DIAG_H
#define G3519_DIAG_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t millis(void);
void oled_init(void);
void oled_line(unsigned row, const char *text);
void range_update(char *line, unsigned size);
const char *servo24_update(uint32_t now);
#ifdef __cplusplus
}
#endif
#endif
