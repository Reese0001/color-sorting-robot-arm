#ifndef ROBOT_WORKFLOW_H
#define ROBOT_WORKFLOW_H
#include "robot_config.h"
/* This engine has no hardware transport or real-motion mode. */
typedef enum { WF_IDLE, WF_RUNNING, WF_PAUSED, WF_DONE, WF_ABORTED, WF_FAULT } WorkflowState;
typedef enum { STEP_READY, STEP_APPROACH, STEP_GRIP, STEP_LIFT, STEP_PLACE,
               STEP_RELEASE, STEP_RETURN, WF_STEP_COUNT } WorkflowStep;
typedef enum { SIM_AUTO, SIM_MANUAL } WorkflowMode;
typedef enum { FAULT_NONE, FAULT_TIMEOUT, FAULT_SIMULATED } WorkflowFault;
typedef enum { EV_START, EV_STEP, EV_SIM_ACK, EV_PAUSE, EV_RESUME,
               EV_STOP, EV_RESET, EV_DONE, EV_FAULT } WorkflowEvent;
typedef enum { WF_OK, WF_BAD_STATE, WF_BAD_COLOR, WF_BAD_MODE, WF_STALE_ACK } WorkflowResult;
typedef void (*WorkflowNotify)(void *context, WorkflowEvent event);
typedef struct {
    WorkflowState state;
    WorkflowStep step;
    RobotColor color;
    WorkflowMode mode;
    WorkflowFault fault;
    uint32_t last_ms, elapsed_ms, ticket;
    uint8_t suppress_ack;
    WorkflowNotify notify;
    void *context;
} RobotWorkflow;
#define WF_SIM_ACTION_MS 1000UL
#define WF_STEP_TIMEOUT_MS 3000UL
void Workflow_Init(RobotWorkflow *w, WorkflowNotify notify, void *context);
WorkflowResult Workflow_Start(RobotWorkflow *w, RobotColor color, uint32_t now);
WorkflowResult Workflow_Pause(RobotWorkflow *w, uint32_t now);
WorkflowResult Workflow_Resume(RobotWorkflow *w, uint32_t now);
WorkflowResult Workflow_Stop(RobotWorkflow *w);
WorkflowResult Workflow_Reset(RobotWorkflow *w);
WorkflowResult Workflow_SetMode(RobotWorkflow *w, WorkflowMode mode);
WorkflowResult Workflow_Ack(RobotWorkflow *w, uint32_t ticket, uint32_t now);
WorkflowResult Workflow_Stall(RobotWorkflow *w);
WorkflowResult Workflow_Fail(RobotWorkflow *w);
void Workflow_Poll(RobotWorkflow *w, uint32_t now);
int Workflow_Busy(const RobotWorkflow *w);
RobotPoseId Workflow_Pose(const RobotWorkflow *w);
const char *Workflow_StateName(WorkflowState state);
const char *Workflow_StepName(WorkflowStep step);
const char *Workflow_FaultName(WorkflowFault fault);
const char *Workflow_ResultName(WorkflowResult result);
#endif
