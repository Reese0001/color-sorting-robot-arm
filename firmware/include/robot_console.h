#ifndef ROBOT_CONSOLE_H
#define ROBOT_CONSOLE_H
#include "robot_workflow.h"
typedef void (*RobotOutput)(void *context, const char *text);
typedef struct {
    RobotWorkflow flow;
    RobotOutput output;
    void *output_context;
} RobotConsole;
void RobotConsole_Init(RobotConsole *c, RobotOutput output, void *context);
/* Return 1 if command belongs to this console, including rejected commands. */
int RobotConsole_Command(RobotConsole *c, const char *line, uint32_t now);
int RobotConsole_IsCommand(const char *line);
void RobotConsole_Status(RobotConsole *c);
void RobotConsole_Help(RobotConsole *c);
#endif
