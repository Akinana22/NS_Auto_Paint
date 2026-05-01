"""
批量图片格式转换后台线程 v2.2.0
"""

import os
from PIL import Image
from PySide6.QtCore import QThread, Signal


class BatchConvertWorker(QThread):
    """后台批量转换图片格式的线程"""

    progress = Signal(int, str)  # 进度百分比, 当前文件名
    finished = Signal(int, int)  # 成功数量, 失败数量
    error = Signal(str)  # 错误信息

    def __init__(self, file_list, target_format, quality, output_dir, sizes=None):
        super().__init__()
        self.file_list = file_list
        self.target_format = target_format
        self.quality = quality
        self.output_dir = output_dir
        self.sizes = sizes or []  # ICO 多分辨率 [(16,16), (32,32), ...]

    def run(self):
        success_count = 0
        fail_count = 0
        total = len(self.file_list)

        for idx, file_path in enumerate(self.file_list):
            progress_pct = int((idx / total) * 100)
            self.progress.emit(progress_pct, os.path.basename(file_path))

            try:
                img = Image.open(file_path)

                # 处理 ICO 多分辨率
                if self.target_format.upper() == "ICO" and self.sizes:
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    output_path = os.path.join(self.output_dir, f"{base_name}.ico")
                    img.save(output_path, format="ICO", sizes=self.sizes)
                else:
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    output_ext = self.target_format.lower()
                    if output_ext == "jpg":
                        output_ext = "jpeg"
                    output_path = os.path.join(
                        self.output_dir, f"{base_name}.{output_ext}"
                    )

                    # RGB 格式不支持透明度，需转换
                    if (
                        self.target_format.upper() in ("JPEG", "JPG", "BMP")
                        and img.mode == "RGBA"
                    ):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])
                        img = background
                    elif img.mode == "P":
                        img = img.convert("RGB")

                    save_kwargs = {}
                    if self.target_format.upper() in ("JPEG", "JPG"):
                        save_kwargs["quality"] = self.quality
                    elif self.target_format.upper() == "PNG":
                        save_kwargs["compress_level"] = 9 - int(self.quality / 10)
                    elif self.target_format.upper() == "WEBP":
                        save_kwargs["quality"] = self.quality
                        save_kwargs["method"] = 6

                    img.save(
                        output_path, format=self.target_format.upper(), **save_kwargs
                    )

                success_count += 1
            except Exception as e:
                fail_count += 1
                self.error.emit(f"{os.path.basename(file_path)}: {str(e)}")

        self.progress.emit(100, "完成")
        self.finished.emit(success_count, fail_count)
