"""Run manually in CanMV IDE; do not save as main.py."""
import os
import time
import sys

print("PROBE 0: script started")
os.exitpoint(os.EXITPOINT_ENABLE)
from libs.PipeLine import PipeLine
from media.sensor import CAM_CHN_ID_1
from media.display import Display
print("PROBE 1: imports OK")

pipeline = None
try:
    pipeline = PipeLine(rgb888p_size=[640, 480],
                        display_size=[640, 480], display_mode="lcd")
    print("PROBE 2: before pipeline.create")
    pipeline.create()
    print("PROBE 3: pipeline.create returned")
    time.sleep_ms(1500)
    count = 0
    last_log = time.ticks_ms()
    while True:
        os.exitpoint()
        if count == 0:
            print("PROBE 4: before first snapshot")
        img = pipeline.sensor.snapshot(chn=CAM_CHN_ID_1)
        if count == 0:
            print("PROBE 5: first snapshot OK")
        img.draw_string_advanced(8, 8, 24, "LIVE " + str(count), color=(255, 255, 0))
        Display.show_image(img)
        if count == 0:
            print("PROBE 6: first show_image OK")
        count += 1
        if time.ticks_diff(time.ticks_ms(), last_log) >= 1000:
            print("LIVE frames:", count)
            last_log = time.ticks_ms()
        time.sleep_ms(50)
except KeyboardInterrupt:
    print("PROBE: stopped")
except Exception as error:
    sys.print_exception(error)
    raise
finally:
    print("PROBE: cleanup starting")
    if pipeline is not None:
        pipeline.destroy()
    print("PROBE: cleanup finished")
