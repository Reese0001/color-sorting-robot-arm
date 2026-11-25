#include "servo_arm.h"

#include <Wire.h>

namespace {
constexpr float PWM_FREQUENCY_HZ = 50.0f;
constexpr float PWM_PERIOD_US = 1000000.0f / PWM_FREQUENCY_HZ;
constexpr uint16_t PWM_RESOLUTION = 4096;
constexpr uint16_t UPDATE_INTERVAL_MS = 20;
}

ServoArm::ServoArm() : pwm_(0x40), current_(POSE_HOME) {}

void ServoArm::begin() {
  Wire.begin();
  pwm_.begin();
  pwm_.setOscillatorFrequency(27000000);
  pwm_.setPWMFreq(PWM_FREQUENCY_HZ);
  delay(20);
  for (uint8_t i = 0; i < SERVO_COUNT; ++i) {
    setImmediate(i, current_.angle[i]);
  }
}

uint16_t ServoArm::angleToTicks(uint8_t channel, float angle) const {
  const ServoCalibration& calibration = SERVO_CALIBRATIONS[channel];
  angle = constrain(angle, calibration.minAngle, calibration.maxAngle);
  float normalized = (angle - calibration.minAngle) /
                     (calibration.maxAngle - calibration.minAngle);
  if (calibration.reversed) normalized = 1.0f - normalized;
  const float pulseUs = calibration.minPulseUs +
                        normalized * (calibration.maxPulseUs - calibration.minPulseUs);
  return static_cast<uint16_t>((pulseUs / PWM_PERIOD_US) * PWM_RESOLUTION);
}

float ServoArm::smoothStep(float value) {
  return value * value * (3.0f - 2.0f * value);
}

void ServoArm::setImmediate(uint8_t channel, float angle) {
  if (channel >= SERVO_COUNT) return;
  const ServoCalibration& calibration = SERVO_CALIBRATIONS[channel];
  angle = constrain(angle, calibration.minAngle, calibration.maxAngle);
  pwm_.setPWM(channel, 0, angleToTicks(channel, angle));
  current_.angle[channel] = angle;
}

void ServoArm::moveTo(const ArmPose& target, uint32_t durationMs) {
  const ArmPose start = current_;
  const uint32_t startedAt = millis();
  uint32_t elapsed = 0;

  do {
    elapsed = millis() - startedAt;
    const float progress = durationMs == 0
                               ? 1.0f
                               : min(1.0f, static_cast<float>(elapsed) / durationMs);
    const float eased = smoothStep(progress);
    for (uint8_t i = 0; i < SERVO_COUNT; ++i) {
      setImmediate(i, start.angle[i] + (target.angle[i] - start.angle[i]) * eased);
    }
    delay(UPDATE_INTERVAL_MS);
  } while (elapsed < durationMs);

  for (uint8_t i = 0; i < SERVO_COUNT; ++i) setImmediate(i, target.angle[i]);
}

void ServoArm::moveServo(uint8_t channel, float angle, uint32_t durationMs) {
  ArmPose target = current_;
  if (channel < SERVO_COUNT) target.angle[channel] = angle;
  moveTo(target, durationMs);
}

const ArmPose& ServoArm::currentPose() const { return current_; }
