# ============================================================
# 亚博 K230 云台舵机 —— 引脚探测
# 文件名：04_servo_probe.py
#
# 目的：在不知道云台舵机接在哪个引脚的情况下，自动挨个试。
#
# 用法：
#   1. 确保云台舵机有独立 5V 供电（K230 板上的舵机口一般自带）
#   2. 运行本程序，盯着云台看
#   3. 云台开始左右/上下摆动的那个瞬间，记住屏幕上的 GPIO 编号
#   4. 按 IDE 停止键，把编号填进 05_scan_color.py 的 PAN_GPIO / TILT_GPIO
#
# 安全说明：
#   只做 60°~120° 的小幅慢速摆动，不会把云台怼到限位。
#   舵机没接 5V 时只会发出极轻微的"嗒嗒"声或完全没反应，这是正常的。
#
# K230 芯片级 PWM 映射（FPIOA 固定，不随板子变）：
#   PWM0=GPIO42  PWM1=GPIO43  PWM2=GPIO46
#   PWM3=GPIO47  PWM4=GPIO52  PWM5=GPIO53
# 如果你的板子把舵机信号线引到了别的排针上，那也只是这几个
# GPIO 之一，改 CANDIDATES 即可。
# ============================================================

import os
import sys
import time
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager
from machine import FPIOA, PWM

# 候选 (GPIO, PWM通道)，K230 芯片固定映射
CANDIDATES = (
    (42, 0),
    (43, 1),
    (46, 2),
    (47, 3),
    (52, 4),
    (53, 5),
)

WIDTH = 640
HEIGHT = 480
USE_LCD = True
FREQ = 50              # 标准模拟舵机 50Hz
HOLD_MS = 2600         # 每个引脚测试时长
ROUNDS = 2             # 整轮重复次数，方便你确认

# 安全摆动范围（0~180 度）
ANG_A = 60
ANG_B = 120


def angle_to_ns(angle):
    """角度 -> 纳秒脉宽：0°=500us，180°=2500us"""
    if angle < 0:
        angle = 0
    if angle > 180:
        angle = 180
    return int(500000 + angle * 2000000 // 180)


def draw_hud(img, l1, l2, l3, l4):
    img.draw_rectangle((0, 0, WIDTH, 118), color=(0, 0, 0), fill=True)
    img.draw_string_advanced(8, 4, 26, l1, color=(255, 255, 255))
    img.draw_string_advanced(8, 34, 22, l2, color=(255, 240, 60))
    img.draw_string_advanced(8, 62, 20, l3, color=(120, 255, 120))
    img.draw_string_advanced(8, 88, 20, l4, color=(180, 220, 255))


def test_pin(gpio, ch, img_getter, deadline):
    """在指定引脚输出慢速摆动，直到 deadline"""
    fpioa = FPIOA()
    pwm = None
    ok = False
    try:
        fpioa.set_function(gpio, getattr(FPIOA, "PWM%d" % ch), ie=0, oe=1)
        pwm = PWM(ch, freq=FREQ, duty_ns=angle_to_ns(90), enable=True)
        ok = True
    except Exception as exc:
        print("  GPIO%d/PWM%d 配置失败: %s" % (gpio, ch, exc))
        return False

    seq = (90, 75, 60, 75, 90, 105, 120, 105, 90)
    i = 0
    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            os.exitpoint()
            pwm.duty_ns(angle_to_ns(seq[i % len(seq)]))
            i += 1
            img = img_getter()
            draw_hud(img,
                     "TESTING  GPIO %d / PWM%d" % (gpio, ch),
                     "angle now: %d deg" % seq[(i - 1) % len(seq)],
                     "watch the gimbal: does it move?",
                     "stop IDE when you see movement")
            Display.show_image(img)
            time.sleep_ms(400)
    finally:
        try:
            pwm.duty_ns(angle_to_ns(90))
            time.sleep_ms(200)
            pwm.deinit()
        except Exception:
            pass
    return ok


def main():
    sensor = None
    print("")
    print("=" * 56)
    print("  K230 云台舵机引脚探测")
    print("=" * 56)
    print("  候选: %s" % (CANDIDATES,))
    print("  盯着云台，动了就记住屏幕上的 GPIO 编号")
    print("=" * 56)
    print("")

    try:
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
        for _ in range(5):
            sensor.snapshot()

        def snap():
            return sensor.snapshot()

        for r in range(ROUNDS):
            print("---- 第 %d 轮 ----" % (r + 1))
            for gpio, ch in CANDIDATES:
                print("  测试 GPIO%d / PWM%d ..." % (gpio, ch))
                deadline = time.ticks_add(time.ticks_ms(), HOLD_MS)
                test_pin(gpio, ch, snap, deadline)
                time.sleep_ms(250)

        # 收尾提示
        print("")
        print("=" * 56)
        print("  两轮都跑完了。")
        print("  - 如果云台动过：把对应 GPIO 填进 05_scan_color.py")
        print("  - 如果完全没动：先确认舵机有 5V 供电，再看下面")
        print("    1) 云台是不是通过总线舵机（一根线串两个）控制？")
        print("       那种要发串口指令，不是 PWM，得另写")
        print("    2) 舵机线是不是还插在 STM32 上？")
        print("       那就该由 STM32 驱动，K230 只管发坐标")
        print("=" * 56)

        # 保持画面，方便用户继续观察
        while True:
            os.exitpoint()
            img = sensor.snapshot()
            draw_hud(img,
                     "PROBE FINISHED",
                     "check the serial terminal",
                     "stop IDE to exit",
                     "")
            Display.show_image(img)

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
