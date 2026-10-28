# 亚博 K230：红绿蓝色块识别 + UART 观测数据输出。
# 先在 CanMV IDE K230 运行；阈值必须用现场木块和光照校准。
import os
import sys
import time
import gc
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager

# ---------- 用户配置 ----------
WIDTH = 640
HEIGHT = 480
USE_LCD = True       # False：只显示到 IDE；确认屏幕为 ST7701 后可改 True
UART_ENABLED = False # 先验证识别；核对板子接口和 STM32 接线后改 True
BAUDRATE = 115200

# 亚博官方 K230 视觉模块 USB 旁通信口：UART1，GPIO9=TX、GPIO10=RX。
# 不适用于所有品牌/版本的 K230；实物需核对。
TX_PIN = 9
RX_PIN = 10

# LAB 顺序：(L最小, L最大, A最小, A最大, B最小, B最大)。
# 以下只是调试起点，不是已对你的木块标定好的参数。
COLOR_THRESHOLDS = (
    (15, 95, 20, 127, 5, 127),     # 红：ID 1
    (15, 95, -90, -12, -10, 90),   # 绿：ID 2
    (10, 90, -40, 90, -128, -20),  # 蓝：ID 3
)
COLOR_NAMES = ("RED", "GREEN", "BLUE")
DRAW_COLORS = ((255, 0, 0), (0, 255, 0), (0, 128, 255))
ROI = (0, 0, WIDTH, HEIGHT)  # 按抓取区修改：(左上x, 左上y, 宽, 高)
MIN_PIXELS = 250            # 实际符合颜色阈值的像素数
MIN_AREA = 400              # 外接矩形面积
MIN_FILL_RATIO = 0.35       # 色块像素数 / 外接矩形面积
MAX_PIXELS = WIDTH * HEIGHT // 2
STABLE_FRAMES = 5
STABLE_MS = 250
MAX_CENTER_DRIFT = 12       # 相对本轮稳定窗口起点的像素位移
MAX_FRAME_GAP_MS = 500      # 采集长时间停顿后重新积累稳定帧
SEND_INTERVAL_MS = 100      # 最多 10 次/秒，实际速率取决于识别帧率
WARMUP_MS = 2000

# 多色同时稳定时，按这个顺序挑一个上报。
# (0,1,2) = 红 > 绿 > 蓝。想改成"蓝优先"就写 (2,0,1)。
PRIORITY = (0, 1, 2)

# 云台当前角度。02 版是固定视角不控云台，所以填死 90。
# 换成 05_scan_color.py 那种会转云台的版本时，这里要传实时角度。
PAN_FIXED = 90
TILT_FIXED = 90


class StableTarget:
    """只做稳定性筛选，不代表已经确认物体材质或可以安全抓取。"""
    # 随臂摄像头：图像稳定不等于机械臂停稳，STM32 需另行确认观察姿态。
    def __init__(self):
        self.reset()

    def reset(self):
        self.anchor = None
        self.count = 0
        self.since = 0
        self.last_seen = 0

    def update(self, target, now):
        # target = (颜色ID, cx, cy, pixels)
        if target is None:
            self.reset()
            return None
        same = self.anchor is not None and target[0] == self.anchor[0]
        if same:
            dx = target[1] - self.anchor[1]
            dy = target[2] - self.anchor[2]
            same = (dx * dx + dy * dy <= MAX_CENTER_DRIFT ** 2
                    and time.ticks_diff(now, self.last_seen) <= MAX_FRAME_GAP_MS)
        if not same:
            self.anchor = target
            self.count = 1
            self.since = now
        else:
            self.count = min(self.count + 1, STABLE_FRAMES)
        self.last_seen = now
        if self.count >= STABLE_FRAMES and time.ticks_diff(now, self.since) >= STABLE_MS:
            return target
        return None


def make_packet(seq, pan, tilt, targets):
    """全景上报帧：三色各占一个槽位，没看到就填 -1,-1,0。

    格式 @T,seq,pan,tilt,rx,ry,rp,gx,gy,gp,bx,by,bp*XX\\r\\n
    targets = [红, 绿, 蓝]，每项是 (颜色ID, cx, cy, pixels) 或 None
    """
    parts = ["T", str(seq), str(pan), str(tilt)]
    for i in range(3):
        t = targets[i] if targets is not None else None
        if t is None:
            parts.append("-1")
            parts.append("-1")
            parts.append("0")
        else:
            parts.append(str(t[1]))
            parts.append(str(t[2]))
            parts.append(str(t[3]))
    body = ",".join(parts)
    checksum = 0
    for v in body.encode("ascii"):
        checksum ^= v
    return ("@%s*%02X\r\n" % (body, checksum)).encode("ascii")


def detect_all(img):
    """三色各自独立检测，互不干扰。

    返回 (per_color, detections)：
      per_color[i] = (颜色ID, cx, cy, pixels) 或 None
      detections   = [(index, blob), ...] 供绘制用

    关键改动：每色只跟自己比，取自己像素最大的块，
    不再跨颜色比较。跨颜色比较的后果是 —— 红蓝木块大小接近时，
    像素数的正常波动会让"胜出者"每帧在红色和蓝色之间跳变，
    颜色 ID 一变，稳定计数立刻清零，永远攒不够帧数，
    屏幕上就一直显示 WAIT: no stable target。
    """
    per_color = [None, None, None]
    detections = []
    for index, threshold in enumerate(COLOR_THRESHOLDS):
        blobs = img.find_blobs([threshold], roi=ROI,
                               pixels_threshold=MIN_PIXELS,
                               area_threshold=MIN_AREA, merge=False)
        best = None
        for blob in blobs:
            pixels = blob.pixels()
            box_area = blob.w() * blob.h()
            if pixels > MAX_PIXELS or pixels < MIN_FILL_RATIO * box_area:
                continue
            detections.append((index, blob))
            if best is None or pixels > best[3]:
                best = (index + 1, blob.cx(), blob.cy(), pixels)
        per_color[index] = best
    return per_color, detections


def main():
    sensor = None
    uart = None
    fpioa = None  # 保持引脚配置对象的生命周期
    seq = 0
    # 三色各一个稳定判定器，互不干扰
    trackers = [StableTarget(), StableTarget(), StableTarget()]
    try:
        print("Board:", os.uname())
        print("UART_ENABLED:", UART_ENABLED)
        if UART_ENABLED:
            from machine import UART, FPIOA
            fpioa = FPIOA()
            fpioa.set_function(TX_PIN, FPIOA.UART1_TXD, ie=0, oe=1)
            fpioa.set_function(RX_PIN, FPIOA.UART1_RXD, ie=1, oe=0)
            uart = UART(UART.UART1, baudrate=BAUDRATE, bits=UART.EIGHTBITS,
                        parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)

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
        start = time.ticks_ms()
        last_send = start
        frame_count = 0
        while True:
            os.exitpoint()
            img = sensor.snapshot()
            now = time.ticks_ms()
            warming_up = time.ticks_diff(now, start) < WARMUP_MS
            if warming_up:
                per_color = [None, None, None]
                detections = []
                for t in trackers:
                    t.reset()
                stables = [None, None, None]
            else:
                per_color, detections = detect_all(img)
                stables = [trackers[i].update(per_color[i], now) for i in range(3)]

            # 多色同时稳定时按 PRIORITY 挑一个上报
            stable = None
            for i in PRIORITY:
                if stables[i] is not None:
                    stable = stables[i]
                    break

            # 持续发送全景观测帧；某色没有稳定目标就填 -1，不沿用旧坐标。
            if time.ticks_diff(now, last_send) >= SEND_INTERVAL_MS:
                packet = make_packet(seq, PAN_FIXED, TILT_FIXED, stables)
                if uart is not None:
                    sent = uart.write(packet)
                    if sent != len(packet):
                        raise RuntimeError("UART incomplete write: %s" % sent)
                print(packet.decode("ascii").strip())
                seq = (seq + 1) & 0xFFFF
                last_send = now

            for index, blob in detections:
                color = DRAW_COLORS[index]
                img.draw_rectangle(blob.rect(), color=color, thickness=2)
                img.draw_cross(blob.cx(), blob.cy(), color=color, thickness=2)
                img.draw_string_advanced(blob.x(), max(0, blob.y() - 24), 20,
                                         COLOR_NAMES[index], color=color)

            # 三色各自的实时状态，哪一色卡住了一眼就能看出来
            for i in range(3):
                if per_color[i] is None:
                    mark = "  ---"
                elif stables[i] is not None:
                    mark = "%5dpx  OK" % per_color[i][3]
                else:
                    mark = "%5dpx  .." % per_color[i][3]
                img.draw_string_advanced(8, 96 + i * 26, 20,
                                         "%s %s" % (COLOR_NAMES[i], mark),
                                         color=DRAW_COLORS[i])

            if stable is not None:
                img.draw_cross(stable[1], stable[2], color=(255, 255, 255),
                               size=20, thickness=3)
                status = "VALID: " + COLOR_NAMES[stable[0] - 1]
            else:
                status = "WARMUP" if warming_up else "WAIT: no stable target"
            img.draw_string_advanced(0, 0, 24, status, color=(255, 255, 255))
            Display.show_image(img)
            frame_count += 1
            if frame_count % 30 == 0:
                gc.collect()
    except KeyboardInterrupt:
        print("Stopped")
    except Exception as exc:
        sys.print_exception(exc)
    finally:
        if uart is not None:
            try:
                uart.write(make_packet(seq, PAN_FIXED, TILT_FIXED, None))
            except Exception:
                pass
        for label, action in (
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
        time.sleep_ms(100)


if __name__ == "__main__":
    main()
