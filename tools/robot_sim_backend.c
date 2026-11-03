/* Desktop-only adapter: compiles the SAME workflow and command parser as Keil. */
#include "robot_console.h"
#include <stdio.h>
#include <string.h>
#define EXPORT __declspec(dllexport)
#define LOG_LINES 128U
static RobotConsole console;
static char logs[LOG_LINES][240], status_text[600];
static unsigned head, tail, lost;
static void output(void *unused, const char *text)
{
    unsigned next=(head+1U)%LOG_LINES;
    (void)unused;
    if(next==tail) { tail=(tail+1U)%LOG_LINES; ++lost; }
    snprintf(logs[head],sizeof(logs[head]),"%s",text); head=next;
}
EXPORT void Sim_Init(void)
{
    head=tail=lost=0;
    RobotConsole_Init(&console,output,0);
    output(0,"Desktop dry run: same C workflow as Keil; no serial ports or motor drivers loaded.\r\n");
}
EXPORT int Sim_Command(const char *command, uint32_t now)
{
    int handled;
    if (!command || strlen(command)>63) { output(0,"ERR command length\r\n"); return 0; }
    if (!strcmp(command,"HELP")) { RobotConsole_Help(&console); return 1; }
    handled=RobotConsole_Command(&console,command,now);
    if(!handled) output(0,"ERR unknown dry run command\r\n");
    return handled;
}
EXPORT void Sim_Poll(uint32_t now) { Workflow_Poll(&console.flow,now); }
EXPORT const char *Sim_Status(void)
{
    RobotWorkflow *w=&console.flow;
    snprintf(status_text,sizeof(status_text),
        "{\"state\":\"%s\",\"step\":%u,\"color\":\"%s\",\"bin\":\"%s\",\"elapsed_ms\":%lu,"
        "\"ticket\":%lu,\"mode\":\"%s\",\"fault\":\"%s\",\"pose\":\"%s\",\"config_issues\":%lu,\"lost_logs\":%u}",
        Workflow_StateName(w->state),(unsigned)w->step,Robot_ColorName(w->color),Robot_BinName(w->color),
        (unsigned long)w->elapsed_ms,(unsigned long)w->ticket,w->mode==SIM_AUTO?"AUTO":"MANUAL",
        Workflow_FaultName(w->fault),g_robot_poses[Workflow_Pose(w)].name,
        (unsigned long)Robot_JointIssues(g_robot_joints),lost);
    return status_text;
}
EXPORT const char *Sim_NextLog(void)
{
    const char *s;
    if(head==tail) return 0;
    s=logs[tail]; tail=(tail+1U)%LOG_LINES; return s;
}
