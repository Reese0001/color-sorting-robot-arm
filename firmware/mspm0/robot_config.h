#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H
/* Bench starting bounds, not measured limits. Verify unloaded before widening. */
#define PWM_MIN_US 1200
#define PWM_MAX_US 1800
#define BUS_MIN 200
#define BUS_MAX 800
#define BUS_BAUD 115200
#define CAMERA_BAUD 115200
#define VISION_STALE_MS 500U
#define BUS_STALE_MS 700U
#define POSE_TOLERANCE 15
#define OBSERVE_SETTLE_MS 1500U
#define PICK_X 320
#define PICK_Y 240
#define PICK_TOL_X 25
#define PICK_TOL_Y 25
/* Set matching unique IDs with BusServoTerminal, ONE servo connected at a time. */
static const uint8_t SERVO_IDS[3] = {1, 2, 3};
#endif
