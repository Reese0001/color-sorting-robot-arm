#include "diag.h"
#include "ti_msp_dl_config.h"
#include <string.h>

/* Uppercase 5x7 column glyphs. One SH1107 page holds one text line. */
static const char alphabet[] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-:/";
static const uint8_t glyph[][5] = {
    {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},{33,65,69,75,49},
    {24,20,18,127,16},{39,69,69,69,57},{60,74,73,73,48},{1,113,9,5,3},
    {54,73,73,73,54},{6,73,73,41,30},
    {126,9,9,9,126},{127,73,73,73,54},{62,65,65,65,34},{127,65,65,34,28},
    {127,73,73,73,65},{127,9,9,9,1},{62,65,73,73,122},{127,8,8,8,127},
    {0,65,127,65,0},{32,64,65,63,1},{127,8,20,34,65},{127,64,64,64,64},
    {127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},{127,9,9,9,6},
    {62,65,81,33,94},{127,9,25,41,70},{38,73,73,73,50},{1,1,127,1,1},
    {63,64,64,64,63},{31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},
    {7,8,112,8,7},{97,81,73,69,67},{8,8,8,8,8},{0,54,54,0,0},{32,16,8,4,2}
};

static void shift(uint8_t value)
{
    for (unsigned mask = 0x80; mask; mask >>= 1) {
        DL_GPIO_clearPins(OLED_PORT, OLED_CLK_PIN);
        if (value & mask) DL_GPIO_setPins(OLED_PORT, OLED_MOSI_PIN);
        else DL_GPIO_clearPins(OLED_PORT, OLED_MOSI_PIN);
        DL_GPIO_setPins(OLED_PORT, OLED_CLK_PIN);
    }
    DL_GPIO_clearPins(OLED_PORT, OLED_CLK_PIN);
}

void oled_line(unsigned row, const char *text)
{
    DL_GPIO_clearPins(OLED_PORT, OLED_CS_PIN | OLED_DC_PIN);
    shift(0xb0 | row);
    shift(0x10);
    shift(0x00);
    DL_GPIO_setPins(OLED_PORT, OLED_DC_PIN);
    unsigned x = 0;
    while (*text && x + 6 <= 128) {
        const char *g = strchr(alphabet, *text++);
        for (unsigned j = 0; j < 5; j++) shift(g ? glyph[g - alphabet][j] : 0);
        shift(0);
        x += 6;
    }
    while (x++ < 128) shift(0);
    DL_GPIO_setPins(OLED_PORT, OLED_CS_PIN);
}

void oled_init(void)
{
    /* RST starts low in SysConfig; allow both power and reset to settle. */
    delay_cycles(CPUCLK_FREQ / 10);
    DL_GPIO_setPins(OLED_PORT, OLED_RST_PIN);
    delay_cycles(CPUCLK_FREQ / 20);
    static const uint8_t init[] = {
        0xae, 0xdc,0, 0x81,0x70, 0x20, 0xa0, 0xc0, 0xa8,0x7f,
        0xd3,0, 0xd5,0x50, 0xad,0x8a, 0xd9,0x22, 0xdb,0x35, 0xa4, 0xa6
    };
    DL_GPIO_clearPins(OLED_PORT, OLED_CS_PIN | OLED_DC_PIN);
    for (unsigned i = 0; i < sizeof init; i++) shift(init[i]);
    DL_GPIO_setPins(OLED_PORT, OLED_CS_PIN);
    for (unsigned row = 0; row < 16; row++) oled_line(row, "");
    DL_GPIO_clearPins(OLED_PORT, OLED_CS_PIN | OLED_DC_PIN);
    shift(0xaf);
    DL_GPIO_setPins(OLED_PORT, OLED_CS_PIN);
}
