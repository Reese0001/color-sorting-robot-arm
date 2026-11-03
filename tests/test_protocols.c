#include "k230_protocol.h"
#include "hiwonder_bus.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { printf("FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static void raw(const char *s, unsigned long now)
{ while (*s) K230_IRQHandler((uint8_t)*s++); K230_Poll((uint32_t)now); }
static void frame(const char *body, uint32_t now)
{
    char s[240]; uint8_t sum=0; const char *p=body;
    while(*p) sum^=(uint8_t)*p++;
    snprintf(s,sizeof(s),"@%s*%02X\r\n",body,(unsigned)sum); raw(s,now);
}
int main(void)
{
    const char *valid="T,42,90,90,320,240,5120,180,260,4800,150,300,4300";
    const char *invalid[]={
      "TX,42,90,90,320,240,5120,-1,-1,0,-1,-1,0",
      "T,65536,90,90,320,240,5120,-1,-1,0,-1,-1,0",
      "T,42,181,90,320,240,5120,-1,-1,0,-1,-1,0",
      "T,42,90,-1,320,240,5120,-1,-1,0,-1,-1,0",
      "T,42,90,90,640,240,5120,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,480,5120,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,-1,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,307201,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,999999999999,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,5junk,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,,-1,-1,0,-1,-1,0",
      "T,42,90,90,-1,240,0,-1,-1,0,-1,-1,0",
      "T,42,90,90,320,240,0,-1,-1,0,-1,-1,0",
      "T,42,90,90,-1,-1,0,-1,-1,0,-1,-1,0,7",
      "T,42,90,90,-1,-1,0,-1,-1,0,-1,-1",
      "T,42,9\r0,90,-1,-1,0,-1,-1,0,-1,-1,0"};
    uint8_t b[BUS_PACKET_MAX], n; unsigned i; BusParser parser;
    const uint8_t move[]={0x55,0x55,1,7,1,0xf4,1,0xe8,3,0x16};
    memset(&parser,0,sizeof(parser));
    K230_Init(); CHECK(!K230_Online(0)); CHECK(K230_PickTarget(0)==-1);
    frame(valid,100); CHECK(g_vision.frames_ok==1); CHECK(g_vision.seq==42);
    CHECK(K230_PickTarget(100)==0); CHECK(K230_Online(599)); CHECK(!K230_Online(600));
    for(i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        frame(invalid[i],200); CHECK(g_vision.frames_ok==1); CHECK(g_vision.seq==42);
    }
    CHECK(g_vision.frames_bad==sizeof(invalid)/sizeof(invalid[0]));
    raw("@T,42,90,90,320,240,5120,180,260,4800,150,300,4300*52junk\n",200);
    CHECK(g_vision.frames_ok==1);
    raw("@T,42,90,90,320,240,5120,180,260,4800,150,300,4300*00\n",200);
    CHECK(g_vision.last_rx_ms==100);
    frame("T,65535,0,180,639,479,307200,-1,-1,0,-1,-1,0",300);
    CHECK(g_vision.slot[0].px==307200); CHECK(g_vision.seq==65535);
    frame("T,0,90,90,-1,-1,0,-1,-1,0,-1,-1,0",301);
    CHECK(K230_PickTarget(301)==-1); CHECK(!g_vision.slot[0].valid);
    frame("T,1,90,90,0,0,95,1,1,100,-1,-1,0",302); CHECK(K230_PickTarget(302)==0);
    frame("T,2,90,90,0,0,94,1,1,100,-1,-1,0",303); CHECK(K230_PickTarget(303)==1);
    raw("junk@partial@",304); frame(valid,304); CHECK(K230_Online(304));
    for(i=0;i<400;++i) K230_IRQHandler('x'); K230_Poll(305);
    CHECK(g_vision.rx_dropped>0); CHECK(!K230_Online(305));
    frame(valid,306); CHECK(K230_Online(306)); K230_RxError(); K230_Poll(307); CHECK(!K230_Online(307));
    K230_Init(); frame(valid,0xfffffff0U); CHECK(K230_Online(10)); CHECK(!K230_Online(600));
    K230_Poll(600); CHECK(!K230_Online(0xfffffff1U));
    n=Bus_Move(b,1,500,1000); CHECK(n==10); CHECK(!memcmp(b,move,10));
    CHECK(!Bus_Move(b,1,1001,1000)); CHECK(!Bus_Move(b,1,500,30001)); CHECK(!Bus_Move(b,254,500,1000));
    n=Bus_Build(b,1,BUS_POS_READ,0,0); CHECK(n==6 && b[5]==0xdf);
    for(i=0;i<n;++i) Bus_Feed(&parser,b[i],100); CHECK(parser.good==1);
    b[5]^=1; for(i=0;i<n;++i) Bus_Feed(&parser,b[i],101); CHECK(parser.bad==1);
    b[5]^=1; for(i=0;i<3;++i) Bus_Feed(&parser,b[i],102);
    for(i=0;i<n;++i) Bus_Feed(&parser,b[i],200); CHECK(parser.good==2);
    printf("PASS: %u checks (K230 validation/timeout/resync and bus packets)\n",checks);
    return 0;
}
