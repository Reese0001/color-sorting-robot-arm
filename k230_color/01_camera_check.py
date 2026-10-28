# 在 CanMV IDE K230 中运行，不是在电脑的 Python 中运行。
# 默认只把画面显示到 IDE，不依赖板载屏幕型号。
import os
import sys
import time
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager

WIDTH = 640
HEIGHT = 480


def main():
    sensor = None
    print("Board:", os.uname())
    print("Python:", sys.version)
    try:
        sensor = Sensor(width=WIDTH, height=HEIGHT)
        sensor.reset()
        sensor.set_framesize(width=WIDTH, height=HEIGHT)
        sensor.set_pixformat(Sensor.RGB565)
        Display.init(Display.VIRT, width=WIDTH, height=HEIGHT, fps=30)
        MediaManager.init()
        sensor.run()
        frames = 0
        while True:
            os.exitpoint()
            img = sensor.snapshot()
            Display.show_image(img)
            frames += 1
            if frames % 60 == 0:
                print("Camera OK; frames:", frames)
    except KeyboardInterrupt:
        print("Stopped")
    except Exception as exc:
        sys.print_exception(exc)
    finally:
        # 即使某一步清理失败，也继续释放其他资源。
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
