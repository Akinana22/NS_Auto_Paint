"""
JSON 构建器 v2.3.1
量化矩阵 -> living-the-grid 兼容 JSON。
"""

import numpy as np
from core.image.hsb_mapper import rgb_to_steps
from core.models.canvas_mode import get_canvas_mode

JSON_PRESET = {"standard": "square", "book": "book", "tv": "tv", "game": "videogame", "decoration": "interior"}


def matrix_to_json(matrix, palette, canvas_mode, brush_type, brush_size):
    mode = get_canvas_mode(canvas_mode)
    step = 1 if brush_type == "smooth" else brush_size
    gw = mode.active_w // step
    gh = mode.active_h // step
    h, w = matrix.shape

    jpal = []
    for rgb in palette:
        hs, ss, bs = rgb_to_steps(*rgb)
        if hs == 200:
            hs = 199
        elif hs == 201:
            hs = 0
        jpal.append({"hex": f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}", "rgb": list(rgb), "press": {"h": hs, "s": ss, "b": bs}})

    pixels = []
    for gy in range(0, h, step):
        row = []
        for gx in range(0, w, step):
            idx = -1
            for dy in range(step):
                for dx in range(step):
                    y, x = gy + dy, gx + dx
                    if y < h and x < w and matrix[y, x] >= 0:
                        idx = int(matrix[y, x])
                        break
                if idx >= 0:
                    break
            row.append(idx if idx >= 0 else None)
        pixels.append(row)

    return {"source": "NS Auto Painter v2.3.1", "version": 2, "width": gw, "height": gh,
            "brush": {"mode": brush_type, "px": brush_size},
            "canvas": {"preset": JSON_PRESET.get(canvas_mode, "square"), "w": mode.active_w, "h": mode.active_h},
            "palette": jpal, "pixels": pixels}
