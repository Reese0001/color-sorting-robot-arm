# ============================================================
# 亚博 K230 红绿蓝木块 —— 阈值自动标定（v2 背景差分版）
# 文件名：03_auto_calibrate.py
#
# 为什么要有 v2：
#   v1（和 Codex 原版思路）是把整个采样框当木块做统计。木块只占框的
#   30% 时，统计值里混进 70% 的桌面颜色，算出的阈值又宽又偏，结果就是
#   "怎么调都框不稳"。v2 改成先量背景、再用 invert 找木块，木块占多小
#   都不影响结果。
#
# 用法（CanMV IDE K230）：
#   1. 把桌面清干净，白色或灰色背景最好
#   2. 打开本文件，点运行
#   3. 按屏幕提示，依次把【红】【绿】【蓝】木块放进中间黄框
#   4. 跑完终端会打印一段 COLOR_THRESHOLDS，整段复制
#   5. 粘进 02_color_uart.py 替换原来的 COLOR_THRESHOLDS
#
# 调参口诀（框不住 / 框太宽时看这里）：
#   木块找不到       -> BG_TOL_L / BG_TOL_AB 调大（16/12 -> 24/18）
#   背景被当成木块   -> BG_TOL_L / BG_TOL_AB 调小（12/10）
#   框比木块大一圈   -> SIGMA 调小（2.6 -> 2.0）
#   只框住木块中间   -> SIGMA 调大（2.6 -> 3.2）
#   小木块漏检       -> MIN_BLOB_PIXELS 调小（350 -> 150）
# ============================================================

import os
import sys
import time
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager

# ================= 用户配置 =================
WIDTH = 640
HEIGHT = 480
USE_LCD = True

BOX_W = 260             # 中央采样框边长
BOX_H = 260
BOX_X = (WIDTH - BOX_W) // 2
BOX_Y = (HEIGHT - BOX_H) // 2

# 背景容差（判断"这个像素是不是背景"的宽容度）
BG_TOL_L = 16
BG_TOL_AB = 12

SIGMA = 2.6             # 木块阈值半宽 = SIGMA x 标准差
MIN_HALF = (10, 9, 9)   # L/A/B 通道最小半宽，防止阈值窄到框不住
MIN_BLOB_PIXELS = 350   # 木块至少这么大才算数
MIN_SAMPLES = 8         # 至少攒够这么多有效帧
SAMPLE_MS = 1800        # 每种颜色采样时长
COUNTDOWN_MS = 4000     # 准备倒计时
RESULT_MS = 3500        # 结果停留
RETRY_MAX = 3           # 采样失败最多重试次数

ONLY_COLOR = 0          # 0=三色全标定；1/2/3=只标定红/绿/蓝（先试一种用这个）

NAMES = ("RED", "GREEN", "BLUE")
DRAW_RGB = ((255, 40, 40), (40, 220, 40), (60, 140, 255))


# ================= 兼容层 =================
# K230 不同固件的 API 细节有差异，这里把可能踩坑的调用都包一层。
# 任何一层挂掉都不至于让脚本退出 —— 脚本一退，画面立刻全黑，
# 你只能看到黑屏看不到原因，这才是最坑的地方。
_CAP = {"stats_kw": False, "median": False, "fill": False, "invert": False}


def chan_mean(s, ch):
    if ch == 0:
        return s.l_mean()
    if ch == 1:
        return s.a_mean()
    return s.b_mean()


def chan_median(s, ch):
    """中位数拿不到就退回均值，精度差一点但不至于崩"""
    if not _CAP["median"]:
        return chan_mean(s, ch)
    try:
        if ch == 0:
            return s.l_median()
        if ch == 1:
            return s.a_median()
        return s.b_median()
    except Exception:
        return chan_mean(s, ch)


def get_stats(img, roi):
    """get_statistics 兼容调用：先试关键字，再试位置参数"""
    if _CAP["stats_kw"]:
        return img.get_statistics(roi=roi)
    try:
        return img.get_statistics([], False, roi)
    except Exception:
        return img.get_statistics()


def fill_rect(img, r, color):
    """填充矩形，不支持 fill 参数就用粗边框模拟"""
    if _CAP["fill"]:
        img.draw_rectangle(r, color=color, fill=True)
    else:
        img.draw_rectangle(r, color=color, thickness=6)


def draw_text(img, x, y, size, text, color):
    try:
        img.draw_string_advanced(x, y, size, text, color=color)
    except Exception:
        try:
            img.draw_string(x, y, text, color=color)
        except Exception:
            pass


def probe_caps(img):
    """开机探测本固件支持哪些调用，结果决定后续走哪条路"""
    try:
        img.get_statistics(roi=(0, 0, 32, 32))
        _CAP["stats_kw"] = True
    except Exception:
        _CAP["stats_kw"] = False
    try:
        s = get_stats(img, (0, 0, 32, 32))
        s.l_median()
        _CAP["median"] = True
    except Exception:
        _CAP["median"] = False
    try:
        img.draw_rectangle((0, 0, 4, 4), color=(0, 0, 0), fill=True)
        _CAP["fill"] = True
    except Exception:
        _CAP["fill"] = False
    try:
        img.find_blobs([(0, 100, -128, 127, -128, 127)],
                       roi=(0, 0, 64, 64), invert=True,
                       pixels_threshold=100, area_threshold=100)
        _CAP["invert"] = True
    except Exception:
        _CAP["invert"] = False
    return _CAP


# ================= 工具 =================
def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def median_of(values):
    n = len(values)
    if n == 0:
        return 0
    s = sorted(values)
    if n & 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def stats6(img, roi):
    """ROI 内 LAB 的 (均值, 标准差)，未做编码归一"""
    s = get_stats(img, roi)
    return (s.l_mean(), s.l_stdev(),
            s.a_mean(), s.a_stdev(),
            s.b_mean(), s.b_stdev())


def bg_median(img):
    """从采样框左右两侧估背景色，返回 (l, a, b) 原始编码值。
    用中位数而不是均值：桌面有反光点时中位数不动，均值会被拉偏。"""
    lw = BOX_X - 12
    rw = WIDTH - (BOX_X + BOX_W) - 12
    if lw < 20:
        lw = 20
    if rw < 20:
        rw = 20
    left = (0, BOX_Y, lw, BOX_H)
    right = (BOX_X + BOX_W + 12, BOX_Y, rw, BOX_H)
    s1 = get_stats(img, left)
    s2 = get_stats(img, right)
    return ((chan_median(s1, 0) + chan_median(s2, 0)) // 2,
            (chan_median(s1, 1) + chan_median(s2, 1)) // 2,
            (chan_median(s1, 2) + chan_median(s2, 2)) // 2)


def resolve_encoding(bg):
    """用背景色判断固件的 statistics 编码。
    白/灰背景是已知参照物：
      标准编码  L 约 0~100，A/B 约 -5~5
      0~255 编码 L 约 200~255，A/B 约 123~133

    关键：先看 A/B，再看 L。因为深色桌面在 0~255 编码下 L 只有 60 左右，
    单看 L 会误判成标准编码；而 A/B 不管明暗都稳在 128 附近，
    这个判断比 L 可靠得多。A/B 一旦确定是 0~255，L 必然同编码。"""
    bl = bg[0]
    ba = bg[1]
    bb = bg[2]
    if ba > 60 or bb > 60:
        # A/B 在 128 附近 -> 整套都是 0~255 编码
        return 100.0 / 255.0, -128
    if bl > 100:
        # A/B 正常但 L 超过 100 -> L 是 0~255，A/B 是标准
        return 100.0 / 255.0, 0
    return 1.0, 0


def bg_threshold(bg, l_scale, ab_off):
    """背景色 +/- 容差，配合 invert=True 就能框出"非背景"的木块"""
    bl = bg[0] * l_scale
    ba = bg[1] + ab_off
    bb = bg[2] + ab_off
    return (int(clamp(bl - BG_TOL_L, 0, 100)), int(clamp(bl + BG_TOL_L, 0, 100)),
            int(clamp(ba - BG_TOL_AB, -128, 127)), int(clamp(ba + BG_TOL_AB, -128, 127)),
            int(clamp(bb - BG_TOL_AB, -128, 127)), int(clamp(bb + BG_TOL_AB, -128, 127)))


def find_block(img, bg, l_scale, ab_off):
    """在采样框里找最大的非背景块。返回 (rect, cx, cy, pixels) 或 None"""
    if not _CAP["invert"]:
        return None
    th = bg_threshold(bg, l_scale, ab_off)
    try:
        blobs = img.find_blobs([th], roi=(BOX_X, BOX_Y, BOX_W, BOX_H),
                               invert=True,
                               pixels_threshold=MIN_BLOB_PIXELS,
                               area_threshold=MIN_BLOB_PIXELS,
                               merge=True)
    except Exception:
        return None
    best = None
    for b in blobs:
        if best is None or b.pixels() > best.pixels():
            best = b
    if best is None:
        return None
    r = best.rect()
    return (r, best.cx(), best.cy(), best.pixels())


def block_threshold(raw, l_scale, ab_off):
    """把木块的 (均值,标准差) 转成 find_blobs 的 6 元阈值"""
    l_c = raw[0] * l_scale
    l_h = raw[1] * l_scale * SIGMA
    if l_h < MIN_HALF[0]:
        l_h = MIN_HALF[0]
    a_c = raw[2] + ab_off
    a_h = raw[3] * SIGMA
    if a_h < MIN_HALF[1]:
        a_h = MIN_HALF[1]
    b_c = raw[4] + ab_off
    b_h = raw[5] * SIGMA
    if b_h < MIN_HALF[2]:
        b_h = MIN_HALF[2]
    return (int(clamp(l_c - l_h, 0, 100)), int(clamp(l_c + l_h, 0, 100)),
            int(clamp(a_c - a_h, -128, 127)), int(clamp(a_c + a_h, -128, 127)),
            int(clamp(b_c - b_h, -128, 127)), int(clamp(b_c + b_h, -128, 127)))


def count_with(img, th, min_px):
    """用给定阈值数一遍，返回 (总像素, 最大 blob)"""
    blobs = img.find_blobs([th], roi=(BOX_X, BOX_Y, BOX_W, BOX_H),
                           pixels_threshold=min_px,
                           area_threshold=min_px,
                           merge=True)
    total = 0
    biggest = None
    for b in blobs:
        total += b.pixels()
        if biggest is None or b.pixels() > biggest.pixels():
            biggest = b
    return total, biggest


def shrink(r, pad=2):
    x = r[0] + pad
    y = r[1] + pad
    w = r[2] - pad * 2
    h = r[3] - pad * 2
    if w < 8 or h < 8:
        return r
    return (x, y, w, h)


def ranges_overlap(a, b):
    return not (a[1] < b[0] or b[1] < a[0])


def check_overlap(results):
    problems = []
    for i in range(3):
        for j in range(i + 1, 3):
            ti = results[i]
            tj = results[j]
            if ti is None or tj is None:
                continue
            if (ranges_overlap((ti[0], ti[1]), (tj[0], tj[1]))
                    and ranges_overlap((ti[2], ti[3]), (tj[2], tj[3]))
                    and ranges_overlap((ti[4], ti[5]), (tj[4], tj[5]))):
                problems.append("%s 与 %s 三通道全重叠，会互相误判" % (NAMES[i], NAMES[j]))
    return problems


# ================= 绘制 =================
def draw_hud(img, l1, l2, l3):
    fill_rect(img, (0, 0, WIDTH, 92), (0, 0, 0))
    draw_text(img, 8, 4, 26, l1, (255, 255, 255))
    draw_text(img, 8, 34, 22, l2, (255, 240, 60))
    draw_text(img, 8, 62, 20, l3, (160, 220, 255))


def draw_box(img, color=(255, 255, 0), thickness=3):
    img.draw_rectangle((BOX_X, BOX_Y, BOX_W, BOX_H), color=color, thickness=thickness)
    img.draw_cross(BOX_X + BOX_W // 2, BOX_Y + BOX_H // 2,
                   color=color, size=12, thickness=2)


def draw_bar(img, pct, color):
    fill_rect(img, (10, HEIGHT - 30, WIDTH - 20, 16), (40, 40, 40))
    if pct > 0:
        fill_rect(img, (10, HEIGHT - 30, int((WIDTH - 20) * pct / 100), 16), color)


def draw_crash(img, err):
    """把异常画在屏幕上。这是本脚本最重要的一段：
    出错也要留在屏幕上，否则你只能对着黑屏猜。"""
    try:
        fill_rect(img, (0, 0, WIDTH, HEIGHT), (45, 0, 0))
        draw_text(img, 12, 20, 28, "SCRIPT ERROR", (255, 70, 70))
        for i in range(4):
            seg = err[i * 50:(i + 1) * 50]
            if not seg:
                break
            draw_text(img, 12, 64 + i * 28, 20, seg, (255, 255, 255))
        draw_text(img, 12, 200, 20, "screenshot this screen", (255, 220, 0))
        draw_text(img, 12, 226, 20, "and send it to me", (255, 220, 0))
    except Exception:
        pass


# ================= 主流程 =================
def main():
    sensor = None
    try:
        print("")
        print("=" * 56)
        print("  K230 红绿蓝木块 —— 阈值自动标定 v2")
        print("=" * 56)
        print("  背景容差  L+/-%d  AB+/-%d" % (BG_TOL_L, BG_TOL_AB))
        print("  阈值半宽  SIGMA = %.1f" % SIGMA)
        print("  依次放入 红 / 绿 / 蓝 木块，放进中间黄框")
        print("=" * 56)
        print("")

        # ===== 阶段 0：最小启动 =====
        # 先把「相机 + 屏幕」这条最基础的链路打通，并立刻送一帧出去。
        # 这一帧能亮，就证明硬件链路没问题，后面所有毛病都是脚本逻辑；
        # 这一帧不亮，说明问题在显示/连接，跟标定算法无关。
        print("[BOOT] 初始化相机")
        sensor = Sensor(width=WIDTH, height=HEIGHT)
        sensor.reset()
        sensor.set_framesize(width=WIDTH, height=HEIGHT)
        sensor.set_pixformat(Sensor.RGB565)
        print("[BOOT] 初始化显示")
        if USE_LCD:
            Display.init(Display.ST7701, to_ide=True)
        else:
            Display.init(Display.VIRT, width=WIDTH, height=HEIGHT, fps=30)
        MediaManager.init()
        print("[BOOT] 启动采集")
        sensor.run()
        img = None
        for _ in range(10):
            img = sensor.snapshot()
        print("[BOOT] 拿到首帧")

        # ===== 能力探测 =====
        caps = probe_caps(img)
        print("[CAP] stats_kw=%s  median=%s  fill=%s  invert=%s"
              % (caps["stats_kw"], caps["median"], caps["fill"], caps["invert"]))

        img = sensor.snapshot()
        fill_rect(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0))
        draw_text(img, 24, 36, 46, "BOOT OK", (0, 255, 0))
        draw_text(img, 24, 110, 22, "stats_kw : %s" % caps["stats_kw"], (255, 255, 255))
        draw_text(img, 24, 140, 22, "median   : %s" % caps["median"], (255, 255, 255))
        draw_text(img, 24, 170, 22, "fill     : %s" % caps["fill"], (255, 255, 255))
        draw_text(img, 24, 200, 22, "invert   : %s" % caps["invert"], (255, 255, 255))
        draw_text(img, 24, 250, 20, "camera + display are working", (255, 220, 0))
        draw_text(img, 24, 276, 20, "calibration starts in a moment", (255, 220, 0))
        Display.show_image(img)
        time.sleep_ms(1600)

        if not caps["invert"]:
            # invert 是 v2 的地基，没有它这套方法不成立
            print("[CAP] !! invert 不可用，v2 方案无法工作")
            img = sensor.snapshot()
            fill_rect(img, (0, 0, WIDTH, HEIGHT), (50, 40, 0))
            draw_text(img, 24, 40, 32, "NO INVERT SUPPORT", (255, 200, 0))
            draw_text(img, 24, 100, 20, "find_blobs(invert=True) failed", (255, 255, 255))
            draw_text(img, 24, 128, 20, "screenshot this and send it", (255, 255, 255))
            Display.show_image(img)
            while True:
                os.exitpoint()
                time.sleep_ms(200)

        # ===== 量背景，定编码 =====
        probe = sensor.snapshot()
        bg0 = bg_median(probe)
        l_scale, ab_off = resolve_encoding(bg0)
        print("[编码] 背景中位色 L=%d A=%d B=%d" % (bg0[0], bg0[1], bg0[2]))
        print("[编码] l_scale=%.3f  ab_off=%d  (%s)"
              % (l_scale, ab_off,
                 "0~255 编码" if (l_scale < 1.0 or ab_off != 0) else "标准编码"))

        img = sensor.snapshot()
        fill_rect(img, (0, 0, WIDTH, HEIGHT), (0, 0, 0))
        draw_text(img, 24, 40, 32, "BACKGROUND", (0, 220, 255))
        draw_text(img, 24, 100, 24, "L=%d  A=%d  B=%d" % (bg0[0], bg0[1], bg0[2]),
                  (255, 255, 255))
        draw_text(img, 24, 136, 24, "scale=%.3f  off=%d" % (l_scale, ab_off),
                  (255, 255, 255))
        draw_text(img, 24, 180, 20, "should be white or grey desk", (255, 220, 0))
        Display.show_image(img)
        time.sleep_ms(1200)

        results = [None, None, None]
        idx = 0
        if ONLY_COLOR:
            idx = ONLY_COLOR - 1
        phase = "countdown"
        t_phase = time.ticks_ms()
        samples = []
        work_rect = (BOX_X, BOX_Y, BOX_W, BOX_H)
        retry = 0
        printed = False

        # 绘制缓存（存数值不存 blob 对象，避免跨帧失效）
        dbg_rect = None
        dbg_px = 0

        while True:
            os.exitpoint()
            try:
                img = sensor.snapshot()
                now = time.ticks_ms()
                dt = time.ticks_diff(now, t_phase)

                # 每帧先用未绘制的原始图量背景
                bg = bg_median(img)

                # ============ 状态机 ============
                if phase == "countdown":
                    dbg_rect = None
                    dbg_px = 0
                    if dt >= COUNTDOWN_MS:
                        phase = "sampling"
                        t_phase = now
                        samples = []
                        work_rect = (BOX_X, BOX_Y, BOX_W, BOX_H)

                elif phase == "sampling":
                    hit = find_block(img, bg, l_scale, ab_off)
                    if hit is not None:
                        dbg_rect = hit[0]
                        dbg_px = hit[3]
                        work_rect = shrink(hit[0])
                        samples.append(stats6(img, work_rect) + (hit[3],))
                    else:
                        dbg_rect = None
                        dbg_px = 0

                    if dt >= SAMPLE_MS:
                        if len(samples) >= MIN_SAMPLES:
                            raw_final = (
                                median_of([s[0] for s in samples]),
                                median_of([s[1] for s in samples]),
                                median_of([s[2] for s in samples]),
                                median_of([s[3] for s in samples]),
                                median_of([s[4] for s in samples]),
                                median_of([s[5] for s in samples]),
                            )
                            th = block_threshold(raw_final, l_scale, ab_off)
                            n_check, _ = count_with(img, th, MIN_BLOB_PIXELS)
                            # 兜底：万一编码判定反了，换一组再算一次，谁框得多用谁
                            if n_check < MIN_BLOB_PIXELS:
                                alt_scale = 1.0 if l_scale != 1.0 else (100.0 / 255.0)
                                alt_off = 0 if ab_off != 0 else -128
                                th_alt = block_threshold(raw_final, alt_scale, alt_off)
                                n_alt, _ = count_with(img, th_alt, MIN_BLOB_PIXELS)
                                if n_alt > n_check:
                                    print("  [%s] 编码判定反了，已自动切换 scale=%.3f off=%d"
                                          % (NAMES[idx], alt_scale, alt_off))
                                    l_scale = alt_scale
                                    ab_off = alt_off
                                    th = th_alt
                                    n_check = n_alt
                            px_med = median_of([s[6] for s in samples])
                            print("  [%s] %d 帧有效，中位 %d px"
                                  % (NAMES[idx], len(samples), px_med))
                            print("  [%s] 木块统计 L=%.1f+/-%.1f A=%.1f+/-%.1f B=%.1f+/-%.1f"
                                  % (NAMES[idx], raw_final[0] * l_scale, raw_final[1] * l_scale,
                                     raw_final[2] + ab_off, raw_final[3],
                                     raw_final[4] + ab_off, raw_final[5]))
                            print("  [%s] 阈值 L %d..%d  A %d..%d  B %d..%d  (自检 %d px)"
                                  % (NAMES[idx], th[0], th[1], th[2], th[3],
                                     th[4], th[5], n_check))
                            if n_check < MIN_BLOB_PIXELS:
                                print("  [%s] !! 自检框不住，把上面几行发我，调 SIGMA 或背景容差"
                                      % NAMES[idx])
                            results[idx] = th
                            idx += 1
                            retry = 0
                            phase = "result"
                            t_phase = now
                        else:
                            retry += 1
                            print("  [%s] 有效帧 %d < %d，重试 %d/%d"
                                  % (NAMES[idx], len(samples), MIN_SAMPLES, retry, RETRY_MAX))
                            if retry > RETRY_MAX:
                                print("  [%s] 跳过。检查木块是否在黄框内、背景是否干净"
                                      % NAMES[idx])
                                idx += 1
                                retry = 0
                            phase = "countdown"
                            t_phase = now

                elif phase == "result":
                    if dt >= RESULT_MS:
                        if idx < 3:
                            phase = "countdown"
                            t_phase = now
                        else:
                            phase = "done"
                            t_phase = now

                elif phase == "done":
                    if not printed:
                        printed = True
                        print("")
                        print("=" * 56)
                        print("  复制下面整段，替换 02_color_uart.py 的 COLOR_THRESHOLDS")
                        print("=" * 56)
                        print("COLOR_THRESHOLDS = (")
                        for i in range(3):
                            t = results[i]
                            if t is None:
                                print("    (0, 100, -128, 127, -128, 127),  # %-5s 未标定" % NAMES[i])
                            else:
                                print("    (%d, %d, %d, %d, %d, %d),  # %-5s ID %d"
                                      % (t[0], t[1], t[2], t[3], t[4], t[5], NAMES[i], i + 1))
                        print(")")
                        print("=" * 56)
                        problems = check_overlap(results)
                        if problems:
                            print("  !! 阈值冲突：")
                            for p in problems:
                                print("    - " + p)
                        else:
                            print("  三色阈值无重叠，可以放心用")
                        print("")
                        print("  进入验证模式：三块木块同时放进画面，")
                        print("  看是否都被框住、框得紧不紧。按 IDE 停止键结束。")
                        print("")

                # ============ 绘制（放最后，避免绘图像素污染统计）============
                if phase == "countdown":
                    left = (COUNTDOWN_MS - dt) // 1000 + 1
                    draw_box(img)
                    draw_hud(img,
                             "STEP %d/3  PUT %s BLOCK" % (idx + 1, NAMES[idx]),
                             "inside the yellow box.  start in %d s" % left,
                             "clean white/grey background, light fixed")
                    draw_bar(img, 100 * dt // COUNTDOWN_MS, (255, 200, 0))

                elif phase == "sampling":
                    draw_box(img, color=(0, 255, 255))
                    pct = 100 * dt // SAMPLE_MS
                    if pct > 100:
                        pct = 100
                    draw_hud(img,
                             "SAMPLING %s  %d%%" % (NAMES[idx], pct),
                             "frames %d/%d   block %d px" % (len(samples), MIN_SAMPLES, dbg_px),
                             "keep still")
                    draw_bar(img, pct, (0, 255, 255))
                    if dbg_rect is not None:
                        img.draw_rectangle(dbg_rect, color=(0, 255, 255), thickness=2)

                elif phase == "result":
                    draw_box(img)
                    t = results[idx - 1]
                    if t is not None:
                        draw_hud(img,
                                 "%s OK    L %d..%d" % (NAMES[idx - 1], t[0], t[1]),
                                 "A %d..%d    B %d..%d" % (t[2], t[3], t[4], t[5]),
                                 "swap to the next block")
                    else:
                        draw_hud(img, "%s FAILED" % NAMES[idx - 1],
                                 "block not found", "will retry or skip")

                elif phase == "done":
                    draw_box(img, color=(110, 110, 110), thickness=2)
                    draw_hud(img, "VERIFY MODE",
                             "put all 3 blocks in view",
                             "stop IDE to quit")
                    y = 100
                    for i in range(3):
                        if results[i] is None:
                            continue
                        n, big = count_with(img, results[i], 150)
                        if big is not None:
                            img.draw_rectangle(big.rect(), color=DRAW_RGB[i], thickness=2)
                            img.draw_cross(big.cx(), big.cy(), color=DRAW_RGB[i], thickness=2)
                        img.draw_string_advanced(10, y, 24, "%s: %d px" % (NAMES[i], n),
                                                 color=DRAW_RGB[i])
                        y += 28

                Display.show_image(img)

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                err = "%s: %s" % (type(exc).__name__, exc)
                print("[ERR] " + err)
                # 崩溃不退出：把错误画在屏幕上，截图就能定位
                try:
                    _e = sensor.snapshot()
                    draw_crash(_e, err)
                    Display.show_image(_e)
                except Exception:
                    pass
                time.sleep_ms(600)
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as exc:
        sys.print_exception(exc)
    finally:
        for label, action in (
            ("sensor", sensor.stop if sensor else None),
            ("display", Display.deinit),
            ("media", MediaManager.deinit),
        ):
            if action:
                try:
                    action()
                except Exception as exc:
                    print("Cleanup", label, exc)
        time.sleep_ms(100)


if __name__ == "__main__":
    main()
