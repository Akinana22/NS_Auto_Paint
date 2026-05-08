"""
裁切模块 v2.3.1
原图保持宽高比缩放到画布有效区，支持用户拖动偏移裁切。
"""

from PIL import Image
from core.models.canvas_mode import get_canvas_mode


def fit_to_canvas(image: Image.Image, canvas_mode: str) -> Image.Image:
    mode = get_canvas_mode(canvas_mode)
    cw, ch = mode.active_w, mode.active_h
    iw, ih = image.size
    scale = max(cw / iw, ch / ih)
    new_w = max(1, int(iw * scale))
    new_h = max(1, int(ih * scale))
    return image.resize((new_w, new_h), Image.LANCZOS)


def crop_to_region(image: Image.Image, left: int, top: int, right: int, bottom: int) -> Image.Image:
    return image.crop((left, top, right, bottom))
