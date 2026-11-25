"""Host regression checks for K230 color segmentation and tracking."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def vision():
    path = Path(__file__).resolve().parents[1] / "vision/k230/three_color_blocks.py"
    spec = importlib.util.spec_from_file_location("three_color_blocks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blob(x=100, y=100, w=40, h=40, pixels=1300):
    return (x, y, w, h, pixels, x + w // 2, y + h // 2)


def target(vision, name="RED", **kwargs):
    result = vision.candidate(blob(**kwargs), name, (255, 0, 0))
    assert result is not None
    return result


class Frame:
    def __init__(self, groups):
        self.groups = iter(groups)
        self.calls = []

    def find_blobs(self, thresholds, **kwargs):
        self.calls.append(kwargs)
        return next(self.groups, [])

    def get_histogram(self, thresholds=None, roi=None):
        lab = (70, 0, 0)
        if thresholds:
            lab = (40, 60, -38) if thresholds[0][2] > 0 else (40, 8, -38)
        return SampleImage(lab, lab)


@pytest.mark.parametrize("values", [
    dict(w=0), dict(w=10, h=10, pixels=50),
    dict(w=100, h=100, pixels=600), dict(w=100, h=20, pixels=1800),
    dict(pixels=1700), dict(x=0), dict(x=600), dict(y=440),
    dict(w=400, h=300, pixels=100000),
])
def test_noise_background_and_clipped_objects_are_rejected(vision, values):
    assert vision.candidate(blob(**values), "RED", None) is None


def test_roi_boundary_is_not_a_complete_block(vision):
    vision.WORK_ROI = (100, 100, 300, 300)
    assert vision.candidate(blob(x=100, y=150), "RED", None) is None
    assert vision.candidate(blob(x=120, y=150), "RED", None) is not None


def test_five_colors_are_detected_without_drawing_on_input(vision):
    frame = Frame([[blob()], [blob(x=200)], [blob(x=300)], [blob(x=400)], [blob(x=500)]])
    results = vision.detect(frame)
    assert {t[0] for t in results} == {"RED", "GREEN", "BLUE", "YELLOW", "PURPLE"}
    assert all(c["roi"] == vision.WORK_ROI and not c["merge"] for c in frame.calls)


def test_color_conflicts_reject_both_but_keep_unrelated_block(vision):
    info = {}
    results = vision.detect(Frame([[blob()], [blob()], [blob(x=300)]]), info)
    assert [t[0] for t in results] == ["BLUE"]
    assert info["reason"] == "COLOR_CONFLICT"


def test_touching_boxes_are_not_color_conflicts(vision):
    assert len(vision.detect(Frame([[blob()], [blob(x=140)], []]))) == 2


def test_clutter_does_not_return_arbitrary_partial_targets(vision):
    info = {}
    assert vision.detect(Frame([[blob()] * (vision.MAX_CANDIDATES + 1)]), info) == []
    assert info["reason"] == "CLUTTER"


def test_empty_scene(vision):
    info = {}
    assert vision.detect(Frame([[], [], []]), info) == []
    assert info["reason"] == "OK"


def test_largest_rank_change_does_not_switch_selected_target(vision):
    tracker = vision.TargetTracker()
    a, b = target(vision), target(vision, x=300)
    assert tracker.select([a, b], 30) is a
    assert tracker.select([b, a], 30) is a
    assert not tracker.reacquired


def test_ambiguous_identity_clears_target(vision):
    tracker = vision.TargetTracker()
    a, b = target(vision), target(vision, x=110)
    tracker.select([a], 30)
    assert tracker.select([a, b], 30) is None
    assert tracker.previous is None


@pytest.mark.parametrize("gap", [-1, 401, 2000])
def test_frame_gap_forces_reacquisition_and_resets_stability(vision, gap):
    tracker, stability = vision.TargetTracker(), vision.Stability()
    a = target(vision)
    for _ in range(6):
        current = tracker.select([a], 60)
        result = stability.update(current, 60, tracker.reacquired)
    assert result
    current = tracker.select([a], gap)
    assert tracker.reacquired
    assert not stability.update(current, gap, tracker.reacquired)
    assert stability.count == 1


def test_stability_requires_time_as_well_as_frame_count(vision):
    stability, a = vision.Stability(), target(vision)
    for _ in range(5):
        assert not stability.update(a, 20)
    for _ in range(9):
        result = stability.update(a, 20)
    assert result


def test_slow_drift_is_not_mistaken_for_stationary_target(vision):
    stability = vision.Stability()
    # Each step is below the old 25px gate, but the object never stops.
    for x in range(100, 200, 3):
        assert not stability.update(target(vision, x=x), 30)


def test_jitter_within_window_is_stable(vision):
    stability = vision.Stability()
    for x in (100, 102, 99, 101, 98, 100):
        result = stability.update(target(vision, x=x), 60)
    assert result


@pytest.mark.parametrize("change", ["color", "size", "lost", "forced"])
def test_changes_clear_stable_state(vision, change):
    stability, a = vision.Stability(), target(vision)
    for _ in range(6):
        assert_result = stability.update(a, 60)
    assert assert_result
    if change == "color":
        a = target(vision, name="BLUE")
    elif change == "size":
        a = target(vision, x=92, y=92, w=56, h=56, pixels=2700)
    elif change == "lost":
        a = None
    assert not stability.update(a, 60, force_reset=change == "forced")


class Percentile:
    def __init__(self, values):
        self.values = values

    def l_value(self):
        return self.values[0]

    def a_value(self):
        return self.values[1]

    def b_value(self):
        return self.values[2]


class SampleImage:
    def __init__(self, low, high):
        self.low, self.high = low, high
        self.roi = None

    def get_histogram(self, roi):
        self.roi = roi
        return self

    def get_percentile(self, percentile):
        return Percentile(self.low if percentile == 0.1 else self.high)


@pytest.fixture
def pixel_frame():
    """Host approximation of the RGB565/LAB operations used by detect()."""
    cv = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    class LabFrame:
        def __init__(self, lab):
            self.lab = lab

        def copy(self):
            return LabFrame(self.lab.copy())

        @staticmethod
        def mask(lab, thresholds):
            hits = np.zeros(lab.shape[:2], dtype=bool)
            for t in thresholds:
                hits |= ((lab >= t[::2]) & (lab <= t[1::2])).all(axis=2)
            return hits

        def binary(self, thresholds, zero):
            assert zero
            self.lab[self.mask(self.lab, thresholds)] = (0, 0, 0)

        def get_histogram(self, thresholds=None, roi=None):
            x, y, w, h = roi
            lab = self.lab[y:y+h, x:x+w]
            pixels = lab[self.mask(lab, thresholds)] if thresholds else lab.reshape(-1, 3)
            median = np.median(pixels, axis=0).astype(int)
            return SampleImage(median, median)

        def find_blobs(self, thresholds, roi, pixels_threshold, area_threshold, merge):
            x, y, w, h = roi
            mask = self.mask(self.lab[y:y+h, x:x+w], thresholds).astype("uint8")
            _, _, stats, centers = cv.connectedComponentsWithStats(mask, connectivity=4)
            return [(x+left, y+top, bw, bh, n, x+cx, y+cy)
                    for (left, top, bw, bh, n), (cx, cy) in zip(stats[1:], centers[1:])
                    if n >= pixels_threshold and bw*bh >= area_threshold]

    def make(background, rectangles):
        rgb = np.full((144, 192, 3), background, dtype="uint8")
        for (x, y, w, h), color in rectangles:
            rgb[y:y+h, x:x+w] = color
        codes = rgb >> (3, 2, 3)
        rgb565 = (codes << (3, 2, 3)) | (codes >> (2, 4, 2))
        return LabFrame(np.rint(cv.cvtColor(rgb565.astype("float32") / 255,
                                             cv.COLOR_RGB2Lab)).astype("int16"))
    return make


@pytest.mark.parametrize("name,color,background", [
    ("RED", (210, 40, 45), (150, 45, 40)),
    ("GREEN", (30, 190, 65), (50, 135, 65)),
    ("BLUE", (0, 0, 255), (45, 40, 175)),
    ("YELLOW", (240, 210, 40), (180, 160, 60)),
    ("PURPLE", (145, 50, 175), (105, 65, 130)),
])
def test_block_on_same_color_surface(vision, pixel_frame, name, color, background):
    vision.WORK_ROI = (8, 8, 176, 128)
    rect = (61, 50, 40, 40)
    frame = pixel_frame(background, [(rect, color)])
    original = frame.lab.copy()
    t = dict((n, threshold) for n, threshold, _ in vision.COLORS)[name]
    assert frame.mask(frame.lab, [t]).all()  # A fixed threshold merges the whole scene.
    targets = vision.detect(frame)
    assert [(v[0], v[1:5]) for v in targets] == [(name, rect)]
    assert (frame.lab == original).all()
    assert not vision.detect(pixel_frame(background, []))


def test_patterned_background_can_use_calibrated_ranges(vision, pixel_frame):
    vision.WORK_ROI = (0, 0, 192, 144)
    yellow_bg = (180, 160, 60)
    frame = pixel_frame(yellow_bg, [((96, 0, 96, 144), (106, 63, 128)),
                                    ((20, 52, 40, 40), (240, 210, 40))])
    assert vision.background_ranges(frame) == []  # Two corners of each color.
    l, a, b = vision.median_lab(frame, (0, 0, 16, 16))
    vision.BACKGROUND_LAB = ((l-4, l+4, a-4, a+4, b-4, b+4),)
    assert [(t[0], t[1:5]) for t in vision.detect(frame)] == [("YELLOW", (20, 52, 40, 40))]


def test_five_separate_blocks_in_one_image(vision, pixel_frame):
    vision.WORK_ROI = (0, 0, 192, 144)
    blocks = [
        ("RED", (210, 40, 45), (12, 12, 32, 32)),
        ("GREEN", (30, 190, 65), (76, 12, 32, 32)),
        ("BLUE", (0, 0, 255), (141, 12, 32, 32)),
        ("YELLOW", (255, 255, 0), (40, 86, 32, 32)),
        ("PURPLE", (145, 50, 175), (110, 86, 32, 32)),
    ]
    frame = pixel_frame((160, 160, 160), [(r, c) for _, c, r in blocks])
    assert {t[0]: t[1:5] for t in vision.detect(frame)} == {n: r for n, _, r in blocks}


def test_sampling_waits_for_enough_frames_and_clamps_lab_ranges(vision):
    sampler = vision.ThresholdSampler()
    img = SampleImage((1, -127, -126), (99, 126, 127))
    for _ in range(vision.SAMPLE_FRAMES - 1):
        assert sampler.update(img) is None
    assert sampler.update(img) == (0, 100, -128, 127, -128, 127)
    assert img.roi == vision.SAMPLE_ROI


def test_sampling_rejects_single_outlier_and_forgets_old_color(vision):
    sampler = vision.ThresholdSampler()
    normal = SampleImage((30, 20, 10), (60, 40, 30))
    for _ in range(vision.SAMPLE_FRAMES):
        expected = sampler.update(normal)
    assert sampler.update(SampleImage((0, -128, -128), (100, 127, 127))) == expected
    other = SampleImage((40, -60, 10), (70, -30, 40))
    for _ in range(vision.SAMPLE_FRAMES):
        result = sampler.update(other)
    assert result == (35, 75, -65, -25, 5, 45)
    assert len(sampler.samples) == vision.SAMPLE_FRAMES


def test_default_settings_are_valid(vision):
    vision.validate_settings()


@pytest.mark.parametrize("name,value", [
    ("WORK_ROI", (-1, 0, 640, 480)), ("WORK_ROI", (0, 0, 641, 480)),
    ("SAMPLE_ROI", (0, 0, 0, 20)), ("SAMPLE_ROI", (0, 0, 4.5, 20)),
    ("MODE", "unknown"), ("SAMPLE_FRAMES", 0), ("MIN_FILL", 1.1),
    ("COLORS", (("RED", (10, 0, 0, 5, 0, 5), None),
                ("GREEN", (0, 100, -128, 127, -128, 127), None),
                ("BLUE", (0, 100, -128, 127, -128, 127), None))),
])
def test_invalid_settings_fail_before_camera_start(vision, name, value):
    setattr(vision, name, value)
    with pytest.raises(ValueError):
        vision.main()


@pytest.fixture
def board_stub(monkeypatch):
    """Exercise loop sequencing and cleanup, not actual board compatibility."""
    import os
    import sys
    from types import ModuleType, SimpleNamespace

    frames, shown, events = [], [], []
    state = {"ticks": 0, "init_error": False}

    class BoardFrame(SampleImage):
        def __init__(self):
            super().__init__((30, 20, 10), (60, 40, 30))
            self.events = []
            self.groups = iter([[blob()], [], [], [], []])

        def find_blobs(self, *args, **kwargs):
            self.events.append("find")
            assert "draw" not in self.events
            return next(self.groups)

        def get_histogram(self, roi):
            self.events.append("sample")
            assert "draw" not in self.events
            if roi[2:] == (16, 16):
                return SampleImage((70, 0, 0), (70, 0, 0))
            return super().get_histogram(roi)

        def draw_rectangle(self, *args, **kwargs):
            self.events.append("draw")

        draw_cross = draw_rectangle
        draw_string_advanced = draw_rectangle

    def snapshot(chn):
        assert chn == 1
        if len(frames) >= 22:
            raise KeyboardInterrupt
        frame = BoardFrame()
        frames.append(frame)
        return frame

    class Pipeline:
        def __init__(self, **kwargs):
            self.sensor = SimpleNamespace(snapshot=snapshot)

        def create(self):
            events.append("create")
            if state["init_error"]:
                raise RuntimeError("camera initialization failed")

        def destroy(self):
            events.append("destroy")

    def ticks_ms():
        state["ticks"] += 60
        return state["ticks"]

    modules = {
        "libs": {}, "libs.PipeLine": {"PipeLine": Pipeline}, "media": {},
        "media.sensor": {"CAM_CHN_ID_1": 1},
        "media.display": {"Display": SimpleNamespace(show_image=shown.append)},
        "time": {"ticks_ms": ticks_ms, "ticks_diff": lambda a, b: a - b,
                 "sleep_ms": lambda ms: None},
    }
    for name, attributes in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(os, "exitpoint", lambda: None, raising=False)
    return frames, shown, events, state


@pytest.mark.parametrize("mode", ["detect", "calibrate", "preview"])
def test_loop_modes_and_keyboard_cleanup(vision, board_stub, capsys, mode):
    frames, shown, events, state = board_stub
    vision.MODE = mode
    vision.main()
    output = capsys.readouterr().out
    assert events == ["create", "destroy"]
    assert len(shown) == len(frames) == 22
    if mode == "detect":
        assert "DETECT,RED,120,120,1300,1" in output
        assert all(f.events[:9] == ["sample"] * 4 + ["find"] * 5 for f in frames)
    elif mode == "calibrate":
        assert "SUGGEST,RED," in output
        assert all(f.events[0] == "sample" for f in frames)
        assert "DETECT," not in output
    else:
        assert all(not f.events for f in frames)
        assert "DETECT," not in output and "SUGGEST," not in output


def test_initialization_failure_attempts_cleanup_and_preserves_error(vision, board_stub):
    frames, shown, events, state = board_stub
    state["init_error"] = True
    with pytest.raises(RuntimeError, match="camera initialization failed"):
        vision.main()
    assert events == ["create", "destroy"]
    assert frames == []
