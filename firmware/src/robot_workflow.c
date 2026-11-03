#include "robot_workflow.h"
#include <string.h>
static void emit(RobotWorkflow *w, WorkflowEvent e) { if (w->notify) w->notify(w->context, e); }
static void enter_step(RobotWorkflow *w, uint32_t now)
{
    w->last_ms = now; w->elapsed_ms = 0;
    if (++w->ticket == 0) ++w->ticket;
    emit(w, EV_STEP);
}
static void fail(RobotWorkflow *w, WorkflowFault fault)
{
    w->fault = fault; w->state = WF_FAULT; emit(w, EV_FAULT);
}
static void advance(RobotWorkflow *w, uint32_t now)
{
    emit(w, EV_SIM_ACK);
    if (w->step == STEP_RETURN) { w->state = WF_DONE; emit(w, EV_DONE); }
    else { w->step = (WorkflowStep)((unsigned)w->step + 1U); enter_step(w, now); }
}
void Workflow_Init(RobotWorkflow *w, WorkflowNotify notify, void *context)
{
    memset(w, 0, sizeof(*w));
    w->color = ROBOT_COLOR_COUNT; w->notify = notify; w->context = context;
}
int Workflow_Busy(const RobotWorkflow *w) { return w->state == WF_RUNNING || w->state == WF_PAUSED; }
WorkflowResult Workflow_Start(RobotWorkflow *w, RobotColor color, uint32_t now)
{
    if (w->state != WF_IDLE) return WF_BAD_STATE;
    if ((unsigned)color >= ROBOT_COLOR_COUNT) return WF_BAD_COLOR;
    w->color = color; w->step = STEP_READY; w->fault = FAULT_NONE;
    w->suppress_ack = 0; w->state = WF_RUNNING;
    emit(w, EV_START); enter_step(w, now);
    return WF_OK;
}
void Workflow_Poll(RobotWorkflow *w, uint32_t now)
{
    uint32_t delta;
    if (w->state != WF_RUNNING) return;
    delta = now - w->last_ms; w->last_ms = now;
    /* Saturate; an overdue poll must fail rather than wrap back into a valid wait. */
    if (delta >= WF_STEP_TIMEOUT_MS - w->elapsed_ms) {
        w->elapsed_ms = WF_STEP_TIMEOUT_MS; fail(w, FAULT_TIMEOUT); return;
    }
    w->elapsed_ms += delta;
    if (w->mode == SIM_AUTO && !w->suppress_ack && w->elapsed_ms >= WF_SIM_ACTION_MS) advance(w, now);
}
WorkflowResult Workflow_Pause(RobotWorkflow *w, uint32_t now)
{
    if (w->state != WF_RUNNING) return WF_BAD_STATE;
    Workflow_Poll(w, now);
    if (w->state != WF_RUNNING) return WF_BAD_STATE;
    w->state = WF_PAUSED; emit(w, EV_PAUSE); return WF_OK;
}
WorkflowResult Workflow_Resume(RobotWorkflow *w, uint32_t now)
{
    if (w->state != WF_PAUSED) return WF_BAD_STATE;
    w->last_ms = now; w->state = WF_RUNNING; emit(w, EV_RESUME); return WF_OK;
}
WorkflowResult Workflow_Stop(RobotWorkflow *w)
{
    if (!Workflow_Busy(w)) return WF_BAD_STATE;
    w->state = WF_ABORTED; emit(w, EV_STOP); return WF_OK;
}
WorkflowResult Workflow_Reset(RobotWorkflow *w)
{
    if (Workflow_Busy(w)) return WF_BAD_STATE;
    /* Ticket survives RESET so a reply from a previous run cannot advance a new run. */
    w->state = WF_IDLE; w->step = STEP_READY; w->color = ROBOT_COLOR_COUNT;
    w->fault = FAULT_NONE; w->elapsed_ms = 0; w->suppress_ack = 0;
    emit(w, EV_RESET); return WF_OK;
}
WorkflowResult Workflow_SetMode(RobotWorkflow *w, WorkflowMode mode)
{
    if (w->state != WF_IDLE) return WF_BAD_STATE;
    if (mode != SIM_AUTO && mode != SIM_MANUAL) return WF_BAD_MODE;
    w->mode = mode; return WF_OK;
}
WorkflowResult Workflow_Ack(RobotWorkflow *w, uint32_t ticket, uint32_t now)
{
    if (w->state != WF_RUNNING || w->mode != SIM_MANUAL) return WF_BAD_STATE;
    if (ticket != w->ticket) return WF_STALE_ACK;
    Workflow_Poll(w, now);
    if (w->state != WF_RUNNING) return WF_BAD_STATE;
    advance(w, now); return WF_OK;
}
WorkflowResult Workflow_Stall(RobotWorkflow *w)
{
    if (w->state != WF_RUNNING || w->mode != SIM_AUTO) return WF_BAD_STATE;
    w->suppress_ack = 1; return WF_OK;
}
WorkflowResult Workflow_Fail(RobotWorkflow *w)
{
    if (!Workflow_Busy(w)) return WF_BAD_STATE;
    fail(w, FAULT_SIMULATED); return WF_OK;
}
RobotPoseId Workflow_Pose(const RobotWorkflow *w)
{
    static const RobotPoseId poses[] = {POSE_READY, POSE_APPROACH, POSE_GRIP, POSE_LIFT,
                                      POSE_PLACE_RED, POSE_RELEASE, POSE_READY};
    if (w->step == STEP_PLACE && (unsigned)w->color < ROBOT_COLOR_COUNT)
        return (RobotPoseId)(POSE_PLACE_RED + (unsigned)w->color);
    return (unsigned)w->step < WF_STEP_COUNT ? poses[(unsigned)w->step] : POSE_READY;
}
const char *Workflow_StateName(WorkflowState s)
{
    static const char * const n[] = {"IDLE","RUNNING","PAUSED","DONE","ABORTED","FAULT"};
    return (unsigned)s < 6 ? n[(unsigned)s] : "INVALID";
}
const char *Workflow_StepName(WorkflowStep s)
{
    static const char * const n[] = {"READY","APPROACH","GRIP","LIFT","PLACE","RELEASE","RETURN"};
    return (unsigned)s < WF_STEP_COUNT ? n[(unsigned)s] : "INVALID";
}
const char *Workflow_FaultName(WorkflowFault f)
{
    static const char * const n[] = {"NONE","TIMEOUT","SIMULATED_FAILURE"};
    return (unsigned)f < 3 ? n[(unsigned)f] : "INVALID";
}
const char *Workflow_ResultName(WorkflowResult r)
{
    static const char * const n[] = {"OK","STATE_REJECTED","INVALID_COLOR","INVALID_MODE","STALE_ACK"};
    return (unsigned)r < 5 ? n[(unsigned)r] : "INVALID";
}
