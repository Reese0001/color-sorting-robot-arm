#include "robot.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static uint32_t tick;
static unsigned writes,pwm_writes,stops,queries;
static uint16_t physical[3]={500,500,500};
static char last_observation[40];
static bool follow=true;
static unsigned min_yaw,max_yaw;
static bool reply_pending;
static uint32_t reply_at;
void hal_log(const char *p) {(void)p;}
void hal_camera(const char *p) {snprintf(last_observation,sizeof last_observation,"%s",p);}
void hal_pwm(uint16_t a,uint16_t b) {assert(a>=1200&&a<=1800&&b>=1200&&b<=1800);pwm_writes++;if(a<min_yaw)min_yaw=a;if(a>max_yaw)max_yaw=a;}
void hal_bus_write(const uint8_t *b,size_t n) {
    assert(!reply_pending || tick-reply_at>=20); // half-duplex quiet window
    assert(n==(size_t)b[3]+3);assert(b[0]==0x55&&b[1]==0x55);
    unsigned sum=0;for(size_t i=2;i<n;i++)sum+=b[i];assert((sum&255)==255);
    assert(b[2]>=1&&b[2]<=3);
    if(b[4]==1) {writes++;unsigned v=b[5]|(b[6]<<8);assert(v>=200&&v<=800);if(follow)physical[b[2]-1]=v;}
    else if(b[4]==12)stops++;
    else if(b[4]==28){queries++;reply_pending=true;reply_at=tick;}
    else assert(0);
}
static void feedback(unsigned id,unsigned value,bool valid) {
    uint8_t b[8]={0x55,0x55,(uint8_t)id,5,28,(uint8_t)value,(uint8_t)(value>>8),0};
    unsigned sum=0;for(int i=2;i<7;i++)sum+=b[i];b[7]=(uint8_t)~sum;
    if(!valid)b[7]^=1;
    for(unsigned i=0;i<8;i++)robot_bus(b[i],tick);
    reply_pending=false;
}
static void advance(unsigned ms,bool online) {
    for(unsigned elapsed=0;elapsed<ms;elapsed+=20) {
        tick+=20;if(online)for(unsigned id=1;id<=3;id++)feedback(id,physical[id-1],true);
        robot_tick(tick);
    }
}
static void command(const char *p) {while(*p)robot_console(*p++,tick);robot_console('\n',tick);}
static void reset(void) {
    tick=0;writes=0;pwm_writes=0;stops=0;queries=0;follow=true;
    min_yaw=65535;max_yaw=0;
    reply_pending=false;
    for(unsigned i=0;i<3;i++)physical[i]=500;
    last_observation[0]=0;robot_init();
}
static void arm(void) {advance(100,true);command("ARM 1500 1500");assert(robot_status().armed);}
static void setup_poses(void) {
    const char *names[]={"HOME","APPROACH","PICK","LIFT","RED","GREEN","BLUE"};
    char b[100];for(unsigned i=0;i<7;i++){snprintf(b,sizeof b,"POSE %s 1500 1500 500 500 500",names[i]);command(b);}
    command("POSE RED 1400 1500 450 500 500");
    command("POSE BLUE 1600 1500 550 500 500");
    command("GRIP 500 550");
}
static void vision(unsigned epoch,unsigned seq,unsigned cal,const char *color,bool stable,bool valid) {
    char b[120],line[128];snprintf(b,sizeof b,"V1,%u,%u,%u,%s,320,240,%u,%u,640",epoch,seq,cal,color,strcmp(color,"NONE")?1300:0,stable);
    unsigned sum=0;for(char *p=b;*p;p++)sum^=(unsigned char)*p;if(!valid)sum^=1;
    snprintf(line,sizeof line,"%s*%02X\n",b,sum);
    for(char *p=line;*p;p++)robot_camera(*p,tick);
}
static unsigned begin_auto(void) {
    arm();setup_poses();command("AUTO");advance(3500,true);
    assert(robot_status().automatic&&!robot_status().moving);
    return (unsigned)strtoul(last_observation+4,NULL,10);
}
int main(void) {
    reset();advance(500,true);assert(!writes&&!pwm_writes&&queries);
    command("JOG 1 1500 1000");assert(!robot_status().moving);
    command("ARM 99999 1500");assert(!robot_status().armed);
    arm();command("AUTO");assert(!robot_status().automatic); // no taught poses
    command("JOG 1 1600 1000 trailing");assert(!robot_status().moving);
    command("JOG 1 -1 1000");assert(!robot_status().moving);
    command("JOG 1 1600 1000");assert(robot_status().moving);
    advance(500,true);assert(robot_status().position.value[0]>1500&&robot_status().position.value[0]<1600);
    command("CLEAR");assert(robot_status().moving&&robot_status().armed);
    advance(600,true);assert(!robot_status().moving&&robot_status().position.value[0]==1600);
    command("JOG 3 600 1000");advance(200,true);command("STOP");unsigned before=writes;
    advance(1000,true);assert(writes==before&&stops==3&&robot_status().fault);
    command("ARM 1500 1500");assert(!robot_status().armed);
    command("CLEAR");command("ARM 1500 1500");assert(robot_status().armed);
    advance(800,false);assert(robot_status().fault);

    reset();for(unsigned i=1;i<=3;i++)feedback(i,500,false);
    command("ARM 1500 1500");assert(!robot_status().armed);
    arm();follow=false;command("JOG 3 700 500");advance(3200,true);
    assert(robot_status().fault); // live feedback, but mechanical target not reached

    reset();unsigned epoch=begin_auto();assert(epoch!=0);
    for(unsigned i=0;i<5;i++)vision(epoch,i,1,"RED",true,true);
    assert(!robot_status().cycle); // must see empty work area first
    vision(epoch,5,1,"NONE",false,true);
    for(unsigned i=6;i<9;i++)vision(epoch,i,0,"RED",true,true);
    assert(!robot_status().cycle); // uncalibrated
    for(unsigned i=9;i<12;i++)vision(epoch+1,i,1,"RED",true,true);
    assert(!robot_status().cycle); // wrong observation session
    for(unsigned i=12;i<15;i++)vision(epoch,i,1,"RED",true,false);
    assert(!robot_status().cycle); // checksum
    vision(epoch,20,1,"RED",true,true);
    vision(epoch,20,1,"RED",true,true);vision(epoch,20,1,"RED",true,true);
    assert(!robot_status().cycle); // replay
    for(unsigned i=21;i<24;i++){vision(epoch,i,1,"RED",true,true);advance(200,true);}
    assert(robot_status().cycle);advance(18500,true);
    assert(!robot_status().cycle&&!robot_status().fault&&robot_status().automatic);
    assert(min_yaw==1400&&max_yaw==1500); // selected RED destination
    unsigned epoch2=(unsigned)strtoul(last_observation+4,NULL,10);assert(epoch2!=epoch);
    for(unsigned i=30;i<36;i++)vision(epoch2,i,1,"RED",true,true);
    assert(!robot_status().cycle); // remaining block cannot retrigger without empty frame
    advance(5000,true);assert(robot_status().fault); // camera lost

    reset();arm();setup_poses();command("SORT BLUE");assert(robot_status().cycle);
    advance(18500,true);assert(!robot_status().cycle&&!robot_status().fault&&!robot_status().automatic);
    assert(min_yaw==1500&&max_yaw==1600); // selected BLUE destination
    reset();arm();setup_poses();command("SORT GREEN");advance(18500,true);
    assert(!robot_status().cycle&&!robot_status().fault&&min_yaw==1500&&max_yaw==1500);
    reset();arm();char large[200];memset(large,'A',sizeof large);for(unsigned i=0;i<sizeof large;i++)robot_console(large[i],tick);
    command("ARM 1500 1500");command("STOP");assert(robot_status().fault);
    puts("PASS: core motion, checksum, limits, startup, STOP/CLEAR, feedback failure, manual and automatic cycles, replay/session and camera timeout");
    return 0;
}
