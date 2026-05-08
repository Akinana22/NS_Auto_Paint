"""
像素化模块 v2.3.1
笔尖 1px 仅缩放不变效果，>=2px 使用 bilinear 缩小 + nearest 放大。
"""

from PIL import Image


def pixelize(image: Image.Image, brush_type: str, brush_size: int) -> Image.Image:
    if brush_size <= 1:
        return image.copy()
    w, h = image.size
    small_w = max(1, w // brush_size)
    small_h = max(1, h // brush_size)
    small = image.resize((small_w, small_h), Image.BILINEAR)
    return small.resize((w, h), Image.NEAREST)
