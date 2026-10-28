# ============================================================
# 亚博 K230 云台扫描 —— 自动寻找红/绿/蓝木块并上报
# 文件名：05_scan_color.py
#
# 工作方式：
#   云台从左扫到右（可选多行），每停一个位置等画面稳住再检测。
#   一旦找到木块，云台就停在那个角度，持续把
#   「颜色 + 图像坐标 + 云台角度」发给 STM32。
#   木块被夹走（画面里连续消失）或超时后，自动继续扫描。
#
# 前置条件：
#   1. 已用 03_auto_calibrate.py 标定好阈值，粘到下面 COLOR_THRESHOLDS
#   2. 已用 04_servo_probe.py 测出云台舵机的 GPIO，填到 PAN_GPIO
#   3. 串口线接好后再把 UART_ENABLED 改成 True
#
# 协议（115200 8N1，ASCII，@ 开头 *XX 校验，CRLF 结尾）：
#   @C,seq,valid,color,cx,cy,pixels,pan,tilt*XX
#   比 02 版多了 pan / tilt 两个字段 —— 云台转了以后，
#   光有像素坐标是没用的，必须知道当时云台在哪个角度。
# ============================================================

import os
import sys
import time
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager
from machine import FPIOA, PWM, UART

# ================= 用户配置 =================
WIDTH = 640
HEIGHT = 480
USE_LCD = True

# ---- 云台舵机（用 04_servo_probe.py 测出来的编号）----
PAN_GPIO = 42           # 水平舵机
PAN_CH = 0
TILT_GPIO = 43          # 垂直舵机
TILT_CH = 1
HAS_TILT = True         # 只有一个舵机就改成 False

# ---- 扫描范围（0~180 度，先小范围试，别一上来就怼满）----
PAN_MIN = 40
PAN_MAX = 140
PAN_STEP = 16
TILT_CENTER = 95        # 垂直中位，镜头大致对着桌面
TILT_STEP = 12
TILT_ROWS = 1           # 1=只扫一行；3=扫三行覆盖一片区域
TILT_MIN = 78           # TILT_ROWS>1 时才用
TILT_MAX = 118

# ---- 节奏 ----
SETTLE_MS = 420         # 云台停下后等画面稳住的时间
SCAN_SAMPLE_MS = 240    # 每个位置持续检测的时长
LOCK_TIMEOUT_MS = 8000  # 锁定后最多保持多久就重新扫描
LOST_FRAMES = 12        # 连续多少帧看不到目标算"被拿走了"
SEND_INTERVAL_MS = 100  # 上报间隔

# ---- 串口 ----
UART_ENABLED = False    # 接线核对无误后再改 True
BAUDRATE = 115200
TX_PIN = 9              # 亚博 K230 通信口 UART1，实物需核对
RX_PIN = 10

# ---- 颜色阈值：把 03 标定输出的整段粘到这里 ----
COLOR_THRESHOLDS = (
    (15, 95, 20, 127, 5, 127),      # 红 ID 1
    (15, 95, -90, -12, -10, 90),    # 绿 ID 2
    (10, 90, -40, 90, -128, -20),   # 蓝 ID 3
)
COLOR_NAMES = ("RED", "GREEN", "BLUE")
DRAW_RGB = ((255, 40, 40), (40, 220, 40), (60, 140, 255))

# ---- 过滤 ----
MIN_PIXELS = 400        # 小于这个像素数当噪声
MIN_AREA = 500          # 外接矩形最小面积
MIN_FILL = 0.35         # 像素数/外接矩形面积，太低说明是细长条
ROI = (0, 0, WIDTH, HEIGHT)


# ================= 工具 =================
def angle_to_ns(angle):
    if angle < 0:
        angle = 0
    if angle > 180:
        angle = 180
    return int(500000 + angle * 2000000 // 180)


def build_stops(lo, hi, step):
    stops = []
    v = lo
    while v <= hi:
        stops.append(v)
        v += step
    if stops and stops[-1] != hi:
        stops.append(hi)
    return stops


def make_packet(seq, valid, color_id, cx, cy, pixels, pan, tilt):
    body = "C,%d,%d,%d,%d,%d,%d,%d,%d" % (
        seq, valid, color_id, cx, cy, pixels, pan, tilt)
    checksum = 0
    for v in body.encode("ascii"):
        checksum ^= v
    return ("@%s*%02X\r\n" % (body, checksum)).encode("ascii")


def detect_best(img):
    """三色全检，返回 (像素数, 颜色ID, blob) 或 None"""
    best = None
    for i in range(3):
        blobs = img.find_blobs([COLOR_THRESHOLDS[i]], roi=ROI,
                               pixels_threshold=MIN_PIXELS,
                               area_threshold=MIN_AREA,
                               merge=True)
        for b in blobs:
            px = b.pixels()
            box = b.w() * b.h()
            if box <= 0 or px < MIN_FILL * box:
                continue
            if best is None or px > best[0]:
                best = (px, i + 1, b)
    return best


def draw_hud(img, l1, l2, l3):
    img.draw_rectangle((0, 0, WIDTH, 92), color=(0, 0, 0), fill=True)
    img.draw_string_advanced(8, 4, 24, l1, color=(255, 255, 255))
    img.draw_string_advanced(8, 34, 20, l2, color=(255, 240, 60))
    img.draw_string_advanced(8, 60, 20, l3, color=(150, 220, 255))


# ================= 主程序 =================
def main():
    sensor = None
    uart = None
    fpioa = None
    pwm_pan = None
    pwm_tilt = None
    seq = 0

    pan_stops = build_stops(PAN_MIN, PAN_MAX, PAN_STEP)
    if TILT_ROWS > 1:
        tilt_stops = build_stops(TILT_MIN, TILT_MAX, TILT_STEP)
    else:
        tilt_stops = [TILT_CENTER]

    print("")
    print("=" * 56)
    print("  K230 云台扫描找木块")
    print("=" * 56)
    print("  PAN  %d..%d step %d -> %d 个位置" % (PAN_MIN, PAN_MAX, PAN_STEP, len(pan_stops)))
    print("  TILT %s" % (tilt_stops,))
    print("  单行耗时约 %.1f 秒" % (len(pan_stops) * (SETTLE_MS + SCAN_SAMPLE_MS) / 1000.0))
    print("=" * 56)
    print("")

    try:
        # ---- 串口 ----
        if UART_ENABLED:
            fpioa = FPIOA()
            fpioa.set_function(TX_PIN, FPIOA.UART1_TXD, ie=0, oe=1)
            fpioa.set_function(RX_PIN, FPIOA.UART1_RXD, ie=1, oe=0)
            uart = UART(UART.UART1, baudrate=BAUDRATE, bits=UART.EIGHTBITS,
                        parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
            print("UART1 on GPIO%d(TX)/GPIO%d(RX) @ %d" % (TX_PIN, RX_PIN, BAUDRATE))

        # ---- 云台舵机 ----
        fpioa2 = FPIOA()
        fpioa2.set_function(PAN_GPIO, getattr(FPIOA, "PWM%d" % PAN_CH), ie=0, oe=1)
        pwm_pan = PWM(PAN_CH, freq=50, duty_ns=angle_to_ns(pan_stops[0]), enable=True)
        if HAS_TILT:
            fpioa2.set_function(TILT_GPIO, getattr(FPIOA, "PWM%d" % TILT_CH), ie=0, oe=1)
            pwm_tilt = PWM(TILT_CH, freq=50, duty_ns=angle_to_ns(tilt_stops[0]), enable=True)
        time.sleep_ms(600)

        # ---- 相机 ----
        sensor = Sensor(width=WIDTH, height=HEIGHT)
        sensor.reset()
        sensor.set_framesize(width=WIDTH, height=HEIGHT)
        sensor.set_pixformat(Sensor.RGB565)
        if USE_LCD:
            Display.init(Display.ST7701, to_ide=True)
        else:
            Display.init(Display.VIRT, width=WIDTH, height=HEIGHT, fps=30)
        MediaManager.init()
        sensor.run()
        for _ in range(8):
            sensor.snapshot()
        time.sleep_ms(300)

        # ---- 状态 ----
        state = "scan"
        pan_i = 0
        tilt_i = 0
        pan_dir = 1
        t_move = time.ticks_ms()
        cur_pan = pan_stops[0]
        cur_tilt = tilt_stops[0]
        pwm_pan.duty_ns(angle_to_ns(cur_pan))
        if pwm_tilt:
            pwm_tilt.duty_ns(angle_to_ns(cur_tilt))
        target = None
        t_lock = 0
        lost = 0
        last_send = 0
        hit_count = 0
        best_here = None

        while True:
            os.exitpoint()
            img = sensor.snapshot()
            now = time.ticks_ms()

            # ================== 扫描 ==================
            if state == "scan":
                dt = time.ticks_diff(now, t_move)

                if dt < SETTLE_MS:
                    # 云台刚移动，画面还在晃，不检测
                    hit_count = 0
                    best_here = None
                elif dt < SETTLE_MS + SCAN_SAMPLE_MS:
                    # 稳定窗口内持续检测，命中次数够了才认
                    hit = detect_best(img)
                    if hit is not None:
                        hit_count += 1
                        best_here = hit
                        img.draw_rectangle(hit[2].rect(), color=DRAW_RGB[hit[1] - 1], thickness=2)
                    if hit_count >= 2 and best_here is not None:
                        target = best_here
                        state = "locked"
                        t_lock = now
                        lost = 0
                        last_send = 0
                        print("[LOCK] %s  pan=%d tilt=%d  cx=%d cy=%d  %d px"
                              % (COLOR_NAMES[target[1] - 1], cur_pan, cur_tilt,
                                 target[2].cx(), target[2].cy(), target[0]))
                else:
                    # 换下一个位置
                    hit_count = 0
                    best_here = None
                    pan_i += pan_dir
                    if pan_i >= len(pan_stops):
                        pan_i = len(pan_stops) - 2
                        pan_dir = -1
                    elif pan_i < 0:
                        pan_i = 1
                        pan_dir = 1
                    # 一行扫完，换下一行
                    if pan_i == 0 or pan_i == len(pan_stops) - 1:
                        if len(tilt_stops) > 1:
                            tilt_i = (tilt_i + 1) % len(tilt_stops)
                            cur_tilt = tilt_stops[tilt_i]
                            if pwm_tilt:
                                pwm_tilt.duty_ns(angle_to_ns(cur_tilt))
                    cur_pan = pan_stops[pan_i]
                    pwm_pan.duty_ns(angle_to_ns(cur_pan))
                    t_move = now
                    print("[SCAN] pan=%d tilt=%d" % (cur_pan, cur_tilt))

                draw_hud(img,
                         "SCANNING  pan=%d tilt=%d" % (cur_pan, cur_tilt),
                         "pos %d/%d  hits %d" % (pan_i + 1, len(pan_stops), hit_count),
                         "searching red/green/blue blocks")

            # ================== 锁定 ==================
            else:
                hit = detect_best(img)
                if hit is not None:
                    # 同色才算同一目标
                    if hit[1] == target[1]:
                        target = hit
                        lost = 0
                    else:
                        lost += 1
                else:
                    lost += 1

                b = target[2]
                img.draw_rectangle(b.rect(), color=DRAW_RGB[target[1] - 1], thickness=3)
                img.draw_cross(b.cx(), b.cy(), color=(255, 255, 255), size=18, thickness=2)
                draw_hud(img,
                         "LOCKED: %s" % COLOR_NAMES[target[1] - 1],
                         "cx=%d cy=%d  %d px" % (b.cx(), b.cy(), target[0]),
                         "pan=%d tilt=%d  lost %d/%d" % (cur_pan, cur_tilt, lost, LOST_FRAMES))

                if lost >= LOST_FRAMES:
                    print("[UNLOCK] 目标消失，继续扫描")
                    state = "scan"
                    t_move = time.ticks_ms() - SETTLE_MS - SCAN_SAMPLE_MS + 100
                    target = None
                elif time.ticks_diff(now, t_lock) > LOCK_TIMEOUT_MS:
                    print("[UNLOCK] 锁定超时，继续扫描")
                    state = "scan"
                    t_move = time.ticks_ms() - SETTLE_MS - SCAN_SAMPLE_MS + 100
                    target = None

            # ================== 上报 ==================
            if time.ticks_diff(now, last_send) >= SEND_INTERVAL_MS:
                if state == "locked" and target is not None:
                    b = target[2]
                    pkt = make_packet(seq, 1, target[1], b.cx(), b.cy(),
                                      target[0], cur_pan, cur_tilt)
                else:
                    pkt = make_packet(seq, 0, 0, -1, -1, 0, cur_pan, cur_tilt)
                if uart is not None:
                    uart.write(pkt)
                print(pkt.decode("ascii").strip())
                seq = (seq + 1) & 0xFFFF
                last_send = now

            Display.show_image(img)

    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as exc:
        sys.print_exception(exc)
    finally:
        if uart is not None:
            try:
                uart.write(make_packet(seq, 0, 0, -1, -1, 0, 90, 90))
            except Exception:
                pass
        for label, action in (
            ("pwm_tilt", pwm_tilt.deinit if pwm_tilt else None),
            ("pwm_pan", pwm_pan.deinit if pwm_pan else None),
            ("sensor", sensor.stop if sensor else None),
            ("display", Display.deinit),
            ("media", MediaManager.deinit),
            ("uart", uart.deinit if uart else None),
        ):
            if action:
                try:
                    action()
                except Exception as exc:
                    print("Cleanup", label, exc)
        time.sleep_ms(150)


if __name__ == "__main__":
    main()
