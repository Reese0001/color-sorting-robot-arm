#include <Arduino.h>

#include "config.h"
#include "servo_arm.h"

enum class BlockColor { NONE, RED, GREEN, BLUE };

struct Detection {
  BlockColor color = BlockColor::NONE;
  int x = 0;
  int y = 0;
  int pixels = 0;
  uint32_t receivedAt = 0;
};

ServoArm arm;
HardwareSerial cameraSerial(PA10, PA9);  // RX, TX
Detection latest;
BlockColor stableColor = BlockColor::NONE;
uint8_t stableFrames = 0;
bool stopped = false;

const char* colorName(BlockColor color) {
  switch (color) {
    case BlockColor::RED: return "RED";
    case BlockColor::GREEN: return "GREEN";
    case BlockColor::BLUE: return "BLUE";
    default: return "NONE";
  }
}

BlockColor parseColor(const String& text) {
  if (text == "RED") return BlockColor::RED;
  if (text == "GREEN") return BlockColor::GREEN;
  if (text == "BLUE") return BlockColor::BLUE;
  return BlockColor::NONE;
}

bool centered(const Detection& detection) {
  return abs(detection.x - PICK_CENTER_X) <= PICK_TOLERANCE_X &&
         abs(detection.y - PICK_CENTER_Y) <= PICK_TOLERANCE_Y;
}

void readCamera() {
  if (!cameraSerial.available()) return;
  String line = cameraSerial.readStringUntil('\n');
  line.trim();
  if (line == "NONE") {
    stableFrames = 0;
    stableColor = BlockColor::NONE;
    return;
  }

  String fields[5];
  int field = 0;
  int start = 0;
  for (int i = 0; i <= line.length() && field < 5; ++i) {
    if (i == line.length() || line[i] == ',') {
      fields[field++] = line.substring(start, i);
      start = i + 1;
    }
  }
  if (field != 5 || fields[0] != "BLOCK") return;

  latest = {parseColor(fields[1]), fields[2].toInt(), fields[3].toInt(),
            fields[4].toInt(), millis()};
  if (latest.color == BlockColor::NONE || !centered(latest)) {
    stableFrames = 0;
    stableColor = BlockColor::NONE;
    return;
  }

  if (latest.color == stableColor) {
    stableFrames = min<uint8_t>(REQUIRED_STABLE_FRAMES, stableFrames + 1);
  } else {
    stableColor = latest.color;
    stableFrames = 1;
  }
}

const ArmPose& dropPose(BlockColor color) {
  if (color == BlockColor::RED) return POSE_RED;
  if (color == BlockColor::GREEN) return POSE_GREEN;
  return POSE_BLUE;
}

void sortBlock(BlockColor color) {
  if (color == BlockColor::NONE || stopped) return;
  Serial.print("Sorting: ");
  Serial.println(colorName(color));

  arm.moveTo(POSE_PICK_APPROACH, MOVE_NORMAL_MS);
  arm.moveTo(POSE_PICK, MOVE_SLOW_MS);
  arm.moveServo(SERVO_GRIPPER, GRIPPER_CLOSED_ANGLE, GRIPPER_WAIT_MS);
  delay(GRIPPER_WAIT_MS);
  arm.moveTo(POSE_LIFT, MOVE_NORMAL_MS);
  arm.moveTo(dropPose(color), MOVE_SLOW_MS);
  arm.moveServo(SERVO_GRIPPER, GRIPPER_OPEN_ANGLE, GRIPPER_WAIT_MS);
  delay(GRIPPER_WAIT_MS);
  arm.moveTo(POSE_LIFT, MOVE_NORMAL_MS);
  arm.moveTo(POSE_HOME, MOVE_SLOW_MS);

  stableFrames = 0;
  stableColor = BlockColor::NONE;
  cameraSerial.flush();
}

void printHelp() {
  Serial.println("Commands: HELP, HOME, SORT RED|GREEN|BLUE, SERVO <0-3> <angle>, STOP, RESUME");
}

void handleConsole() {
  if (!Serial.available()) return;
  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toUpperCase();

  if (command == "HELP") printHelp();
  else if (command == "STOP") {
    stopped = true;
    Serial.println("Stopped; current PWM positions are held.");
  } else if (command == "RESUME") {
    stopped = false;
    Serial.println("Resumed.");
  } else if (command == "HOME" && !stopped) {
    arm.moveTo(POSE_HOME, MOVE_SLOW_MS);
  } else if (command.startsWith("SORT ") && !stopped) {
    sortBlock(parseColor(command.substring(5)));
  } else if (command.startsWith("SERVO ") && !stopped) {
    int separator = command.indexOf(' ', 6);
    if (separator > 0) {
      int channel = command.substring(6, separator).toInt();
      float angle = command.substring(separator + 1).toFloat();
      if (channel >= 0 && channel < SERVO_COUNT) arm.moveServo(channel, angle, 500);
    }
  } else {
    Serial.println("Unknown or blocked command. Type HELP.");
  }
}

void setup() {
  Serial.begin(115200);
  cameraSerial.begin(115200);
  cameraSerial.setTimeout(20);
  arm.begin();
  delay(300);
  arm.moveTo(POSE_HOME, MOVE_SLOW_MS);
  Serial.println("Three-color sorting arm ready.");
  printHelp();
}

void loop() {
  handleConsole();
  readCamera();
  if (!stopped && stableFrames >= REQUIRED_STABLE_FRAMES &&
      millis() - latest.receivedAt <= DETECTION_TIMEOUT_MS) {
    sortBlock(stableColor);
  }
}
