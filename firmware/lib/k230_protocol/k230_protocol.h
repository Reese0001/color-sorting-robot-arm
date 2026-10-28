/**
  ******************************************************************************
  * @file    k230_protocol.h
  * @brief   K230 视觉模块 → STM32 通信协议（接收端 + 抓取决策）
  * @version v1.1
  * @date    2026-10-28
  *
  * 帧格式（ASCII，115200 8N1）：
  *   @T,seq,pan,tilt,rx,ry,rp,gx,gy,gp,bx,by,bp*XX\r\n
  *
  * 使用三步：
  *   1. main() 里调一次 K230_Init()
  *   2. USART2_IRQHandler() 里收到字节就调 K230_IRQHandler(byte)
  *   3. 主循环里反复调 K230_Poll(now_ms)，然后 K230_PickTarget() 拿结果
  *
  * 依赖：stm32f10x.h + 标准库 string.h / stdlib.h
  *       不依赖 printf、不依赖浮点
  ******************************************************************************
  */

#ifndef __K230_PROTOCOL_H
#define __K230_PROTOCOL_H

#include "stm32f10x.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------- 可调参数 ------------------------- */

/* 帧最大长度。典型 40~55 字节，留 80 足够 */
#define K230_FRAME_MAX      80

/* 环形缓冲大小，必须是 2 的幂或能被整除即可，256 够用 */
#define K230_RB_SIZE        256

/* 视觉离线判定：超过这个毫秒数没收到合法帧，就认为 K230 掉线 */
#define K230_TIMEOUT_MS     500

/* 「分不出谁更大」的容差，单位百分比。
 * 95 表示：像素数在最大值的 95% 以上，就算和最大值并列，
 * 此时不按大小、改按 红 > 绿 > 蓝 的顺序选。
 * 想更倾向于选最大的，把它调高（如 99）；想更容易触发颜色顺序，调低（如 90）。 */
#define K230_TIE_RATIO      95

/* ------------------------- 数据结构 ------------------------- */

#define K230_SLOT_RED       0
#define K230_SLOT_GREEN     1
#define K230_SLOT_BLUE      2

/* 单个颜色的观测结果 */
typedef struct {
    int16_t  cx;        /* 中心 x，0~639，无效时为 -1 */
    int16_t  cy;        /* 中心 y，0~479，无效时为 -1 */
    uint32_t px;        /* 色块像素数，最大 640*480 = 307200，必须用 uint32 */
    uint8_t  valid;     /* 1=本帧看到且稳定，0=没看到 */
} K230_Slot;

/* 视觉模块整体状态 */
typedef struct {
    K230_Slot slot[3];      /* 索引用 K230_SLOT_RED / GREEN / BLUE */
    uint16_t  seq;          /* 最近一帧的序号，可用于检测丢帧 */
    uint8_t   pan;          /* 云台水平角 0~180 */
    uint8_t   tilt;         /* 云台俯仰角 0~180 */
    uint32_t  last_rx_ms;   /* 最近一次收到合法帧的时刻 */
    uint32_t  frames_ok;    /* 累计合法帧数 */
    uint32_t  frames_bad;   /* 累计被丢弃帧数（校验错/格式错/超长） */
} K230_Vision;

extern K230_Vision g_vision;

/* --------------------------- API --------------------------- */

/**
 * @brief  初始化。上电后调一次。
 */
void K230_Init(void);

/**
 * @brief  喂一个字节进去。在 USART2_IRQHandler 里调用。
 * @note   这个函数只做入队，不解析，执行时间几十个周期，可以放心放中断。
 */
void K230_IRQHandler(uint8_t byte);

/**
 * @brief  解析缓冲区里的数据。主循环里反复调用，越快越好（建议 5~10ms 一次）。
 * @param  now_ms 当前毫秒时间戳，用于超时判定。传自己的 millis()。
 */
void K230_Poll(uint32_t now_ms);

/**
 * @brief  视觉是否在线（K230_TIMEOUT_MS 内收到过合法帧）
 * @param  now_ms 当前毫秒时间戳
 * @retval 1=在线  0=掉线
 */
uint8_t K230_Online(uint32_t now_ms);

/**
 * @brief  按决策规则选一块木块来抓。
 * @param  now_ms 当前毫秒时间戳
 * @retval K230_SLOT_RED / GREEN / BLUE；-1 表示没有可抓目标
 *
 * 决策规则（按顺序判断）：
 *   1. 视觉掉线            -> 返回 -1
 *   2. 一种颜色有效        -> 直接选它
 *   3. 多种颜色有效        -> 选像素数最大的
 *   4. 像素数差距在 K230_TIE_RATIO 以内（分不出谁最大）
 *                          -> 按 红 > 绿 > 蓝 的顺序选
 *
 * 第 4 条存在的意义：两个木块大小接近时，像素数的正常波动会让
 * 「最大的那个」每帧跳变，机械臂就会左右摇摆。固定顺序能把这种
 * 抖动压住。
 */
int8_t K230_PickTarget(uint32_t now_ms);

/**
 * @brief  取颜色名字符串，调试打印用。
 */
const char *K230_ColorName(uint8_t slot_index);

#ifdef __cplusplus
}
#endif

#endif /* __K230_PROTOCOL_H */
