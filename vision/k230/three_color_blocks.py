"""Yahboom K230: five-color block preview; run manually in CanMV IDE.

Requires the vendor /sdcard/libs/PipeLine.py already on the TF card.
No model or actuator commands. Optional UART link to MSPM0; defaults off.
Coordinates are pixels in the 640 x 480 image, not robot coordinates.
See README.md beside this file for calibration and bench acceptance.
"""

# LAB: L_min, L_max, A_min, A_max, B_min, B_max.
# Trial thresholds: lower L admits shaded faces. Still NOT calibrated.
COLORS = (
    ("RED", (15, 96, 20, 127, 10, 127), (255, 0, 0)),
    ("GREEN", (15, 100, -128, -17, -3, 127), (0, 255, 0)),
    ("BLUE", (12, 100, -74, 95, -128, -10), (0, 128, 255)),
    ("YELLOW", (20, 100, -34, 19, 24, 127), (255, 220, 0)),
    ("PURPLE", (12, 96, 18, 127, -128, -8), (220, 90, 255)),
)
WIDTH, HEIGHT = 640, 480
# Restrict this rectangle to the work surface to exclude the green arm.
WORK_ROI = (0, 0, WIDTH, HEIGHT)
# Half-width of the background exclusion band in L*, a*, b*.
BG_TOLERANCE = (6, 6, 6)
# Optional background ranges from calibrate mode, for patterned work surfaces.
BACKGROUND_LAB = ()
MIN_PIXELS = 500
MIN_AREA = 700
MIN_FILL = 0.45
MIN_ASPECT, MAX_ASPECT = 0.5, 2.0
STABLE_FRAMES = 5
MAX_CENTER_STEP = 25
MAX_FRAME_GAP_MS = 400
STABLE_TIME_MS = 250
STABLE_RADIUS = 8             # Max displacement from the stability window's start.
MAX_SIZE_RATIO = 1.5          # Bounding area change also resets stability.
EDGE_MARGIN = 2              # Reject blobs clipped by the ROI or frame boundary.
MAX_AREA_FRACTION = 0.35      # Reject a large colored background.
MAX_CANDIDATES = 30          # Bound Python overlap checks in cluttered scenes.

# detect: recognition; calibrate: LAB sampling; preview: clean camera image.
MODE = "detect"
UART_ENABLED = False         # Enable after standalone vision and wiring checks.
CALIBRATED = False           # Set True only after bench calibration.
CALIBRATION_COLOR = "RED"    # Any color label, or BACKGROUND.
SAMPLE_ROI = (300, 220, 40, 40)
SAMPLE_FRAMES = 20
SAMPLE_PADDING = 5



def validate_settings():
    if MODE not in ("detect", "calibrate", "preview"):
        raise ValueError("MODE must be detect, calibrate or preview")
    for roi in (WORK_ROI, SAMPLE_ROI):
        if len(roi) != 4 or any(type(v) is not int for v in roi):
            raise ValueError("ROI must contain four integers")
        x, y, w, h = roi
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > WIDTH or y + h > HEIGHT:
            raise ValueError("ROI is outside the 640x480 frame")
    if WORK_ROI[2] <= EDGE_MARGIN * 2 or WORK_ROI[3] <= EDGE_MARGIN * 2:
        raise ValueError("WORK_ROI is too small for EDGE_MARGIN")
    names = tuple(c[0] for c in COLORS)
    if names != ("RED", "GREEN", "BLUE", "YELLOW", "PURPLE"):
        raise ValueError("Expected RED, GREEN, BLUE, YELLOW, PURPLE in COLORS")
    if len(BG_TOLERANCE) != 3 or any(type(v) is not int or v < 0 for v in BG_TOLERANCE):
        raise ValueError("Invalid BG_TOLERANCE")
    for name, threshold, color in COLORS + tuple(("BACKGROUND", t, None) for t in BACKGROUND_LAB):
        if len(threshold) != 6 or any(type(v) is not int for v in threshold):
            raise ValueError("LAB threshold must contain six integers: " + name)
        for i, lo, hi in ((0, 0, 100), (2, -128, 127), (4, -128, 127)):
            if not lo <= threshold[i] < threshold[i + 1] <= hi:
                raise ValueError("Invalid LAB range: " + name)
    if CALIBRATION_COLOR not in names + ("BACKGROUND",):
        raise ValueError("Invalid CALIBRATION_COLOR")
    if (MIN_PIXELS <= 0 or MIN_AREA <= 0 or not 0 < MIN_FILL <= 1
            or not 0 < MIN_ASPECT <= MAX_ASPECT or not 0 < MAX_AREA_FRACTION <= 1
            or MAX_CANDIDATES < 1 or STABLE_FRAMES < 2 or STABLE_TIME_MS <= 0
            or MAX_FRAME_GAP_MS <= 0 or MAX_CENTER_STEP <= 0 or STABLE_RADIUS < 0
            or MAX_SIZE_RATIO <= 1 or EDGE_MARGIN < 0 or SAMPLE_FRAMES < 1
            or SAMPLE_PADDING < 0):
        raise ValueError("Invalid detection or sampling settings")


def candidate(blob, name, draw_color):
    """Vendor blob tuple: x, y, w, h, pixels, cx, cy, ... ."""
    x, y, w, h, pixels, cx, cy = blob[0:7]
    # Some K230 firmware returns float centroids; drawing and UART need pixels.
    cx, cy = int(cx), int(cy)
    if w <= 0 or h <= 0:
        return None
    area = w * h
    if pixels < MIN_PIXELS or area < MIN_AREA or pixels > area:
        return None
    if pixels / area < MIN_FILL or not MIN_ASPECT <= w / h <= MAX_ASPECT:
        return None
    rx, ry, rw, rh = WORK_ROI
    if (x <= rx + EDGE_MARGIN or y <= ry + EDGE_MARGIN
            or x + w >= rx + rw - EDGE_MARGIN or y + h >= ry + rh - EDGE_MARGIN
            or area > rw * rh * MAX_AREA_FRACTION):
        return None
    return (name, x, y, w, h, pixels, cx, cy, draw_color)


def overlap(a, b):
    left, top = max(a[1], b[1]), max(a[2], b[2])
    right = min(a[1] + a[3], b[1] + b[3])
    bottom = min(a[2] + a[4], b[2] + b[4])
    intersection = max(0, right - left) * max(0, bottom - top)
    return intersection / min(a[3] * a[4], b[3] * b[4])


def median_lab(img, roi, thresholds=None):
    hist = (img.get_histogram(roi=roi) if thresholds is None
            else img.get_histogram(thresholds, roi=roi))
    p = hist.get_percentile(0.5)
    return p.l_value(), p.a_value(), p.b_value()


def background_ranges(img):
    x, y, w, h = WORK_ROI
    side = min(16, max(1, min(w, h) // 8))
    corners = [median_lab(img, (left, top, side, side))
               for left in (x, x + w - side) for top in (y, y + h - side)]
    ranges = list(BACKGROUND_LAB)
    # Three agreeing corners keep one object or a shadow from setting the mask.
    for sample in corners:
        similar = [c for c in corners if all(abs(c[i] - sample[i]) <= BG_TOLERANCE[i]
                                              for i in range(3))]
        if len(similar) >= 3:
            band = []
            for i, (lo, hi) in enumerate(((0, 100), (-128, 127), (-128, 127))):
                center = sorted(c[i] for c in similar)[len(similar) // 2]
                band.extend((max(lo, center - BG_TOLERANCE[i]), min(hi, center + BG_TOLERANCE[i])))
            # A neutral background usually cannot enter any color mask.
            if any(all(band[i] <= t[i + 1] and t[i] <= band[i + 1] for i in (0, 2, 4))
                   for _, t, _ in COLORS):
                ranges.append(tuple(band))
            break
    return ranges


def detect(img, diagnostics=None):
    ranges = background_ranges(img)
    if ranges:
        img = img.copy()
        img.binary(ranges, zero=True)
    found = []
    thresholds = {name: t for name, t, _ in COLORS}
    neighbors = {"BLUE": "PURPLE", "PURPLE": "BLUE", "GREEN": "YELLOW", "YELLOW": "GREEN"}
    # Complete ALL detection before drawing: overlays must not become targets.
    for name, threshold, draw_color in COLORS:
        for blob in img.find_blobs([threshold], roi=WORK_ROI,
                                   pixels_threshold=MIN_PIXELS,
                                   area_threshold=MIN_AREA, merge=False):
            item = candidate(blob, name, draw_color)
            if item is not None:
                # Use chroma direction only in the shared part of neighboring ranges.
                if name in neighbors:
                    lab = median_lab(img, item[1:5], [threshold])
                    other = thresholds[neighbors[name]]
                    if all(other[2*i] <= v <= other[2*i+1] for i, v in enumerate(lab)):
                        if name in ("BLUE", "PURPLE"):
                            label = "BLUE" if -lab[2] > 1.25 * lab[1] else "PURPLE"
                        else:
                            label = "YELLOW" if lab[2] > -2 * lab[1] else "GREEN"
                        if name != label:
                            continue
                found.append(item)
                if len(found) > MAX_CANDIDATES:
                    if diagnostics is not None:
                        diagnostics["reason"] = "CLUTTER"
                    return []
    # Reject a region that matches two colors; do not guess by color order.
    accepted = sorted(
        [a for a in found if not any(
            a[0] != b[0] and overlap(a, b) > 0.5 for b in found)],
        key=lambda a: a[5], reverse=True)
    if diagnostics is not None:
        diagnostics["reason"] = "COLOR_CONFLICT" if len(accepted) < len(found) else "OK"
    return accepted


def size_matches(a, b):
    ratio = (a[3] * a[4]) / (b[3] * b[4])
    return 1 / MAX_SIZE_RATIO <= ratio <= MAX_SIZE_RATIO


def nearby(a, b, radius):
    return (a[6] - b[6]) ** 2 + (a[7] - b[7]) ** 2 <= radius ** 2


class TargetTracker:
    """Keep a nearby target instead of following fluctuating largest-blob rank."""
    def __init__(self):
        self.previous = None
        self.reacquired = True

    def select(self, targets, gap_ms):
        previous = self.previous
        self.reacquired = True
        if not targets:
            self.previous = None
            return None
        if previous is not None and 0 <= gap_ms <= MAX_FRAME_GAP_MS:
            matches = [t for t in targets if t[0] == previous[0]
                       and nearby(t, previous, MAX_CENTER_STEP) and size_matches(t, previous)]
            if len(matches) > 1:
                # Identity cannot be resolved; start a fresh window next frame.
                self.previous = None
                return None
            if len(matches) == 1:
                self.previous = matches[0]
                self.reacquired = False
                return self.previous
        self.previous = targets[0]
        return self.previous


class Stability:
    def __init__(self):
        self.previous = None
        self.count = 0
        self.anchor = None
        self.elapsed_ms = 0

    def update(self, target, gap_ms, force_reset=False):
        previous = self.previous
        if target is None:
            self.previous, self.count = None, 0
            self.anchor, self.elapsed_ms = None, 0
            return False
        same = (not force_reset and previous is not None and 0 <= gap_ms <= MAX_FRAME_GAP_MS
                and target[0] == previous[0]
                and nearby(target, self.anchor, STABLE_RADIUS)
                and size_matches(target, self.anchor))
        if same:
            self.count = min(STABLE_FRAMES, self.count + 1)
            self.elapsed_ms = min(STABLE_TIME_MS, self.elapsed_ms + gap_ms)
        else:
            self.count, self.elapsed_ms, self.anchor = 1, 0, target
        self.previous = target
        return self.count >= STABLE_FRAMES and self.elapsed_ms >= STABLE_TIME_MS


class DisplayTracks:
    """Confirm each visible block independently, including blocks of the same color."""
    def __init__(self):
        self.windows = []

    def update(self, targets, gap):
        matches = []
        uses = [0] * len(self.windows)
        for target in targets:
            indices = []
            for i, window in enumerate(self.windows):
                prior = window.previous
                if (prior[0] == target[0] and nearby(prior, target, MAX_CENTER_STEP)
                        and size_matches(target, prior)):
                    uses[i] += 1
                    indices.append(i)
            matches.append(indices)

        windows, visible = [], []
        for target, indices in zip(targets, matches):
            if len(indices) == 1 and uses[indices[0]] == 1:
                window = self.windows[indices[0]]
            else:
                window = Stability()
            if window.update(target, gap):
                visible.append(target)
            windows.append(window)
        self.windows = windows
        return visible


class ThresholdSampler:
    """Recent frame percentile medians; suggestions never overwrite thresholds."""
    def __init__(self):
        self.samples = []

    def update(self, img):
        histogram = img.get_histogram(roi=SAMPLE_ROI)
        low, high = histogram.get_percentile(0.1), histogram.get_percentile(0.9)
        self.samples.append((low.l_value(), high.l_value(), low.a_value(),
                             high.a_value(), low.b_value(), high.b_value()))
        if len(self.samples) > SAMPLE_FRAMES:
            self.samples.pop(0)
        if len(self.samples) < SAMPLE_FRAMES:
            return None
        values = [sorted(row[i] for row in self.samples)[len(self.samples) // 2]
                  for i in range(6)]
        limits = ((0, 100), (0, 100), (-128, 127), (-128, 127), (-128, 127), (-128, 127))
        return tuple(max(limits[i][0], min(limits[i][1],
                     values[i] + (-SAMPLE_PADDING if i % 2 == 0 else SAMPLE_PADDING)))
                     for i in range(6))


def main():
    validate_settings()
    import os
    import time
    from libs.PipeLine import PipeLine
    from media.sensor import CAM_CHN_ID_1
    from media.display import Display

    pipeline = PipeLine(rgb888p_size=[WIDTH, HEIGHT],
                        display_size=[WIDTH, HEIGHT], display_mode="lcd")
    stability = Stability()
    tracker = TargetTracker()
    display_tracks = DisplayTracks()
    sampler = ThresholdSampler()
    link = None
    calibration_label = "CAL" if CALIBRATED else "UNCAL"
    try:
        if UART_ENABLED:
            from robot_link import RobotLink
            link = RobotLink()
        pipeline.create()
        time.sleep_ms(1500)
        previous_time = time.ticks_ms()
        last_print = previous_time
        fps_time, fps_frames, fps = previous_time, 0, 0.0
        print("Five-color preview: {}; mode={}; no actuator control; 640x480 pixels".format(
            calibration_label, MODE))
        while True:
            os.exitpoint()
            if link is not None and link.poll():
                tracker = TargetTracker()
                stability = Stability()
            img = pipeline.sensor.snapshot(chn=CAM_CHN_ID_1)
            now = time.ticks_ms()
            gap = time.ticks_diff(now, previous_time)
            previous_time = now
            fps_frames += 1
            period = time.ticks_diff(now, fps_time)
            if period >= 1000:
                fps = fps_frames * 1000 / period
                fps_time, fps_frames = now, 0
            if MODE == "preview":
                Display.show_image(img)
                time.sleep_ms(20)
                continue
            if MODE == "calibrate":
                if gap > MAX_FRAME_GAP_MS or gap < 0:
                    sampler.samples = []
                suggestion = sampler.update(img)  # Sample BEFORE adding any overlay.
                img.draw_rectangle(SAMPLE_ROI, color=(255, 255, 255), thickness=2)
                img.draw_string_advanced(4, 2, 20, "SAMPLE {} {}/{}".format(
                    CALIBRATION_COLOR, len(sampler.samples), SAMPLE_FRAMES), color=(255, 255, 255))
                Display.show_image(img)
                if suggestion is not None and time.ticks_diff(now, last_print) >= 1000:
                    print("SUGGEST,{},{},{}".format(CALIBRATION_COLOR, suggestion, SAMPLE_ROI))
                    last_print = now
                time.sleep_ms(20)
                continue
            diagnostics = {}
            targets = detect(img, diagnostics)
            target = tracker.select(targets, gap)
            stable = stability.update(target, gap, tracker.reacquired)
            for item in display_tracks.update(targets, gap):
                name, x, y, w, h, pixels, cx, cy, color = item
                img.draw_rectangle((x, y, w, h), color=color,
                                   thickness=4 if item is target else 1)
                img.draw_cross(cx, cy, color=color, thickness=2)
                img.draw_string_advanced(x, max(25, y - 24), 20,
                                         "{} {},{}".format(name, cx, cy), color=color)
            img.draw_rectangle(WORK_ROI, color=(180, 180, 180), thickness=1)
            img.draw_string_advanced(4, 2, 20, "{} {:.1f}fps".format(calibration_label, fps),
                                     color=(255, 255, 255))
            Display.show_image(img)
            if time.ticks_diff(now, last_print) >= 200:
                if link is not None:
                    link.send(target, stable, CALIBRATED,
                              not targets and diagnostics['reason'] == 'OK')
                if target is None:
                    print("NONE")
                else:
                    print("DETECT,{},{},{},{},{}".format(
                        target[0], target[6], target[7], target[5], int(stable)))
                last_print = now
            time.sleep_ms(20)
    except KeyboardInterrupt:
        print("Five-color preview stopped")
    finally:
        try:
            pipeline.destroy()
        finally:
            if link is not None:
                link.close()


if __name__ == "__main__":
    main()
