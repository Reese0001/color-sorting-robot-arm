#ifndef APP_CONFIG_H
#define APP_CONFIG_H
/* Set these only after board wiring, power rails and servo limits are checked. */
#define MOTION_OUTPUT_ENABLE 0
#define BUS_PROTOCOL_CONFIRMED 0
#define CPU_HZ 32000000UL
#define UART_BAUD 115200UL
#define PWM_PERIOD_US 20000U
#define PWM_MIN_US 1000U
#define PWM_MAX_US 2000U
#define MANUAL_LEASE_MS 10000UL
/* Provisional single-servo test limits, NOT calibrated robot joint limits. */
#define BUS_TEST_MIN 450U
#define BUS_TEST_MAX 550U
#endif
