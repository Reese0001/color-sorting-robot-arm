#include "robot_config.h"

/* ID assignments are proposals. No configuration is written into any servo. */
const RobotJoint g_robot_joints[ROBOT_JOINT_COUNT] = {
    {"BASE",     1, 0, 0, 0, -1, -1, -1, 0},
    {"SHOULDER", 2, 0, 0, 0, -1, -1, -1, 0},
    {"ELBOW",    3, 0, 0, 0, -1, -1, -1, 0},
    {"GRIPPER",  4, 0, 0, 0, -1, -1, -1, 0}
};
/* No guessed joint positions. Masks: bits 0..3 = base/shoulder/elbow/gripper. */
const RobotPose g_robot_poses[ROBOT_POSE_COUNT] = {
    {"READY",       15, 0, {-1,-1,-1,-1}, 0},
    {"APPROACH",     7, 0, {-1,-1,-1,-1}, 0},
    {"GRIP",         8, 0, {-1,-1,-1,-1}, 0},
    {"LIFT",         7, 0, {-1,-1,-1,-1}, 0},
    {"PLACE_RED",    7, 0, {-1,-1,-1,-1}, 0},
    {"PLACE_GREEN",  7, 0, {-1,-1,-1,-1}, 0},
    {"PLACE_BLUE",   7, 0, {-1,-1,-1,-1}, 0},
    {"RELEASE",      8, 0, {-1,-1,-1,-1}, 0}
};
static uint32_t joint_issues(const RobotJoint *j)
{
    uint32_t errors = 0;
    if (!j->id_confirmed || j->servo_id > 253) errors |= CONFIG_ID;
    if (!j->calibrated) errors |= CONFIG_UNCALIBRATED;
    if (j->direction != 1 && j->direction != -1) errors |= CONFIG_DIRECTION;
    if (j->min_raw < 0 || j->max_raw > 1000 || j->min_raw >= j->max_raw ||
        j->zero_raw < j->min_raw || j->zero_raw > j->max_raw) errors |= CONFIG_RANGE;
    if (!j->max_speed_raw_s) errors |= CONFIG_SPEED;
    return errors;
}
uint32_t Robot_JointIssues(const RobotJoint *joints)
{
    unsigned i, j;
    uint32_t errors = 0;
    if (!joints) return CONFIG_UNCALIBRATED;
    for (i = 0; i < ROBOT_JOINT_COUNT; ++i) {
        errors |= joint_issues(&joints[i]);
        for (j = 0; j < i; ++j)
            if (joints[i].servo_id == joints[j].servo_id) errors |= CONFIG_DUPLICATE_ID;
    }
    return errors;
}
uint32_t Robot_PoseIssues(const RobotJoint *joints, const RobotPose *pose)
{
    unsigned i;
    uint32_t errors = Robot_JointIssues(joints);
    if (!joints || !pose) return errors | CONFIG_POSE;
    if (!pose->calibrated || !pose->joint_mask || (pose->joint_mask & 0xf0U) ||
        !pose->move_ms || pose->move_ms > 30000) errors |= CONFIG_POSE;
    for (i = 0; i < ROBOT_JOINT_COUNT; ++i) {
        if (pose->joint_mask & (1U << i)) {
            if (pose->raw[i] < joints[i].min_raw || pose->raw[i] > joints[i].max_raw ||
                pose->raw[i] < 0 || pose->raw[i] > 1000) errors |= CONFIG_POSE;
        } else if (pose->raw[i] != ROBOT_RAW_UNKNOWN) errors |= CONFIG_POSE;
    }
    return errors;
}
int Robot_OffsetToRaw(const RobotJoint *joint, int32_t offset, uint16_t *raw)
{
    int32_t result;
    if (!joint || !raw || joint_issues(joint) || offset < -1000 || offset > 1000) return 0;
    result = joint->zero_raw + joint->direction * offset;
    if (result < joint->min_raw || result > joint->max_raw) return 0;
    *raw = (uint16_t)result;
    return 1;
}
const char *Robot_ColorName(RobotColor c)
{
    static const char * const names[] = {"RED", "GREEN", "BLUE"};
    return (unsigned)c < ROBOT_COLOR_COUNT ? names[(unsigned)c] : "NONE";
}
const char *Robot_BinName(RobotColor c)
{
    static const char * const names[] = {"LEFT", "CENTER", "RIGHT"};
    return (unsigned)c < ROBOT_COLOR_COUNT ? names[(unsigned)c] : "NONE";
}
