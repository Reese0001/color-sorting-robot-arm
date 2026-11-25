#include "pololu/VL53L0X.h"
#include "ti_msp_dl_config.h"
#include "text.h"

TwoWire Wire;
static VL53L0X sensor;
static constexpr uint32_t faults = DL_I2C_INTERRUPT_CONTROLLER_NACK |
                                  DL_I2C_INTERRUPT_CONTROLLER_ARBITRATION_LOST;
static constexpr uint32_t completed = DL_I2C_INTERRUPT_CONTROLLER_TX_DONE |
                                     DL_I2C_INTERRUPT_CONTROLLER_RX_DONE;

/* Pololu's largest transaction is the register address plus six SPAD bytes.
 * It fits the controller FIFO; every hardware wait has a deadline. */
static bool transfer(uint8_t address, uint8_t *bytes, uint8_t count, bool reading)
{
    if (!count || count > 8 || Wire.failed) return false;
    const uint32_t start = millis();
    while (!(DL_I2C_getControllerStatus(RANGE_INST) & DL_I2C_CONTROLLER_STATUS_IDLE))
        if (millis() - start >= 8) return false;
    DL_I2C_clearInterruptStatus(RANGE_INST, faults | completed);
    if (!reading && DL_I2C_fillControllerTXFIFO(RANGE_INST, bytes, count) != count)
        return false;
    const uint32_t done = reading ? DL_I2C_INTERRUPT_CONTROLLER_RX_DONE :
                                    DL_I2C_INTERRUPT_CONTROLLER_TX_DONE;
    DL_I2C_startControllerTransfer(RANGE_INST, address, reading ?
        DL_I2C_CONTROLLER_DIRECTION_RX : DL_I2C_CONTROLLER_DIRECTION_TX, count);
    for (;;) {
        uint32_t flags = DL_I2C_getRawInterruptStatus(RANGE_INST, faults | done);
        if ((flags & faults) || millis() - start >= 8) return false;
        if (flags & done) break;
    }
    if (reading) {
        for (unsigned i = 0; i < count; i++) {
            if (DL_I2C_isControllerRXFIFOEmpty(RANGE_INST)) return false;
            bytes[i] = DL_I2C_receiveControllerData(RANGE_INST);
        }
    }
    return true;
}

void TwoWire::beginTransmission(uint8_t addr)
{
    address = addr;
    length = 0;
}
void TwoWire::write(uint8_t value)
{
    if (length < sizeof(bytes)) bytes[length++] = value;
    else failed = true;
}
uint8_t TwoWire::endTransmission()
{
    if (!transfer(address, bytes, length, false)) failed = true;
    return failed ? 4 : 0;
}
void TwoWire::requestFrom(uint8_t addr, uint8_t count)
{
    index = length = 0;
    if (transfer(addr, bytes, count, true)) length = count;
    else failed = true;
}
uint8_t TwoWire::read()
{
    if (index < length) return bytes[index++];
    failed = true;
    return 0xff;
}

void range_update(char *line, unsigned size)
{
    static bool running = false, attempted = false;
    static uint32_t lastAttempt, lastReady;
    uint32_t now = millis();
    if (!running) {
        if (attempted && now - lastAttempt < 1200) return;
        attempted = true;
        lastAttempt = now;
        if (Wire.failed) {
            DL_I2C_reset(RANGE_INST);
            DL_I2C_enablePower(RANGE_INST);
            delay_cycles(POWER_STARTUP_DELAY);
            SYSCFG_DL_RANGE_init();
            Wire.failed = false;
        }
        uint8_t id = sensor.readReg(VL53L0X::IDENTIFICATION_MODEL_ID);
        if (Wire.failed) {
            append(line, line + size-1, "TOF NO I2C REPLY");
            return;
        }
        if (id != 0xee) {
            number_line(line, size, "TOF CHIP ID ", id, "");
            return;
        }
        // Reset the sensor as the MCU can reboot separately from its supply.
        sensor.writeReg(0xbf, 0);
        delay_cycles(CPUCLK_FREQ / 500);
        sensor.writeReg(0xbf, 1);
        delay_cycles(CPUCLK_FREQ / 100);
        sensor.setTimeout(100);
        if (!sensor.init() || Wire.failed) {
            append(line, line + size-1, "TOF INIT FAIL");
            return;
        }
        sensor.startContinuous();
        running = !Wire.failed;
        lastReady = millis();
        append(line, line + size-1, running ? "TOF STARTED" : "TOF START FAIL");
        return;
    }
    uint8_t ready = sensor.readReg(VL53L0X::RESULT_INTERRUPT_STATUS);
    if (!Wire.failed && (ready & 7)) {
        const uint8_t status = (sensor.readReg(VL53L0X::RESULT_RANGE_STATUS) >> 3) & 15;
        const unsigned mm = sensor.readReg16Bit(VL53L0X::RESULT_RANGE_STATUS + 10);
        sensor.writeReg(VL53L0X::SYSTEM_INTERRUPT_CLEAR, 1);
        if (!Wire.failed) {
            lastReady = now;
            if (status == 11 && mm > 0 && mm < 8190)
                number_line(line, size, "TOF ", mm, " MM");
            else number_line(line, size, "TOF INVALID ", status, "");
            return;
        }
    }
    if (Wire.failed || now - lastReady > 500) {
        append(line, line + size-1, Wire.failed ? "TOF I2C LOST" : "TOF DATA TIMEOUT");
        running = false;
        lastAttempt = now;
    }
}
