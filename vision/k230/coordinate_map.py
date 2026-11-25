"""Pixel to printed-map millimetres at the 30 mm cube-top plane.

Measured from output/k230_e_point_blue.png (640 x 480). The paper's
bottom-left A is (0, 0); +X goes to B and +Y goes to D. These are local
paper coordinates, not robot-base coordinates. Recalibrate after moving the
camera, arm observation pose, or target plane.
"""

# Four corner correspondences A, B, C, D from the saved K230 frame.
IMAGE_POINTS = ((177, 341), (446, 308), (403, 32), (186, 53))
MAP_POINTS_MM = ((0, 0), (160, 0), (160, 160), (0, 160))

# The user moved the printed map after measuring base (-75, -170) mm.
# The current map-to-base translation is unknown until remeasured.
BASE_MAP_X_MM = None
BASE_MAP_Y_MM = None

# Homography from cv2.getPerspectiveTransform(IMAGE_POINTS, MAP_POINTS_MM).
H = (
    (0.758033414108, 0.0236885441909, -142.249707866),
    (-0.0715258596315, -0.583044128512, 211.478124977),
    (-0.00000850193695299, 0.000887499282825, 1.0),
)


def pixel_to_map_mm(u, v):
    """Return local map (x, y) in mm, or None outside the printed 160 mm grid."""
    w = H[2][0] * u + H[2][1] * v + H[2][2]
    if abs(w) < 1e-9:
        return None
    x = (H[0][0] * u + H[0][1] * v + H[0][2]) / w
    y = (H[1][0] * u + H[1][1] * v + H[1][2]) / w
    # Keep printed border points despite floating-point roundoff.
    eps = 1e-6
    if not (-eps <= x <= 160 + eps and -eps <= y <= 160 + eps):
        return None
    return (min(160, max(0, x)), min(160, max(0, y)))


def map_to_base_xy_mm(x, y, base_x_mm=BASE_MAP_X_MM,
                      base_y_mm=BASE_MAP_Y_MM):
    """Translate paper coordinates to axes centred on the base yaw joint.

    The returned axes are still parallel to the printed grid. A measured
    base-yaw zero direction is needed before converting these to servo angles.
    """
    if base_x_mm is None or base_y_mm is None:
        raise ValueError("Base-to-A offset must be remeasured after moving the map")
    return (x - base_x_mm, y - base_y_mm)


def necessary_reach_mm(x, y, base_x_mm=BASE_MAP_X_MM,
                       base_y_mm=BASE_MAP_Y_MM, target_z_mm=15):
    """Loose geometric gate only; joint limits and wrist pitch may reject more."""
    import math
    dx, dy = map_to_base_xy_mm(x, y, base_x_mm, base_y_mm)
    return math.sqrt(dx * dx + dy * dy + (target_z_mm - 144) ** 2) <= 405
