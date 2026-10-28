/**
  ******************************************************************************
  * @file    k230_protocol.c
  * @brief   K230 视觉模块 → STM32 通信协议（接收端 + 抓取决策）
  * @version v1.1
  * @date    2026-10-28
  *
  * 帧格式：@T,seq,pan,tilt,rx,ry,rp,gx,gy,gp,bx,by,bp*XX\r\n
  * 完整规范见仓库根目录下 docs/通信协议.md
  ******************************************************************************
  */

#include "k230_protocol.h"
#include <string.h>
#include <stdlib.h>

/* ------------------------- 全局状态 ------------------------- */

K230_Vision g_vision;

/* 中断 → 主循环 的环形缓冲 */
static volatile uint8_t  s_rb[K230_RB_SIZE];
static volatile uint16_t s_head = 0;    /* 中断写 */
static volatile uint16_t s_tail = 0;    /* 主循环读 */

/* 拼帧缓存 */
static char    s_line[K230_FRAME_MAX];
static uint8_t s_len = 0;
static uint8_t s_in_frame = 0;

/* ------------------------- 内部函数 ------------------------- */

static int8_t hex2(char c)
{
    if (c >= '0' && c <= '9') return (int8_t)(c - '0');
    if (c >= 'A' && c <= 'F') return (int8_t)(c - 'A' + 10);
    if (c >= 'a' && c <= 'f') return (int8_t)(c - 'a' + 10);
    return -1;
}

/**
 * @brief  解析一行完整帧（已去掉 @ 和 \r\n，内容形如 T,42,...,4300*52）
 */
static void k230_parse(char *s, uint8_t len)
{
    char    *star;
    char    *f[13];
    char    *p;
    uint8_t  body_len;
    uint8_t  calc;
    uint8_t  i;
    uint8_t  n;
    int8_t   hi;
    int8_t   lo;

    if (len < 4) {
        g_vision.frames_bad++;
        return;
    }

    star = strchr(s, '*');
    if (star == NULL) {
        g_vision.frames_bad++;
        return;
    }

    body_len = (uint8_t)(star - s);
    if (body_len < 2) {
        g_vision.frames_bad++;
        return;
    }

    /* 防止 star[1] star[2] 越界：'*' 后面必须还有两位 */
    if ((uint16_t)body_len + 3 > (uint16_t)len) {
        g_vision.frames_bad++;
        return;
    }

    /* ---- 校验：T 到 * 之前所有字节逐字节异或 ---- */
    calc = 0;
    for (i = 0; i < body_len; i++) {
        calc ^= (uint8_t)s[i];
    }

    hi = hex2(star[1]);
    lo = hex2(star[2]);
    if (hi < 0 || lo < 0) {
        g_vision.frames_bad++;
        return;
    }
    if (calc != (uint8_t)(((uint8_t)hi << 4) | (uint8_t)lo)) {
        g_vision.frames_bad++;
        return;
    }

    /* 截断，body 变成标准 C 字符串 */
    *star = '\0';

    /* ---- 逗号分割，必须正好 13 个字段 ---- */
    n = 0;
    p = s;
    while (n < 13) {
        f[n++] = p;
        p = strchr(p, ',');
        if (p == NULL) {
            break;
        }
        *p++ = '\0';
    }
    if (n != 13) {
        g_vision.frames_bad++;
        return;
    }
    if (f[0][0] != 'T') {
        g_vision.frames_bad++;
        return;
    }

    /* ---- 填字段 ---- */
    g_vision.seq  = (uint16_t)atoi(f[1]);
    g_vision.pan  = (uint8_t)atoi(f[2]);
    g_vision.tilt = (uint8_t)atoi(f[3]);

    for (i = 0; i < 3; i++) {
        int16_t  cx = (int16_t)atoi(f[4 + i * 3]);
        int16_t  cy = (int16_t)atoi(f[5 + i * 3]);
        uint32_t px = (uint32_t)atoi(f[6 + i * 3]);

        /* 范围检查：越界一律当无效，防止拿脏数据去驱动舵机 */
        if (cx < 0 || cx > 639 || cy < 0 || cy > 479 || px == 0) {
            g_vision.slot[i].valid = 0;
            g_vision.slot[i].cx    = -1;
            g_vision.slot[i].cy    = -1;
            g_vision.slot[i].px    = 0;
        } else {
            g_vision.slot[i].valid = 1;
            g_vision.slot[i].cx    = cx;
            g_vision.slot[i].cy    = cy;
            g_vision.slot[i].px    = px;
        }
    }

    g_vision.frames_ok++;
}

/* ------------------------- 对外接口 ------------------------- */

void K230_Init(void)
{
    memset(&g_vision, 0, sizeof(g_vision));
    g_vision.slot[0].cx = -1;
    g_vision.slot[1].cx = -1;
    g_vision.slot[2].cx = -1;
    g_vision.slot[0].cy = -1;
    g_vision.slot[1].cy = -1;
    g_vision.slot[2].cy = -1;

    s_head = 0;
    s_tail = 0;
    s_len  = 0;
    s_in_frame = 0;
}

void K230_IRQHandler(uint8_t byte)
{
    uint16_t next = (uint16_t)((s_head + 1) % K230_RB_SIZE);

    if (next != s_tail) {       /* 满了就丢新字节，不覆盖旧数据 */
        s_rb[s_head] = byte;
        s_head = next;
    }
}

void K230_Poll(uint32_t now_ms)
{
    char     c;
    uint16_t next;
    uint32_t ok_before;

    while (s_tail != s_head) {
        next = (uint16_t)((s_tail + 1) % K230_RB_SIZE);
        c = (char)s_rb[s_tail];
        s_tail = next;

        if (c == '@') {                 /* 帧头：无条件重来 */
            s_len = 0;
            s_in_frame = 1;
        } else if (s_in_frame) {
            if (c == '\n') {            /* 帧尾 */
                ok_before = g_vision.frames_ok;
                s_line[s_len] = '\0';
                k230_parse(s_line, s_len);
                /* 只有解析成功（frames_ok 增加）才刷新时间戳，
                 * 校验错的垃圾帧不能延长"在线"判定 */
                if (g_vision.frames_ok != ok_before) {
                    g_vision.last_rx_ms = now_ms;
                }
                s_in_frame = 0;
                s_len = 0;
            } else if (c != '\r') {
                if (s_len < K230_FRAME_MAX - 1) {
                    s_line[s_len++] = c;
                } else {                /* 超长：整帧丢弃，防止越界 */
                    s_in_frame = 0;
                    s_len = 0;
                    g_vision.frames_bad++;
                }
            }
        }
    }
}

uint8_t K230_Online(uint32_t now_ms)
{
    return (uint8_t)((uint32_t)(now_ms - g_vision.last_rx_ms) < K230_TIMEOUT_MS);
}

int8_t K230_PickTarget(uint32_t now_ms)
{
    uint8_t  i;
    uint8_t  n = 0;
    int8_t   only = -1;
    uint32_t max_px = 0;
    uint32_t floor_px;

    if (!K230_Online(now_ms)) {
        return -1;
    }

    /* 先扫一遍：数有效颜色个数，同时找最大像素数 */
    for (i = 0; i < 3; i++) {
        if (g_vision.slot[i].valid) {
            n++;
            only = (int8_t)i;
            if (g_vision.slot[i].px > max_px) {
                max_px = g_vision.slot[i].px;
            }
        }
    }

    if (n == 0) {
        return -1;              /* 一个都没有 */
    }
    if (n == 1) {
        return only;            /* 规则 2：只有一种颜色，直接选它 */
    }

    /* 规则 3 + 4：多种颜色时，取像素数达到最大值 K230_TIE_RATIO% 的，
     * 按 红 > 绿 > 蓝 的顺序第一个满足条件的胜出。
     * 这样既实现了「选最大的」，又能在大小接近时用固定顺序压住抖动。 */
    floor_px = max_px * K230_TIE_RATIO / 100;

    for (i = 0; i < 3; i++) {
        if (g_vision.slot[i].valid && g_vision.slot[i].px >= floor_px) {
            return (int8_t)i;
        }
    }

    return -1;
}

const char *K230_ColorName(uint8_t slot_index)
{
    switch (slot_index) {
    case K230_SLOT_RED:   return "RED";
    case K230_SLOT_GREEN: return "GREEN";
    case K230_SLOT_BLUE:  return "BLUE";
    default:              return "NONE";
    }
}
