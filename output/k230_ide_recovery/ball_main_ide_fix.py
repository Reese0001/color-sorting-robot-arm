"""Yahboom CanMV K230 单模型钢球检测入口。

将本文件复制到 TF 卡根目录并命名为 ``main.py`` 后运行。
依赖板卡固件及 TF 卡中的 ``libs`` 目录和 ``/sdcard/model.kmodel``。
"""

KMODEL_PATH = "/sdcard/model.kmodel"
RGB888P_SIZE = [640, 480]
DISPLAY_SIZE = [640, 480]
MODEL_INPUT_SIZE = [640, 640]
LABELS = ["ball"]
GUIDE_CENTER_X = 306
GUIDE_TENTH_MM_PER_PIXEL = 4.552
GUIDE_OFFSET_TENTH_MM = 500


def _as_list(value):
    """Convert ulab arrays and normal Python lists to a common sequence."""
    try:
        return value.tolist()
    except AttributeError:
        return value


def guide_lines():
    """Return LCD x positions for the confirmed -5cm, 0cm and +5cm guides."""
    offset_px = int(round(GUIDE_OFFSET_TENTH_MM / GUIDE_TENTH_MM_PER_PIXEL))
    return (
        (GUIDE_CENTER_X - offset_px, "-5cm"),
        (GUIDE_CENTER_X, "0cm"),
        (GUIDE_CENTER_X + offset_px, "+5cm"),
    )


def draw_guides(osd_img):
    """Draw fixed calibrated reference lines after YOLO clears the OSD image."""
    for x, label in guide_lines():
        osd_img.draw_line(x, 0, x, DISPLAY_SIZE[1] - 1, color=(0, 255, 255), thickness=1)
        osd_img.draw_string_advanced(x + 4, 32, 18, label, color=(0, 255, 255))


def select_ball(result):
    """Return the highest-confidence ball as ``(center_x, confidence_pct)``."""
    if not result or len(result) < 3:
        return None

    boxes, class_ids, confidences = result[0], result[1], result[2]
    count = min(len(boxes), len(class_ids), len(confidences))
    best_box = None
    best_confidence = -1.0

    for index in range(count):
        if int(class_ids[index]) != 0:
            continue
        box = _as_list(boxes[index])
        if len(box) < 4:
            continue
        confidence = float(confidences[index])
        if confidence > best_confidence:
            best_box = box
            best_confidence = confidence

    if best_box is None:
        return None

    center_x = int(float(best_box[0]) + float(best_box[2]) / 2)
    confidence_pct = max(0, min(100, int(round(best_confidence * 100))))
    return center_x, confidence_pct


def run_device():
    """Run camera preview, YOLOv8 inference and LCD result overlay forever."""
    import os
    import gc
    from libs.PipeLine import PipeLine
    from libs.YOLO import YOLOv8

    pipeline = detector = None
    frame = result = None
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        pipeline = PipeLine(
            rgb888p_size=RGB888P_SIZE,
            display_size=DISPLAY_SIZE,
            display_mode="lcd",
        )
        pipeline.create(to_ide=False)

        detector = YOLOv8(
            task_type="detect",
            mode="video",
            kmodel_path=KMODEL_PATH,
            labels=LABELS,
            rgb888p_size=RGB888P_SIZE,
            model_input_size=MODEL_INPUT_SIZE,
            display_size=DISPLAY_SIZE,
            conf_thresh=0.5,
            nms_thresh=0.45,
            max_boxes_num=10,
        )
        detector.config_preprocess()
        print("K230 ball detector ready")

        while True:
            os.exitpoint()
            frame = pipeline.get_frame()
            if frame is None:
                continue

            result = detector.run(frame)
            detector.draw_result(result, pipeline.osd_img)
            draw_guides(pipeline.osd_img)
            ball = select_ball(result)
            if ball is None:
                message = "NO BALL"
                print("ball: none")
            else:
                center_x, confidence_pct = ball
                message = "x={} conf={}%".format(center_x, confidence_pct)
                print("ball:", message)

            pipeline.osd_img.draw_string_advanced(8, 8, 24, message, color=(255, 255, 0))
            pipeline.show_image()
    except KeyboardInterrupt:
        print("K230 ball detector stopped")
    finally:
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        frame = result = None
        try:
            if detector is not None:
                detector.deinit()
        finally:
            detector = None
            try:
                if pipeline is not None:
                    pipeline.destroy()
            finally:
                pipeline = None
                gc.collect()


if __name__ == "__main__":
    run_device()
