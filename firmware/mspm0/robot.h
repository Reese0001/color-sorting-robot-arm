#ifndef ROBOT_H
#define ROBOT_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* HAL: UART calls must be bounded; no heap or board headers in the core. */
void hal_log(const char *line);
void hal_camera(const char *line);
void hal_bus_write(const uint8_t *data, size_t count);
void hal_pwm(uint16_t yaw_us, uint16_t shoulder_us);
void robot_init(void);
void robot_tick(uint32_t now);
void robot_console(char byte, uint32_t now);
void robot_camera(char byte, uint32_t now);
void robot_bus(uint8_t byte, uint32_t now);
void robot_stop(const char *reason);

typedef struct {
    uint16_t value[5]; /* J1/J2: microseconds; J3/J4/claw: 0..1000 bus units */
} Pose;
typedef struct {
    bool armed, moving, automatic, cycle, fault;
    uint8_t stage;
    Pose position;
} RobotStatus;
RobotStatus robot_status(void);
#endif
