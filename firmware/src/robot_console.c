#include "robot_console.h"
#include <stdio.h>
#include <string.h>
static void print(RobotConsole *c, const char *s) { if (c->output) c->output(c->output_context, s); }
static void event(void *context, WorkflowEvent e)
{
    static const char * const names[] = {"START","STEP","SIM_ACK","PAUSE","RESUME","STOP","RESET","DONE","FAULT"};
    RobotConsole *c = (RobotConsole *)context;
    RobotWorkflow *w = &c->flow;
    char s[220];
    if (e == EV_STEP) {
        snprintf(s, sizeof(s), "DRY STEP %u/7 %s pose=%s ticket=%lu [positions UNCALIBRATED; no servo output]\r\n",
            (unsigned)w->step+1, Workflow_StepName(w->step), g_robot_poses[Workflow_Pose(w)].name,
            (unsigned long)w->ticket);
    } else {
        snprintf(s, sizeof(s), "DRY %s state=%s color=%s bin=%s step=%s ticket=%lu fault=%s\r\n",
            names[(unsigned)e], Workflow_StateName(w->state), Robot_ColorName(w->color), Robot_BinName(w->color),
            Workflow_StepName(w->step), (unsigned long)w->ticket, Workflow_FaultName(w->fault));
    }
    print(c, s);
}
void RobotConsole_Init(RobotConsole *c, RobotOutput output, void *context)
{
    c->output = output; c->output_context = context;
    Workflow_Init(&c->flow, event, c);
}
void RobotConsole_Help(RobotConsole *c)
{
    print(c, "DRY ONLY: START RED|GREEN|BLUE; PAUSE; RESUME; STOP; RESET; FLOW; JOINTS; POSES\r\n");
    print(c, "SIM AUTO|MANUAL (idle only); ACK ticket (manual); SIM STALL; SIM FAIL\r\n");
    print(c, "AUTO ack=1000ms/step; timeout=3000ms active time. No physical motion.\r\n");
}
void RobotConsole_Status(RobotConsole *c)
{
    char s[220];
    RobotWorkflow *w = &c->flow;
    snprintf(s, sizeof(s), "FLOW dry=1 state=%s color=%s bin=%s step=%s elapsed=%lu ticket=%lu mode=%s fault=%s\r\n",
        Workflow_StateName(w->state), Robot_ColorName(w->color), Robot_BinName(w->color),
        Workflow_StepName(w->step), (unsigned long)w->elapsed_ms, (unsigned long)w->ticket,
        w->mode == SIM_AUTO ? "AUTO" : "MANUAL", Workflow_FaultName(w->fault));
    print(c, s);
}
static int verb(const char *s, const char *v)
{
    size_t n = strlen(v);
    return !strncmp(s, v, n) && (s[n] == 0 || s[n] == ' ');
}
int RobotConsole_IsCommand(const char *s)
{
    static const char * const verbs[] = {"START","PAUSE","RESUME","STOP","RESET","FLOW","JOINTS","POSES","SIM","ACK"};
    unsigned i;
    for (i = 0; i < sizeof(verbs)/sizeof(verbs[0]); ++i) if (verb(s, verbs[i])) return 1;
    return 0;
}
static int ticket_number(const char *s, uint32_t *n)
{
    uint32_t value = 0, digit;
    if (!*s) return 0;
    while (*s) {
        if (*s < '0' || *s > '9') return 0;
        digit = (uint32_t)(*s++ - '0');
        if (value > (UINT32_MAX - digit)/10U) return 0;
        value = value*10U + digit;
    }
    if (!value) return 0;
    *n = value; return 1;
}
int RobotConsole_Command(RobotConsole *c, const char *s, uint32_t now)
{
    WorkflowResult result = WF_OK;
    char text[220];
    uint32_t ticket;
    unsigned i;
    if (!RobotConsole_IsCommand(s)) return 0;
    if (!strcmp(s,"START RED")) result=Workflow_Start(&c->flow,ROBOT_RED,now);
    else if (!strcmp(s,"START GREEN")) result=Workflow_Start(&c->flow,ROBOT_GREEN,now);
    else if (!strcmp(s,"START BLUE")) result=Workflow_Start(&c->flow,ROBOT_BLUE,now);
    else if (!strcmp(s,"PAUSE")) result=Workflow_Pause(&c->flow,now);
    else if (!strcmp(s,"RESUME")) result=Workflow_Resume(&c->flow,now);
    else if (!strcmp(s,"STOP")) result=Workflow_Stop(&c->flow);
    else if (!strcmp(s,"RESET")) result=Workflow_Reset(&c->flow);
    else if (!strcmp(s,"FLOW")) RobotConsole_Status(c);
    else if (!strcmp(s,"SIM AUTO")) result=Workflow_SetMode(&c->flow,SIM_AUTO);
    else if (!strcmp(s,"SIM MANUAL")) result=Workflow_SetMode(&c->flow,SIM_MANUAL);
    else if (!strcmp(s,"SIM STALL")) result=Workflow_Stall(&c->flow);
    else if (!strcmp(s,"SIM FAIL")) result=Workflow_Fail(&c->flow);
    else if (!strncmp(s,"ACK ",4) && ticket_number(s+4,&ticket)) result=Workflow_Ack(&c->flow,ticket,now);
    else if (!strcmp(s,"JOINTS")) {
        for (i=0; i<ROBOT_JOINT_COUNT; ++i) {
            const RobotJoint *j=&g_robot_joints[i];
            snprintf(text,sizeof(text),"JOINT %s id=%u id_ok=%u dir=%d zero=%d min=%d max=%d max_speed=%u calibrated=%u\r\n",
                j->name,(unsigned)j->servo_id,(unsigned)j->id_confirmed,(int)j->direction,
                (int)j->zero_raw,(int)j->min_raw,(int)j->max_raw,(unsigned)j->max_speed_raw_s,(unsigned)j->calibrated);
            print(c,text);
        }
        snprintf(text,sizeof(text),"CONFIG issues=0x%02lX; -1/0 placeholders are NOT motion targets\r\n",
            (unsigned long)Robot_JointIssues(g_robot_joints)); print(c,text);
    } else if (!strcmp(s,"POSES")) {
        for (i=0; i<ROBOT_POSE_COUNT; ++i) {
            const RobotPose *p=&g_robot_poses[i];
            snprintf(text,sizeof(text),"POSE %s mask=%u raw=%d,%d,%d,%d move_ms=%u calibrated=%u issues=0x%02lX\r\n",
                p->name,(unsigned)p->joint_mask,(int)p->raw[0],(int)p->raw[1],(int)p->raw[2],(int)p->raw[3],
                (unsigned)p->move_ms,(unsigned)p->calibrated,(unsigned long)Robot_PoseIssues(g_robot_joints,p));
            print(c,text);
        }
    } else { print(c,"ERR DRY command syntax; send HELP\r\n"); return 1; }
    if (result != WF_OK) {
        snprintf(text,sizeof(text),"ERR DRY %s\r\n",Workflow_ResultName(result)); print(c,text);
    }
    return 1;
}
