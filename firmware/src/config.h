#pragma once

#include <Arduino.h>

constexpr uint8_t SERVO_COUNT = 4;
constexpr uint8_t SERVO_BASE = 0;
constexpr uint8_t SERVO_SHOULDER = 1;
constexpr uint8_t SERVO_ELBOW = 2;
constexpr uint8_t SERVO_GRIPPER = 3;

struct ServoCalibration {
  uint16_t minPulseUs;
  uint16_t maxPulseUs;
  float minAngle;
  float maxAngle;
  bool reversed;
};

struct ArmPose {
  float angle[SERVO_COUNT];
};

// Tune pulse widths and safe angles for the actual servos before mounting links.
constexpr ServoCalibration SERVO_CALIBRATIONS[SERVO_COUNT] = {
    {500, 2500, 10, 170, false},  // base
    {600, 2400, 20, 155, true},   // shoulder
    {600, 2400, 15, 165, false},  // elbow
    {700, 2200, 35, 105, false},  // gripper
};

constexpr ArmPose POSE_HOME = {{90, 70, 100, 90}};
constexpr ArmPose POSE_PICK_APPROACH = {{90, 100, 125, 90}};
constexpr ArmPose POSE_PICK = {{90, 118, 142, 90}};
constexpr ArmPose POSE_LIFT = {{90, 75, 105, 55}};
constexpr ArmPose POSE_RED = {{35, 78, 108, 55}};
constexpr ArmPose POSE_GREEN = {{90, 78, 108, 55}};
constexpr ArmPose POSE_BLUE = {{145, 78, 108, 55}};

constexpr float GRIPPER_OPEN_ANGLE = 90;
constexpr float GRIPPER_CLOSED_ANGLE = 55;

constexpr uint32_t MOVE_FAST_MS = 700;
constexpr uint32_t MOVE_NORMAL_MS = 1100;
constexpr uint32_t MOVE_SLOW_MS = 1500;
constexpr uint32_t GRIPPER_WAIT_MS = 450;

// QQVGA image-space gate around the fixed pickup point.
constexpr int PICK_CENTER_X = 80;
constexpr int PICK_CENTER_Y = 62;
constexpr int PICK_TOLERANCE_X = 22;
constexpr int PICK_TOLERANCE_Y = 18;
constexpr uint8_t REQUIRED_STABLE_FRAMES = 5;
constexpr uint32_t DETECTION_TIMEOUT_MS = 400;
