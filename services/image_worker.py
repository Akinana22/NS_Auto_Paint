"""
图像像素化后台处理线程 v2.2.0
用于在后台线程中执行像素化算法，避免阻塞 UI。
"""

from PySide6.QtCore import QThread, Signal
from core.image.processor import pixelate_image_simple
from core.utils.logger import get_logger


class ImageProcessWorkerPyx(QThread):
    """后台图像处理线程（基于 Pyxelate 或预设调色盘）"""

    finished = Signal(
        object, int
    )  # (pixel_image, color_palette, color_index_matrix), unique_colors
    error = Signal(str)

    def __init__(self, image_path, pixel_size, max_colors, use_preset=False):
        super().__init__()
        self.image_path = image_path
        self.pixel_size = pixel_size
        self.max_colors = max_colors
        self.use_preset = use_preset

    def run(self):
        logger = get_logger("image_processor")
        logger.info(
            f"[后台线程启动] pixel_size={self.pixel_size}, max_colors={self.max_colors}, "
            f"use_preset={self.use_preset}"
        )
        try:
            pixel_image, color_palette, color_index_matrix = pixelate_image_simple(
                self.image_path,
                self.pixel_size,
                self.max_colors,
                use_preset=self.use_preset,
            )
            unique_colors = len(color_palette)
            logger.info(f"[后台线程完成] 实际颜色数: {unique_colors}")
            # 发送元组 (pixel_image, color_palette, color_index_matrix) 和 unique_colors
            self.finished.emit(
                (pixel_image, color_palette, color_index_matrix), unique_colors
            )
        except Exception as e:
            logger.error(f"[后台线程异常] {str(e)}", exc_info=True)
            self.error.emit(str(e))
