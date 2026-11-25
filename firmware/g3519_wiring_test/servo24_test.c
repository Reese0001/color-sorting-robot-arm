#include "diag.h"
#include "ti_msp_dl_config.h"
#include <stdbool.h>
#include <stddef.h>

enum { DEBOUNCE_MS = 30, STEP_MS = 1000, TX_TIMEOUT_MS = 30, FRAME_BYTES = 6 };

/* A complete 6-byte frame takes 6.25 ms at 9600 8N1. The flag describes
 * the local transmitter only. J19 RX3 and GND provide no return path. */
static bool send_frame(const char *frame)
{
    const uint32_t start = millis();
    unsigned sent = 0;
    do {
        if (sent < FRAME_BYTES)
            sent += DL_UART_Main_fillTXFIFO(PTZ_INST, (const uint8_t *)frame + sent,
                                           FRAME_BYTES - sent);
        if (sent == FRAME_BYTES && DL_UART_Main_isTXFIFOEmpty(PTZ_INST) &&
            !DL_UART_Main_isBusy(PTZ_INST))
            return true;
    } while (millis() - start < TX_TIMEOUT_MS);
    return false;
}

/* NULL means that there is no new OLED log entry. */
const char *servo24_update(uint32_t now)
{
    static const char *const frames[2][2] = {{"$A090#", "$A095#"}, {"$B090#", "$B095#"}};
    static const char *const logs[2][2] = {{"S1 TX 090", "S1 TX 095"}, {"S2 TX 090", "S2 TX 095"}};
    enum { IDLE = 3 };
    static unsigned step = IDLE, channel, last_keys;
    static uint32_t changed_at, sent_at;
    static bool armed, fault;
    if (fault) return NULL;

    unsigned keys = 0;
    if (!DL_GPIO_readPins(PAN_KEY_PORT, PAN_KEY_K1_PIN)) keys |= 1;
    if (!DL_GPIO_readPins(TILT_KEY_PORT, TILT_KEY_K2_PIN)) keys |= 2;
    if (keys != last_keys) {
        last_keys = keys;
        changed_at = now;
    }

    if (step == IDLE) {
        if (now - changed_at < DEBOUNCE_MS) return NULL;
        if (keys == 0) {
            armed = true;
            return NULL;
        }
        if (!armed) return NULL;
        armed = false;
        if (keys == 3) return NULL;
        channel = keys - 1;
        step = 0;
    }
    if (step != 0 && now - sent_at < STEP_MS) return NULL;

    unsigned offset = (step == 1);
    if (!send_frame(frames[channel][offset])) {
        /* The board parser can retain a partial frame. Stop until both boards
         * are restarted instead of appending another command to that frame. */
        fault = true;
        return "A08 TX TIMEOUT";
    }
    sent_at = millis();
    ++step;
    return logs[channel][offset];
}
