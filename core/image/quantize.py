"""
色彩量化模块 v2.3.1
PNG-8 风格: Median Cut、无仿色、全透/全不透、无半透明、无杂边。
"""

import numpy as np
from PIL import Image


def quantize(image: Image.Image, max_colors: int):
    max_colors = max(2, min(max_colors, 256))
    arr = np.array(image.convert("RGBA"))
    alpha = arr[:, :, 3]
    is_opaque = alpha >= 128
    h, w = is_opaque.shape

    rgb_arr = arr[:, :, :3].copy()
    rgb_arr[~is_opaque] = [0, 0, 0]

    rgb_img = Image.fromarray(rgb_arr, "RGB")
    qi = rgb_img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

    pr = qi.getpalette()
    palette = [[pr[i * 3], pr[i * 3 + 1], pr[i * 3 + 2]] for i in range(256)]

    qa = np.array(qi).astype(np.int16)
    matrix = np.full((h, w), -1, dtype=np.int16)
    matrix[is_opaque] = qa[is_opaque]

    out = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            if matrix[y, x] >= 0:
                c = matrix[y, x]
                out[y, x] = palette[c] + [255]

    return Image.fromarray(out, "RGBA"), palette, matrix
