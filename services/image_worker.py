"""
图像处理后台线程 v2.3.1
新管线 worker: crop -> pixelize -> quantize -> json
旧 worker: ImageProcessWorkerPyx 保留用于第三方 JSON 兼容
"""

from PySide6.QtCore import QThread, Signal
from core.image.processor import process_pipeline, pixelate_image_simple
from core.utils.logger import get_logger


class ImagePipelineWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, image_path, canvas_mode, brush_type, brush_size, max_colors,
                 offset_x=0, offset_y=0):
        super().__init__()
        self.image_path = image_path
        self.canvas_mode = canvas_mode
        self.brush_type = brush_type
        self.brush_size = brush_size
        self.max_colors = max_colors
        self.offset_x = offset_x
        self.offset_y = offset_y

    def run(self):
        logger = get_logger("ImagePipeline")
        try:
            result = process_pipeline(
                self.image_path, self.canvas_mode, self.brush_type,
                self.brush_size, self.max_colors, self.offset_x, self.offset_y,
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error(str(e), exc_info=True)
            self.error.emit(str(e))


# 保留旧 worker 兼容性
class ImageProcessWorkerPyx(QThread):
    finished = Signal(object, int)
    error = Signal(str)

    def __init__(self, image_path, pixel_size, max_colors, use_preset=False, canvas_mode="standard"):
        super().__init__()
        self.image_path = image_path
        self.pixel_size = pixel_size
        self.max_colors = max_colors
        self.use_preset = use_preset
        self.canvas_mode = canvas_mode

    def run(self):
        logger = get_logger("image_processor")
        try:
            pixel_image, color_palette, color_index_matrix = pixelate_image_simple(
                self.image_path, self.pixel_size, self.max_colors,
                use_preset=self.use_preset, canvas_mode=self.canvas_mode,
            )
            self.finished.emit((pixel_image, color_palette, color_index_matrix), len(color_palette))
        except Exception as e:
            logger.error(str(e), exc_info=True)
            self.error.emit(str(e))
