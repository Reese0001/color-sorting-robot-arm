"""OpenMV three-color block detector.

Output protocol (UART3, 115200):
    BLOCK,<RED|GREEN|BLUE>,<cx>,<cy>,<pixels>\n
    NONE\n
Tune LAB thresholds with OpenMV IDE's Threshold Editor under real lighting.
"""

import sensor
import time
from machine import UART


# (L min, L max, A min, A max, B min, B max)
# These are safe starting points only. Real projects must recalibrate them.
COLOR_THRESHOLDS = {
    "RED": (20, 80, 20, 75, 5, 60),
    "GREEN": (20, 85, -70, -10, -10, 55),
    "BLUE": (15, 75, -20, 35, -75, -15),
}

PIXELS_THRESHOLD = 350
AREA_THRESHOLD = 500
MIN_FILL_RATIO = 0.45
ASPECT_RATIO_MIN = 0.65
ASPECT_RATIO_MAX = 1.45

uart = UART(3, 115200, timeout_char=20)

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QQVGA)  # 160x120; fast enough for control loop
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)
sensor.skip_frames(time=1500)
clock = time.clock()


def best_block(img):
    """Return (color_name, blob) for the largest square-like valid blob."""
    winner = None
    winner_pixels = 0

    for color_name, threshold in COLOR_THRESHOLDS.items():
        blobs = img.find_blobs(
            [threshold],
            pixels_threshold=PIXELS_THRESHOLD,
            area_threshold=AREA_THRESHOLD,
            merge=True,
            margin=5,
        )
        for blob in blobs:
            width = max(blob.w(), 1)
            height = max(blob.h(), 1)
            aspect = width / height
            fill = blob.pixels() / max(blob.area(), 1)
            if not (ASPECT_RATIO_MIN <= aspect <= ASPECT_RATIO_MAX):
                continue
            if fill < MIN_FILL_RATIO:
                continue
            if blob.pixels() > winner_pixels:
                winner = (color_name, blob)
                winner_pixels = blob.pixels()

    return winner


while True:
    clock.tick()
    image = sensor.snapshot()
    result = best_block(image)

    if result is None:
        uart.write("NONE\n")
        continue

    color, target = result
    image.draw_rectangle(target.rect(), color=(255, 255, 255), thickness=2)
    image.draw_cross(target.cx(), target.cy(), color=(255, 255, 255), size=5)
    uart.write(
        "BLOCK,{},{},{},{}\n".format(
            color, target.cx(), target.cy(), target.pixels()
        )
    )
