#pragma once
#include <stdint.h>
class TwoWire {
public:
    bool failed = false;
    void beginTransmission(uint8_t address);
    void write(uint8_t value);
    uint8_t endTransmission();
    void requestFrom(uint8_t address, uint8_t count);
    uint8_t read();
private:
    uint8_t bytes[8], address, length, index;
};
extern TwoWire Wire;
