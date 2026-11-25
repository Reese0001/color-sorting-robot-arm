#include "ti_msp_dl_config.h"
#include "robot.h"
#include <string.h>

static volatile uint32_t milliseconds;
static volatile bool io_fault;
typedef struct {volatile unsigned head,tail;uint8_t data[256];} Ring;
static Ring rx[3];
static bool pwm_started;

void SysTick_Handler(void) {milliseconds++;}
static void receive(UART_Regs *uart,Ring *ring) {
    unsigned quota=64;
    while(!DL_UART_Main_isRXFIFOEmpty(uart) && quota--) {
        uint8_t b=DL_UART_Main_receiveData(uart);
        unsigned next=(ring->head+1)&255;
        if(next==ring->tail) io_fault=true;
        else {ring->data[ring->head]=b;ring->head=next;}
    }
}
void CONSOLE_INST_IRQHandler(void) {receive(CONSOLE_INST,&rx[0]);}
void CAMERA_INST_IRQHandler(void) {receive(CAMERA_INST,&rx[1]);}
void SERVO_BUS_INST_IRQHandler(void) {receive(SERVO_BUS_INST,&rx[2]);}
static bool send(UART_Regs *uart,const uint8_t *p,size_t n) {
    for(size_t i=0;i<n;i++) {
        uint32_t start=milliseconds;
        while(DL_UART_Main_isTXFIFOFull(uart)) if(milliseconds-start>5) {io_fault=true;return false;}
        DL_UART_Main_transmitData(uart,p[i]);
    }
    return true;
}
void hal_log(const char *line) {send(CONSOLE_INST,(const uint8_t *)line,strlen(line));}
void hal_camera(const char *line) {send(CAMERA_INST,(const uint8_t *)line,strlen(line));}
void hal_bus_write(const uint8_t *p,size_t n) {send(SERVO_BUS_INST,p,n);}
void hal_pwm(uint16_t yaw,uint16_t shoulder) {
    /* Both timers: 32MHz / 32 -> 1MHz; period 20000 ticks -> 50Hz. */
    DL_TimerA_setCaptureCompareValue(ARM_PWM_INST,yaw,DL_TIMER_CC_1_INDEX);
    DL_TimerG_setCaptureCompareValue(SHOULDER_PWM_INST,shoulder,DL_TIMER_CC_1_INDEX);
    if(!pwm_started) {
        DL_TimerA_setCaptCompUpdateMethod(ARM_PWM_INST,DL_TIMER_CC_UPDATE_METHOD_ZERO_EVT,DL_TIMER_CC_1_INDEX);
        DL_TimerG_setCaptCompUpdateMethod(SHOULDER_PWM_INST,DL_TIMER_CC_UPDATE_METHOD_ZERO_EVT,DL_TIMER_CC_1_INDEX);
        DL_TimerA_startCounter(ARM_PWM_INST);
        DL_TimerG_startCounter(SHOULDER_PWM_INST);
        pwm_started=true;
    }
}
int main(void) {
    SYSCFG_DL_init();
    /* PA2/K1 active low; ensure disconnected input does not float. */
    DL_GPIO_initDigitalInputFeatures(STOP_KEY_K1_IOMUX,DL_GPIO_INVERSION_DISABLE,
        DL_GPIO_RESISTOR_PULL_UP,DL_GPIO_HYSTERESIS_ENABLE,DL_GPIO_WAKEUP_DISABLE);
    SysTick_Config(CPUCLK_FREQ/1000);
    NVIC_EnableIRQ(CONSOLE_INST_INT_IRQN);
    NVIC_EnableIRQ(CAMERA_INST_INT_IRQN);
    NVIC_EnableIRQ(SERVO_BUS_INST_INT_IRQN);
    robot_init();
    bool key_latched=false;
    while(1) {
        /* Feed only from main: a stuck main loop triggers hardware watchdog reset. */
        DL_WWDT_restart(WATCHDOG_INST);
        bool pressed=DL_GPIO_readPins(STOP_KEY_PORT,STOP_KEY_K1_PIN)==0;
        if(pressed && !key_latched) robot_stop("K1");
        key_latched=pressed;
        if(io_fault) {
            io_fault=false;
            for(unsigned i=0;i<3;i++)rx[i].tail=rx[i].head;
            robot_stop("UART overflow or TX timeout");
        }
        for(unsigned i=0;i<3;i++) {
            unsigned quota=64;
            while(rx[i].tail!=rx[i].head && quota--) {
                uint8_t b=rx[i].data[rx[i].tail];rx[i].tail=(rx[i].tail+1)&255;
                if(i==0) { if(!pressed)robot_console((char)b,milliseconds); }
                else if(i==1)robot_camera((char)b,milliseconds);
                else robot_bus(b,milliseconds);
            }
        }
        robot_tick(milliseconds);
    }
}
