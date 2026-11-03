/* Bench + simulated workflow. No automatic hardware grasping is performed. */
#include "app_config.h"
#include "board.h"
#include "k230_protocol.h"
#include "hiwonder_bus.h"
#include "robot_console.h"
#include <stdio.h>
#include <string.h>

static BusParser bus;
static uint8_t armed, moved_mask, read_id;
static uint32_t lease_start, read_start;
static char command[64];
static unsigned command_used;
static uint8_t discard_line;
static RobotConsole robot;
static void robot_output(void *context, const char *text)
{
    (void)context;
    Board_Print(text);
}

static void status(void)
{
    char s[220];
    uint32_t now = Board_Millis();
    int8_t target = K230_PickTarget(now);
    snprintf(s, sizeof(s), "STATUS ms=%lu online=%u seq=%u target=%s ok=%lu bad=%lu drop=%lu motion=%u armed=%u bus=%u\r\n",
        (unsigned long)now, (unsigned)K230_Online(now), (unsigned)g_vision.seq,
        K230_ColorName((uint8_t)target), (unsigned long)g_vision.frames_ok,
        (unsigned long)g_vision.frames_bad, (unsigned long)g_vision.rx_dropped,
        MOTION_OUTPUT_ENABLE, (unsigned)armed, BUS_PROTOCOL_CONFIRMED);
    Board_Print(s);
    if (target >= 0) {
        const K230_Slot *p = &g_vision.slot[(unsigned)target];
        snprintf(s, sizeof(s), "TARGET x=%d y=%d pixels=%lu (image coordinates only)\r\n",
            (int)p->cx, (int)p->cy, (unsigned long)p->px);
        Board_Print(s);
    }
}
static int send_bus(uint8_t id, uint8_t cmd)
{
    uint8_t frame[BUS_PACKET_MAX];
    uint8_t n = Bus_Build(frame, id, cmd, 0, 0);
    return n && Board_Write(PORT_BUS, frame, n);
}
static void disarm(void)
{
    unsigned id;
    Board_PWMOff(); armed = 0;
    for (id = 1; id <= 4; ++id)
        if (moved_mask & (1U << (id - 1))) (void)send_bus((uint8_t)id, BUS_MOVE_STOP);
    moved_mask = 0;
    Board_Print("DISARMED: PWM off; stop requested for moved IDs; not a power cut\r\n");
}
/* Strict unsigned decimal arguments; reject overflow and trailing garbage. */
static int args(const char *p, unsigned *out, unsigned count)
{
    unsigned i;
    for (i = 0; i < count; ++i) {
        unsigned n = 0, digits = 0;
        while (*p == ' ') ++p;
        while (*p >= '0' && *p <= '9') {
            if (n > 3000) return 0;
            n = n * 10 + (unsigned)(*p++ - '0'); ++digits;
        }
        if (!digits || (*p && *p != ' ')) return 0;
        out[i] = n;
    }
    while (*p == ' ') ++p;
    return !*p;
}
static void execute(const char *s)
{
    unsigned a[3];
    uint8_t frame[BUS_PACKET_MAX], n;
    if (RobotConsole_IsCommand(s)) {
        if (armed) Board_Print("ERR DISARM manual hardware control before dry run commands\r\n");
        else (void)RobotConsole_Command(&robot, s, Board_Millis());
        return;
    }
    if (robot.flow.state != WF_IDLE && (!strcmp(s, "ARM") || !strncmp(s, "PWM ", 4) || !strncmp(s, "MOVE ", 5))) {
        Board_Print("ERR dry run not idle; STOP if active, then RESET before manual control\r\n"); return;
    }
    if (!strcmp(s, "HELP")) {
        Board_Print("HELP STATUS PING ARM DISARM | PWM us us | READ id | MOVE id pos ms\r\n");
        Board_Print("Default: motion=0 bus=0. ARM lease=10s. IDs=1..4 are provisional.\r\n");
        RobotConsole_Help(&robot);
    } else if (!strcmp(s, "STATUS")) status();
    else if (!strcmp(s, "PING")) Board_Print("PONG MSPM0G3507\r\n");
    else if (!strcmp(s, "DISARM")) {
        if (Workflow_Busy(&robot.flow)) (void)Workflow_Stop(&robot.flow);
        disarm();
    }
    else if (!strcmp(s, "ARM")) {
        if (!MOTION_OUTPUT_ENABLE) Board_Print("ERR motion disabled in app_config.h\r\n");
        else { armed = 1; lease_start = Board_Millis(); Board_Print("ARMED 10s; no movement yet\r\n"); }
    } else if (!strncmp(s, "PWM ", 4) && args(s + 4, a, 2)) {
        if (!armed) Board_Print("ERR not armed\r\n");
        else if (!Board_PWM((uint16_t)a[0], (uint16_t)a[1])) Board_Print("ERR PWM range/config\r\n");
        else { lease_start = Board_Millis(); Board_Print("OK PWM\r\n"); }
    } else if (!strncmp(s, "READ ", 5) && args(s + 5, a, 1)) {
        if (!BUS_PROTOCOL_CONFIRMED) Board_Print("ERR bus protocol/wiring not confirmed\r\n");
        else if (a[0] < 1 || a[0] > 4 || read_id) Board_Print("ERR ID range or read pending\r\n");
        else if (send_bus((uint8_t)a[0], BUS_POS_READ)) { read_id = (uint8_t)a[0]; read_start = Board_Millis(); }
        else Board_Print("ERR bus TX\r\n");
    } else if (!strncmp(s, "MOVE ", 5) && args(s + 5, a, 3)) {
        if (!armed || !MOTION_OUTPUT_ENABLE || !BUS_PROTOCOL_CONFIRMED) Board_Print("ERR motion/bus locked\r\n");
        else if (a[0] < 1 || a[0] > 4 || a[1] < BUS_TEST_MIN || a[1] > BUS_TEST_MAX || a[2] < 500 || a[2] > 3000)
            Board_Print("ERR test limits: ID 1..4 position 450..550 time 500..3000\r\n");
        else {
            n = Bus_Move(frame, (uint8_t)a[0], (uint16_t)a[1], (uint16_t)a[2]);
            if (Board_Write(PORT_BUS, frame, n)) {
                moved_mask |= (uint8_t)(1U << (a[0] - 1)); lease_start = Board_Millis();
                Board_Print("SENT MOVE (no position acknowledgement)\r\n");
            } else Board_Print("ERR bus TX\r\n");
        }
    } else Board_Print("ERR command; send HELP\r\n");
}
static void debug_poll(void)
{
    uint8_t b;
    int r;
    while ((r = Board_Read(PORT_DEBUG, &b)) != 0) {
        if (r < 0) { discard_line = 1; command_used = 0; continue; }
        if (b == '\n') {
            if (!discard_line && command_used) { command[command_used] = 0; execute(command); }
            discard_line = 0; command_used = 0;
        } else if (b != '\r' && !discard_line) {
            if (b < 32 || b > 126 || command_used >= sizeof(command) - 1) { discard_line = 1; command_used = 0; }
            else command[command_used++] = (char)b;
        }
    }
}
static void bus_poll(void)
{
    uint8_t b;
    int r;
    while ((r = Board_Read(PORT_BUS, &b)) != 0) {
        if (r < 0) { bus.used = 0; ++bus.bad; continue; }
        if (Bus_Feed(&bus, b, Board_Millis()) && read_id && bus.id == read_id &&
            bus.command == BUS_POS_READ && bus.parameter_count == 2) {
            char s[60];
            int16_t p = (int16_t)((uint16_t)bus.parameters[0] | (uint16_t)bus.parameters[1] << 8);
            snprintf(s, sizeof(s), "POSITION id=%u raw=%d\r\n", (unsigned)read_id, (int)p);
            Board_Print(s); read_id = 0;
        }
    }
    if (read_id && (uint32_t)(Board_Millis() - read_start) >= 100U) { read_id = 0; Board_Print("ERR position timeout\r\n"); }
}
int main(void)
{
    uint32_t report_ms = 0;
    K230_Init(); Board_Init(); RobotConsole_Init(&robot, robot_output, 0);
    Board_Print("MSPM0G3507 robot bench v2.1 | SYSOSC 32MHz | UART 115200 8N1\r\n");
    Board_Print("DEBUG UART0: PA10=TX PA11=RX | SWD: PA19=DIO PA20=CLK\r\n");
    Board_Print("No automatic motion. Send HELP + newline.\r\n");
    for (;;) {
        uint32_t now = Board_Millis();
        K230_Poll(now);
        if (armed && (uint32_t)(now - lease_start) >= MANUAL_LEASE_MS) disarm();
        debug_poll(); bus_poll();
        Workflow_Poll(&robot.flow, Board_Millis());
        if ((uint32_t)(now - report_ms) >= 1000U) { report_ms = now; status(); }
    }
}
