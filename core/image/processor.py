"""
图像处理管线 v2.3.1
新管线: crop -> pixelize -> quantize -> json
旧管线: 保留 pixelate_image_simple 用于第三方 JSON 导入（预设色板判断）
"""

import numpy as np
from PIL import Image

from core.utils.logger import get_logger
from core.image.crop import fit_to_canvas, crop_to_region
from core.image.pixelize import pixelize
from core.image.quantize import quantize
from core.image.json_builder import matrix_to_json

logger = get_logger("image_processor")


def process_pipeline(image_path: str, canvas_mode: str, brush_type: str,
                     brush_size: int, max_colors: int, offset_x: int = 0, offset_y: int = 0):
    """完整管线: 裁切 -> 像素化 -> 量化 -> JSON，返回各阶段中间产物"""
    img = Image.open(image_path).convert("RGBA")

    fitted = fit_to_canvas(img, canvas_mode)
    cropped = crop_to_region(fitted, canvas_mode, offset_x, offset_y)
    pixelized = pixelize(cropped, brush_type, brush_size)
    quantized_img, palette, matrix = quantize(pixelized, max_colors)
    json_data = matrix_to_json(matrix, palette, canvas_mode, brush_type, brush_size)

    return {
        "fitted": fitted,
        "cropped": cropped,
        "pixelized": pixelized,
        "quantized": quantized_img,
        "palette": palette,
        "matrix": matrix,
        "json": json_data,
    }


# 保留旧接口兼容第三方 JSON（预设色板判断在 json_importer 中）
def pixelate_image_simple(*args, **kwargs):
    raise NotImplementedError("use process_pipeline instead")
