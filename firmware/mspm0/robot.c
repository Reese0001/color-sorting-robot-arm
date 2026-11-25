#include "robot.h"
#include "robot_config.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static RobotStatus s;
static Pose poses[7], origin, destination;
static bool taught[7], grip_set, seen[3];
static const char *names[7] = {"HOME","APPROACH","PICK","LIFT","RED","GREEN","BLUE"};
static uint16_t feedback[3], grip_open, grip_closed;
static uint32_t feedback_at[3], now_ms, move_at, last_step, last_poll, observe_at;
static uint32_t move_ms=1800, active_duration, dwell_at, epoch, last_seq, vision_at;
static uint8_t poll_index, selected_color, stable_count;
static bool dwell, sequence_seen, fresh_clear;
static char linebuf[2][128];
static unsigned line_used[2];
static bool line_drop[2];
static uint8_t busbuf[32], bus_used;
static uint32_t bus_byte_at;
static bool bus_pending, bus_stopping;
static uint8_t pending_id;
static uint32_t query_at;

static uint32_t age(uint32_t at) { return now_ms-at; }
static void logtext(const char *p) { hal_log(p); }
static bool bounds(const Pose *p) {
    for(unsigned i=0;i<5;i++)
        if(p->value[i]<(i<2?PWM_MIN_US:BUS_MIN) || p->value[i]>(i<2?PWM_MAX_US:BUS_MAX)) return false;
    return true;
}
static void packet(uint8_t id,uint8_t cmd,const uint8_t *params,uint8_t n) {
    uint8_t b[16]={0x55,0x55,id,(uint8_t)(n+3),cmd};
    uint8_t sum=(uint8_t)(id+n+3+cmd);
    for(unsigned i=0;i<n;i++) { b[5+i]=params[i]; sum+=params[i]; }
    b[5+n]=(uint8_t)~sum;
    hal_bus_write(b,n+6);
}
static void write_pose(void) {
    hal_pwm(s.position.value[0],s.position.value[1]);
    for(unsigned i=0;i<3;i++) {
        uint16_t pos=s.position.value[i+2];
        uint8_t p[4]={(uint8_t)pos,(uint8_t)(pos>>8),40,0};
        packet(SERVO_IDS[i],1,p,4);
    }
}
static bool online(void) {
    for(unsigned i=0;i<3;i++) if(!seen[i] || age(feedback_at[i])>BUS_STALE_MS) return false;
    return true;
}
static bool reached(void) {
    if(!online()) return false;
    for(unsigned i=0;i<3;i++) if(abs((int)feedback[i]-(int)destination.value[i+2])>POSE_TOLERANCE) return false;
    return true;
}
static void observation(bool enable) {
    char b[40];
    if(enable) { epoch++; if(epoch==0) epoch=1; }
    snprintf(b,sizeof b,"OBS,%lu\n",(unsigned long)(enable?epoch:0));
    hal_camera(b);
    stable_count=0; sequence_seen=false; vision_at=now_ms;
    observe_at=now_ms; fresh_clear=false;
}
void robot_stop(const char *reason) {
    s.moving=false; s.automatic=false; s.cycle=false; s.fault=true; dwell=false;
    stable_count=0;
    memset(line_used,0,sizeof line_used);memset(line_drop,0,sizeof line_drop);
    /* Hold PWM; do not unload a load-bearing joint. Stop bus trajectories. */
    bus_stopping=true; /* Wait at most 20 ms for an in-flight half-duplex reply. */
    observation(false);
    char b[96]; snprintf(b,sizeof b,"STOP %s; holding; CLEAR then ARM to recover\n",reason); logtext(b);
    s.armed=false;
}
static bool start_move(Pose p,uint32_t duration) {
    if(!s.armed || s.fault || s.moving || !bounds(&p)) return false;
    origin=s.position; destination=p; move_at=now_ms; last_step=now_ms-20;
    active_duration=duration; s.moving=true; dwell=false;
    return true;
}
static bool ready(void) {
    if(!s.armed || s.fault || s.moving || !grip_set || !online()) return false;
    for(unsigned i=0;i<7;i++) if(!taught[i]) return false;
    return true;
}
static void next_stage(void) {
    static const uint8_t slots[8]={1,2,2,3,0,0,3,0};
    unsigned index=slots[s.stage];
    if(s.stage==4 || s.stage==5) index=selected_color+3;
    Pose p=poses[index];
    p.value[4]=(s.stage>=2 && s.stage<=4)?grip_closed:grip_open;
    if(!start_move(p,move_ms)) robot_stop("bad stage");
}
static void start_cycle(uint8_t color) {
    selected_color=color; s.cycle=true; s.stage=0; observation(false); next_stage();
}
static int slot(const char *p) { for(int i=0;i<7;i++) if(!strcmp(p,names[i])) return i; return -1; }
static bool number(const char *s0,unsigned long *v) {
    if(!s0 || !*s0) return false;
    unsigned long n=0;
    for(const char *p=s0;*p;p++) { if(*p<'0'||*p>'9'||n>429496729UL) return false;
        unsigned digit=(unsigned)(*p-'0'); if(n==429496729UL && digit>5) return false; n=n*10+digit; }
    *v=n; return true;
}
static unsigned split(char *s0,char delimiter,char **out,unsigned max) {
    unsigned n=0;
    for(char *p=s0;;) {
        if(n==max || !*p) return 0;
        out[n++]=p;
        char *q=strchr(p,delimiter); if(!q) return n;
        *q=0; p=q+1;
    }
}
static void console_line(char *line) {
    char *a[10]; unsigned n=split(line,' ',a,10); unsigned long v[8]={0};
    if(!n) { logtext("ERR syntax\n"); return; }
    if(n==1 && !strcmp(a[0],"STOP")) { robot_stop("console"); return; }
    if(n==1 && !strcmp(a[0],"CLEAR")) {
        if(s.moving||s.automatic||s.cycle) {logtext("ERR STOP before CLEAR\n");return;}
        s.fault=false; s.armed=false; logtext("OK disarmed; ARM requires fresh bus positions\n"); return;
    }
    if(n==1 && !strcmp(a[0],"HELP")) {
        logtext("STATUS | ARM pwm1 pwm2 | JOG joint value ms | TEACH name | POSE name p1 p2 b1 b2 grip | GRIP open closed | GOTO name | AUTO | SORT RED/GREEN/BLUE | STOP | CLEAR | DUMP\n"); return;
    }
    if(n==1 && !strcmp(a[0],"STATUS")) {
        char b[180]; snprintf(b,sizeof b,"STATE armed=%u moving=%u auto=%u cycle=%u fault=%u pwm=%u,%u bus=%u,%u,%u online=%u epoch=%lu\n",s.armed,s.moving,s.automatic,s.cycle,s.fault,s.position.value[0],s.position.value[1],feedback[0],feedback[1],feedback[2],online(),(unsigned long)epoch); logtext(b); return;
    }
    if(n==1 && !strcmp(a[0],"DUMP")) {
        char b[100];
        for(unsigned i=0;i<7;i++) if(taught[i]) {
            snprintf(b,sizeof b,"POSE %s %u %u %u %u %u\n",names[i],poses[i].value[0],poses[i].value[1],poses[i].value[2],poses[i].value[3],poses[i].value[4]); logtext(b);
        }
        if(grip_set) { snprintf(b,sizeof b,"GRIP %u %u\n",grip_open,grip_closed); logtext(b); }
        return;
    }
    if(s.fault || s.moving || s.cycle || s.automatic) { logtext("ERR busy/fault; STOP first\n"); return; }
    if(n==3 && !strcmp(a[0],"ARM") && number(a[1],&v[0]) && number(a[2],&v[1])) {
        if(s.armed || bus_stopping || !online() || v[0]>65535 || v[1]>65535) { logtext("ERR ARM requires disarmed and bus online\n"); return; }
        Pose p={{(uint16_t)v[0],(uint16_t)v[1],feedback[0],feedback[1],feedback[2]}};
        if(!bounds(&p)) { logtext("ERR limits\n"); return; }
        s.position=p; s.armed=true;
        /* Explicit operator supplied current PWM pose; first enable may move PWM servos. */
        hal_pwm(p.value[0],p.value[1]); logtext("OK ARM\n"); return;
    }
    if(n==4 && !strcmp(a[0],"JOG") && number(a[1],&v[0]) && number(a[2],&v[1]) && number(a[3],&v[2])) {
        if(v[0]<1||v[0]>5||v[1]>65535||v[2]<500||v[2]>10000) { logtext("ERR range\n"); return; }
        Pose p=s.position; p.value[v[0]-1]=(uint16_t)v[1];
        logtext(start_move(p,v[2])?"OK moving\n":"ERR disarmed/limits\n"); return;
    }
    if(n==2 && !strcmp(a[0],"TEACH")) {
        int i=slot(a[1]); if(i<0 || !s.armed || !online()) { logtext("ERR TEACH\n"); return; }
        poses[i]=s.position;
        for(unsigned j=0;j<3;j++) poses[i].value[j+2]=feedback[j];
        if(!bounds(&poses[i])) { logtext("ERR limits\n"); return; }
        taught[i]=true; logtext("OK taught in RAM; DUMP to retain\n"); return;
    }
    if(n==7 && !strcmp(a[0],"POSE")) {
        int i=slot(a[1]); Pose p;
        if(i<0) { logtext("ERR pose name\n"); return; }
        for(unsigned j=0;j<5;j++) { if(!number(a[j+2],&v[j]) || v[j]>65535) { logtext("ERR number\n"); return; } p.value[j]=(uint16_t)v[j]; }
        if(!bounds(&p)) { logtext("ERR limits\n"); return; }
        poses[i]=p; taught[i]=true; logtext("OK pose loaded, no motion\n"); return;
    }
    if(n==3 && !strcmp(a[0],"GRIP") && number(a[1],&v[0]) && number(a[2],&v[1])) {
        if(v[0]<BUS_MIN||v[0]>BUS_MAX||v[1]<BUS_MIN||v[1]>BUS_MAX||v[0]==v[1]) { logtext("ERR grip limits\n"); return; }
        grip_open=v[0];grip_closed=v[1];grip_set=true;logtext("OK grip configured\n");return;
    }
    if(n==2 && !strcmp(a[0],"GOTO")) {
        int i=slot(a[1]); logtext(i>=0 && taught[i] && start_move(poses[i],move_ms)?"OK moving\n":"ERR pose/disarmed\n");return;
    }
    if(n==1 && !strcmp(a[0],"AUTO") && ready()) {
        s.automatic=true; Pose p=poses[0];p.value[4]=grip_open;
        if(!start_move(p,move_ms)) { robot_stop("home failed"); return; }
        observation(false); logtext("OK homing; remove target then present it\n");return;
    }
    if(n==2 && !strcmp(a[0],"SORT") && ready()) {
        int c=slot(a[1]);if(c>=4) { start_cycle((uint8_t)(c-3)); logtext("OK manual cycle\n");return; }
    }
    logtext("ERR command or prerequisites; HELP\n");
}
static void camera_line(char *line) {
    char *star=strchr(line,'*');
    if(!star || strlen(star+1)!=2) {stable_count=0;return;}
    uint8_t sum=0; for(char *p=line;p<star;p++) sum^=(uint8_t)*p;
    char expected[3];snprintf(expected,sizeof expected,"%02X",sum);
    if(strcmp(expected,star+1)) {stable_count=0;return;}
    *star=0; char *a[10];unsigned n=split(line,',',a,10);unsigned long v[8];
    if(n!=10 || strcmp(a[0],"V1")) {stable_count=0;return;}
    /* V1,epoch,seq,cal,color,x,y,pixels,stable,width; width must be 640. */
    unsigned indices[8]={1,2,3,5,6,7,8,9};
    for(unsigned i=0;i<8;i++) if(!number(a[indices[i]],&v[i])) {stable_count=0;return;}
    if(!s.automatic||s.moving||s.cycle||age(observe_at)<OBSERVE_SETTLE_MS||v[0]!=epoch) return;
    if(v[2]>1||v[3]>=640||v[4]>=480||v[5]>307200||v[6]>1||v[7]!=640) {stable_count=0;return;}
    uint32_t seq=(uint32_t)v[1];
    if(sequence_seen && (seq-last_seq==0 || seq-last_seq>=0x80000000U)) {stable_count=0;return;}
    if(age(vision_at)>VISION_STALE_MS) stable_count=0;
    last_seq=seq; sequence_seen=true; vision_at=now_ms;
    if(!strcmp(a[4],"NONE")) {
        stable_count=0; if(v[2]==1 && v[5]==0 && v[6]==0) fresh_clear=true;return;
    }
    int color=slot(a[4]);
    if(!fresh_clear||v[2]!=1||v[6]!=1||color<4||v[5]<500 || abs((int)v[3]-PICK_X)>PICK_TOL_X || abs((int)v[4]-PICK_Y)>PICK_TOL_Y) {stable_count=0;return;}
    if(selected_color!=(uint8_t)(color-3)) stable_count=0;
    selected_color=(uint8_t)(color-3);
    if(++stable_count>=3 && ready()) start_cycle(selected_color);
}
static void feed(unsigned channel,char byte,uint32_t now) {
    now_ms=now;
    if(byte=='\r') return;
    if(byte=='\n') {
        if(!line_drop[channel] && line_used[channel]) {
            linebuf[channel][line_used[channel]]=0;
            if(channel==0) console_line(linebuf[channel]);else camera_line(linebuf[channel]);
        }
        line_used[channel]=0;line_drop[channel]=false;return;
    }
    if((unsigned char)byte<32 || (unsigned char)byte>126 || line_used[channel]>=sizeof linebuf[channel]-1) {
        line_drop[channel]=true;if(channel==1)stable_count=0;return;
    }
    if(!line_drop[channel]) linebuf[channel][line_used[channel]++]=byte;
}
void robot_console(char b,uint32_t now) {feed(0,b,now);}
void robot_camera(char b,uint32_t now) {feed(1,b,now);}
void robot_bus(uint8_t b,uint32_t now) {
    now_ms=now;
    if((uint32_t)(now-bus_byte_at)>20) bus_used=0;
    bus_byte_at=now;
    if(bus_used<2) { if(b==0x55) busbuf[bus_used++]=b;else bus_used=0;return; }
    busbuf[bus_used++]=b;
    if(bus_used==4 && (b<3 || b>sizeof busbuf-3)) {bus_used=0;return;}
    if(bus_used>=4 && bus_used==busbuf[3]+3) {
        uint8_t sum=0;for(unsigned i=2;i<bus_used;i++)sum+=busbuf[i];
        if(sum==255 && busbuf[3]==5 && busbuf[4]==28) {
            uint16_t value=(uint16_t)(busbuf[5]|((uint16_t)busbuf[6]<<8));
            for(unsigned i=0;i<3;i++) if(busbuf[2]==SERVO_IDS[i] && value<=1000) {
                feedback[i]=value;feedback_at[i]=now;seen[i]=true;
                if(bus_pending && pending_id==busbuf[2])bus_pending=false;
            }
        }
        bus_used=0;
    }
}
void robot_init(void) {
    memset(&s,0,sizeof s);memset(taught,0,sizeof taught);memset(seen,0,sizeof seen);
    memset(line_used,0,sizeof line_used);memset(line_drop,0,sizeof line_drop);
    grip_set=false;bus_used=0;now_ms=0;epoch=0;last_poll=0;poll_index=0;dwell=false;
    sequence_seen=false;fresh_clear=false;stable_count=0;
    bus_pending=false;bus_stopping=false;
    logtext("ROBOT1 V1 DISARMED. HELP. No startup motion.\n");
}
RobotStatus robot_status(void) {return s;}
void robot_tick(uint32_t now) {
    now_ms=now;
    if(s.armed && !online()) {robot_stop("bus feedback timeout");return;}
    if(bus_pending && age(query_at)>=20)bus_pending=false;
    if(bus_pending)return;
    if(bus_stopping) {
        for(unsigned i=0;i<3;i++)packet(SERVO_IDS[i],12,NULL,0);
        bus_stopping=false;return;
    }
    if(age(last_poll)>=80) {
        last_poll=now;query_at=now;pending_id=SERVO_IDS[poll_index];bus_pending=true;
        packet(pending_id,28,NULL,0);poll_index=(poll_index+1)%3;
        return; /* Do not transmit motion packets while the servo is replying. */
    }
    if(s.moving) {
        uint32_t elapsed=age(move_at);
        if(age(last_step)>=20) {
            last_step=now;
            float t=elapsed>=active_duration?1.0f:(float)elapsed/(float)active_duration;
            float eased=t*t*(3.0f-2.0f*t);
            for(unsigned i=0;i<5;i++)s.position.value[i]=(uint16_t)(origin.value[i]+((int)destination.value[i]-(int)origin.value[i])*eased+0.5f);
            write_pose();
        }
        if(elapsed>=active_duration && reached()) {
            s.moving=false;logtext("DONE motion\n");
            if(s.cycle) {dwell=true;dwell_at=now;}
            else if(s.automatic) observation(true);
        } else if(elapsed>active_duration+2500) robot_stop("servo did not reach target");
    } else if(s.cycle && dwell && age(dwell_at)>=400) {
        dwell=false;
        if(++s.stage<8) next_stage();
        else {s.cycle=false;logtext("DONE cycle\n");if(s.automatic)observation(true);}
    }
    if(s.automatic && !s.moving && !s.cycle && age(observe_at)>OBSERVE_SETTLE_MS+3000 && age(vision_at)>3000) robot_stop("vision link timeout");
}
