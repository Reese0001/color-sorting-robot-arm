#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H
#include <stdint.h>
#define ROBOT_JOINT_COUNT 4U
#define ROBOT_RAW_UNKNOWN (-1)
typedef enum { ROBOT_RED, ROBOT_GREEN, ROBOT_BLUE, ROBOT_COLOR_COUNT } RobotColor;
typedef enum {
    POSE_READY, POSE_APPROACH, POSE_GRIP, POSE_LIFT,
    POSE_PLACE_RED, POSE_PLACE_GREEN, POSE_PLACE_BLUE, POSE_RELEASE,
    ROBOT_POSE_COUNT
} RobotPoseId;
typedef struct {
    const char *name;
    uint8_t servo_id, id_confirmed, calibrated;
    int8_t direction; /* 0 unknown; +1/-1 after physical calibration */
    int16_t zero_raw, min_raw, max_raw;
    uint16_t max_speed_raw_s; /* 0 unknown; raw units per second, NOT degrees */
} RobotJoint;
typedef struct {
    const char *name;
    uint8_t joint_mask, calibrated;
    int16_t raw[ROBOT_JOINT_COUNT];
    uint16_t move_ms; /* 0 unknown. Simulation timing is a separate parameter. */
} RobotPose;
enum {
    CONFIG_ID = 1U, CONFIG_DUPLICATE_ID = 2U, CONFIG_UNCALIBRATED = 4U,
    CONFIG_DIRECTION = 8U, CONFIG_RANGE = 16U, CONFIG_SPEED = 32U,
    CONFIG_POSE = 64U
};
extern const RobotJoint g_robot_joints[ROBOT_JOINT_COUNT];
extern const RobotPose g_robot_poses[ROBOT_POSE_COUNT];
uint32_t Robot_JointIssues(const RobotJoint *joints);
uint32_t Robot_PoseIssues(const RobotJoint *joints, const RobotPose *pose);
int Robot_OffsetToRaw(const RobotJoint *joint, int32_t offset, uint16_t *raw);
const char *Robot_ColorName(RobotColor color);
const char *Robot_BinName(RobotColor color);
#endif
