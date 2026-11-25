#pragma once

#include <Adafruit_PWMServoDriver.h>
#include "config.h"

class ServoArm {
 public:
  ServoArm();
  void begin();
  void moveTo(const ArmPose& target, uint32_t durationMs);
  void moveServo(uint8_t channel, float angle, uint32_t durationMs);
  void setImmediate(uint8_t channel, float angle);
  const ArmPose& currentPose() const;

 private:
  Adafruit_PWMServoDriver pwm_;
  ArmPose current_;
  uint16_t angleToTicks(uint8_t channel, float angle) const;
  static float smoothStep(float value);
};
