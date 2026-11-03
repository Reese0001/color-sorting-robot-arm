#include "robot_console.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks, steps, done_events;
static char captured[16000];
#define CHECK(x) do { ++checks; if(!(x)) { printf("FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static void notify(void *ctx, WorkflowEvent e)
{
    (void)ctx;
    if(e==EV_STEP) ++steps;
    if(e==EV_DONE) ++done_events;
}
static void capture(void *ctx, const char *s)
{
    size_t used=strlen(captured);
    (void)ctx;
    if(used+strlen(s)<sizeof(captured)) strcat(captured,s);
}
static void config_tests(void)
{
    RobotJoint j[ROBOT_JOINT_COUNT];
    RobotPose p;
    unsigned i;
    uint16_t value=777;
    CHECK(Robot_JointIssues(g_robot_joints)!=0);
    CHECK(!Robot_OffsetToRaw(&g_robot_joints[0],0,&value)); CHECK(value==777);
    for(i=0;i<ROBOT_POSE_COUNT;++i) CHECK(Robot_PoseIssues(g_robot_joints,&g_robot_poses[i])!=0);
    memcpy(j,g_robot_joints,sizeof(j));
    for(i=0;i<ROBOT_JOINT_COUNT;++i) {
        j[i].id_confirmed=j[i].calibrated=1; j[i].direction=1;
        j[i].zero_raw=500; j[i].min_raw=100; j[i].max_raw=900; j[i].max_speed_raw_s=100;
    }
    CHECK(Robot_JointIssues(j)==0);
    CHECK(Robot_OffsetToRaw(&j[0],400,&value) && value==900);
    CHECK(!Robot_OffsetToRaw(&j[0],401,&value));
    j[0].direction=-1; CHECK(Robot_OffsetToRaw(&j[0],400,&value) && value==100);
    CHECK(!Robot_OffsetToRaw(&j[0],INT32_MAX,&value));
    CHECK(!Robot_OffsetToRaw(&j[0],INT32_MIN,&value));
    j[1].servo_id=j[0].servo_id; CHECK(Robot_JointIssues(j)&CONFIG_DUPLICATE_ID); j[1].servo_id=2;
    j[0].direction=0; CHECK(Robot_JointIssues(j)&CONFIG_DIRECTION); j[0].direction=1;
    j[0].min_raw=501; CHECK(Robot_JointIssues(j)&CONFIG_RANGE); j[0].min_raw=100;
    j[0].max_speed_raw_s=0; CHECK(Robot_JointIssues(j)&CONFIG_SPEED); j[0].max_speed_raw_s=100;
    j[0].id_confirmed=0; CHECK(Robot_JointIssues(j)&CONFIG_ID); j[0].id_confirmed=1;
    j[0].servo_id=254; CHECK(Robot_JointIssues(j)&CONFIG_ID); j[0].servo_id=1;
    p=g_robot_poses[POSE_GRIP]; p.calibrated=1; p.raw[3]=500; p.move_ms=1000;
    CHECK(Robot_PoseIssues(j,&p)==0);
    p.raw[3]=901; CHECK(Robot_PoseIssues(j,&p)&CONFIG_POSE); p.raw[3]=500;
    p.raw[0]=500; CHECK(Robot_PoseIssues(j,&p)&CONFIG_POSE); p.raw[0]=-1;
    p.joint_mask=0; CHECK(Robot_PoseIssues(j,&p)&CONFIG_POSE);
    CHECK(Robot_PoseIssues(0,&p)!=0); CHECK(!Robot_OffsetToRaw(0,0,&value));
}
static void flow_tests(void)
{
    RobotWorkflow w;
    unsigned color,i;
    uint32_t ticket;
    for(color=0;color<ROBOT_COLOR_COUNT;++color) {
        Workflow_Init(&w,notify,0); steps=done_events=0;
        CHECK(Workflow_Start(&w,(RobotColor)color,0)==WF_OK);
        for(i=0;i<WF_STEP_COUNT;++i) {
            CHECK(w.state==WF_RUNNING && (unsigned)w.step==i);
            if(i==STEP_PLACE) CHECK(Workflow_Pose(&w)==(RobotPoseId)(POSE_PLACE_RED+color));
            Workflow_Poll(&w,(i+1)*1000U);
        }
        CHECK(w.state==WF_DONE && steps==7 && done_events==1);
        Workflow_Poll(&w,99999); CHECK(done_events==1);
        CHECK(Workflow_Start(&w,ROBOT_RED,99999)==WF_BAD_STATE);
        CHECK(Workflow_Reset(&w)==WF_OK);
    }
    Workflow_Init(&w,0,0);
    CHECK(Workflow_Start(&w,(RobotColor)-1,0)==WF_BAD_COLOR); CHECK(w.state==WF_IDLE);
    CHECK(Workflow_SetMode(&w,(WorkflowMode)9)==WF_BAD_MODE);
    CHECK(Workflow_Pause(&w,0)==WF_BAD_STATE); CHECK(Workflow_Resume(&w,0)==WF_BAD_STATE);
    CHECK(Workflow_Stop(&w)==WF_BAD_STATE); CHECK(Workflow_Fail(&w)==WF_BAD_STATE);
    CHECK(Workflow_Start(&w,ROBOT_RED,100)==WF_OK);
    ticket=w.ticket;
    CHECK(Workflow_Start(&w,ROBOT_BLUE,200)==WF_BAD_STATE && w.color==ROBOT_RED && w.ticket==ticket);
    CHECK(Workflow_Reset(&w)==WF_BAD_STATE); CHECK(Workflow_SetMode(&w,SIM_MANUAL)==WF_BAD_STATE);
    CHECK(Workflow_Pause(&w,500)==WF_OK && w.elapsed_ms==400);
    Workflow_Poll(&w,20000); CHECK(w.elapsed_ms==400 && w.step==STEP_READY);
    CHECK(Workflow_Start(&w,ROBOT_GREEN,20000)==WF_BAD_STATE);
    CHECK(Workflow_Resume(&w,20000)==WF_OK);
    Workflow_Poll(&w,20599); CHECK(w.step==STEP_READY);
    Workflow_Poll(&w,20600); CHECK(w.step==STEP_APPROACH);
    CHECK(Workflow_Stop(&w)==WF_OK); ticket=w.ticket;
    Workflow_Poll(&w,50000); CHECK(w.state==WF_ABORTED && w.ticket==ticket);
    CHECK(Workflow_Resume(&w,50000)==WF_BAD_STATE); CHECK(Workflow_Reset(&w)==WF_OK);
    CHECK(Workflow_SetMode(&w,SIM_MANUAL)==WF_OK);
    CHECK(Workflow_Start(&w,ROBOT_BLUE,0)==WF_OK); ticket=w.ticket;
    CHECK(Workflow_Ack(&w,ticket-1,10)==WF_STALE_ACK && w.step==STEP_READY);
    CHECK(Workflow_Ack(&w,ticket,20)==WF_OK && w.step==STEP_APPROACH);
    CHECK(Workflow_Ack(&w,ticket,30)==WF_STALE_ACK && w.step==STEP_APPROACH);
    CHECK(Workflow_Pause(&w,40)==WF_OK);
    CHECK(Workflow_Ack(&w,w.ticket,50)==WF_BAD_STATE);
    CHECK(Workflow_Stop(&w)==WF_OK); CHECK(Workflow_Reset(&w)==WF_OK);
    CHECK(Workflow_Start(&w,ROBOT_GREEN,0)==WF_OK);
    CHECK(Workflow_Ack(&w,ticket,10)==WF_STALE_ACK);
    ticket=w.ticket; CHECK(Workflow_Ack(&w,ticket,3000)==WF_BAD_STATE && w.fault==FAULT_TIMEOUT);
    CHECK(Workflow_Start(&w,ROBOT_GREEN,3000)==WF_BAD_STATE); CHECK(Workflow_Reset(&w)==WF_OK);
    CHECK(Workflow_SetMode(&w,SIM_AUTO)==WF_OK); CHECK(Workflow_Start(&w,ROBOT_RED,0)==WF_OK);
    CHECK(Workflow_Stall(&w)==WF_OK); Workflow_Poll(&w,2999); CHECK(w.state==WF_RUNNING);
    Workflow_Poll(&w,3000); CHECK(w.state==WF_FAULT && w.fault==FAULT_TIMEOUT);
    CHECK(Workflow_Reset(&w)==WF_OK); CHECK(Workflow_Start(&w,ROBOT_BLUE,0)==WF_OK);
    CHECK(Workflow_Fail(&w)==WF_OK && w.fault==FAULT_SIMULATED);
    CHECK(Workflow_Reset(&w)==WF_OK); CHECK(Workflow_Start(&w,ROBOT_RED,0xfffffff0U)==WF_OK);
    Workflow_Poll(&w,0x10); CHECK(w.elapsed_ms==32);
    CHECK(Workflow_Pause(&w,0x20)==WF_OK); CHECK(Workflow_Resume(&w,0xffffff00U)==WF_OK);
    Workflow_Poll(&w,0x300); CHECK(w.step==STEP_APPROACH);
    Workflow_Poll(&w,UINT32_MAX); CHECK(w.state==WF_FAULT);
}
static void console_tests(void)
{
    RobotConsole c;
    RobotConsole_Init(&c,capture,0); captured[0]=0;
    CHECK(!RobotConsole_Command(&c,"ARM",0));
    CHECK(RobotConsole_Command(&c,"START RED extra",0) && c.flow.state==WF_IDLE);
    CHECK(RobotConsole_Command(&c,"START RED",0) && c.flow.state==WF_RUNNING);
    CHECK(RobotConsole_Command(&c,"START BLUE",0) && c.flow.color==ROBOT_RED);
    CHECK(RobotConsole_Command(&c,"STOP",0) && c.flow.state==WF_ABORTED);
    CHECK(RobotConsole_Command(&c,"RESET",0) && c.flow.state==WF_IDLE);
    CHECK(RobotConsole_Command(&c,"SIM MANUAL",0));
    CHECK(RobotConsole_Command(&c,"START GREEN",0));
    CHECK(RobotConsole_Command(&c,"ACK 4294967296",0) && c.flow.step==STEP_READY);
    CHECK(RobotConsole_Command(&c,"ACK -1",0) && c.flow.step==STEP_READY);
    CHECK(RobotConsole_Command(&c,"JOINTS",0)); CHECK(strstr(captured,"zero=-1")!=0);
    CHECK(RobotConsole_Command(&c,"POSES",0)); CHECK(strstr(captured,"raw=-1,-1,-1,-1")!=0);
    CHECK(strstr(captured,"no servo output")!=0);
    CHECK(strstr(captured,"ERR DRY STATE_REJECTED")!=0);
}
int main(void)
{
    config_tests(); flow_tests(); console_tests();
    printf("PASS: %u checks (joint validation, all color routes, pause/stop/reset, stale ACK, faults and wraparound)\n",checks);
    return 0;
}
