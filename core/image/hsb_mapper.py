"""
HSB 映射器 v2.3.1
游戏内选色器非线性感知曲线的校准模型。
全空间暴力建表 (201x213x112) + 欧氏距离最近邻搜索。
LUT 缓存至 assets/hsb_lut.npz，首次生成后续复用。
"""

import os
import numpy as np

from core.utils.logger import get_logger
from core.utils.resource import resource_path

logger = get_logger("hsb_mapper")

HUE_ANCHORS = [
    (0,   "#FF0000"),
    (34,  "#FF00FF"),
    (64,  "#0000FF"),
    (100, "#00FFFF"),
    (136, "#00FF00"),
    (166, "#FFFF00"),
    (200, "#FF0000"),
]

H_MAX = 200
S_MAX = 212
V_MAX = 111

LUT_PATH = "assets/hsb_lut.npz"


def _hex_to_rgb01(hex_str: str) -> np.ndarray:
    h = hex_str.lstrip("#")
    return np.array([int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float64)


def _rgb01_to_h(rgb: np.ndarray) -> float:
    r, g, b = rgb
    mn = min(r, g, b)
    mx = max(r, g, b)
    d = mx - mn
    if d == 0:
        return 0.0
    if mx == r:
        return 60.0 * (((g - b) / d) % 6)
    if mx == g:
        return 60.0 * ((b - r) / d + 2)
    return 60.0 * ((r - g) / d + 4)


def _hsv_to_rgb01(h, s, v):
    if s == 0:
        return np.array([v, v, v], dtype=np.float64)
    h = h / 60.0
    i = int(h)
    f = h - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    lut = {
        0: (v, t, p), 1: (q, v, p), 2: (p, v, t),
        3: (p, q, v), 4: (t, p, v), 5: (v, p, q),
    }
    return np.array(lut.get(i % 6, (0, 0, 0)), dtype=np.float64)


def _hue_angle_for_step(h_step):
    for i in range(len(HUE_ANCHORS) - 1):
        s0, h0 = HUE_ANCHORS[i]
        s1, h1 = HUE_ANCHORS[i + 1]
        if s0 <= h_step <= s1:
            if s1 == s0:
                break
            t = (h_step - s0) / (s1 - s0)
            hue0 = _rgb01_to_h(_hex_to_rgb01(h0))
            hue1 = _rgb01_to_h(_hex_to_rgb01(h1))
            if abs(hue1 - hue0) > 180:
                if hue0 < hue1:
                    hue0 += 360
                else:
                    hue1 += 360
            hue = hue0 + t * (hue1 - hue0)
            return hue % 360
    return 0.0


def _saturation_for_step(s_step):
    p = max(0.0, min(1.0, s_step / S_MAX))
    if p == 0:
        return 0.0
    s = 0.49 * p + 0.2 * (p ** 38) + 0.31 * (p ** 3.9)
    return max(0.0, min(1.0, s))


def _brightness_for_step(b_step):
    p = max(0.0, min(1.0, b_step / V_MAX))
    if p == 0:
        return 0.0
    return p ** (1.0 / 2.26)


def _build_lut():
    logger.info("构建 HSB LUT ...")
    lut = np.zeros((H_MAX + 1, S_MAX + 1, V_MAX + 1, 3), dtype=np.int16)
    for h_s in range(H_MAX + 1):
        hue = _hue_angle_for_step(h_s)
        for s_s in range(S_MAX + 1):
            sat = _saturation_for_step(s_s)
            for b_s in range(V_MAX + 1):
                val = _brightness_for_step(b_s)
                rgb = _hsv_to_rgb01(hue, sat, val)
                lut[h_s, s_s, b_s] = [int(round(rgb[i] * 255)) for i in range(3)]
        if h_s % 20 == 0:
            logger.info(f"  H: {h_s}/{H_MAX}")
    logger.info("HSB LUT 完成")
    return lut


_lut = None


def get_lut():
    global _lut
    if _lut is not None:
        return _lut
    rp = resource_path(LUT_PATH)
    if os.path.exists(rp):
        logger.info(f"加载 LUT: {rp}")
        _lut = np.load(rp)["lut"]
    else:
        _lut = _build_lut()
        os.makedirs(os.path.dirname(resource_path(LUT_PATH)), exist_ok=True)
        np.savez_compressed(resource_path(LUT_PATH), lut=_lut)
        logger.info(f"LUT 已保存")
    return _lut


def rgb_to_steps(r, g, b):
    lut = get_lut()
    diff = lut.astype(np.int32) - np.array([r, g, b], dtype=np.int32)
    dist_sq = diff[:, :, :, 0]**2 + diff[:, :, :, 1]**2 + diff[:, :, :, 2]**2
    idx = np.argmin(dist_sq)
    h_s, s_s, b_s = np.unravel_index(idx, (H_MAX + 1, S_MAX + 1, V_MAX + 1))
    return int(h_s), int(s_s), int(b_s)
