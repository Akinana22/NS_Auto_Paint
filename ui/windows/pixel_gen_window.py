"""
像素图生成窗口 v2.3.1
全新管线: 上传 → 裁切 → 像素化 → 限制色彩 → 生成JSON → 渲染JSON
支持第三方 JSON 导入及画布模式。
"""

import os, json, time
import numpy as np
from PIL import Image

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QSlider, QFileDialog,
    QTextEdit, QMessageBox, QComboBox, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QIcon, QBrush, QImage, QWheelEvent, QFont

from core.utils.logger import get_logger
from core.utils.resource import resource_path
from core.image.json_importer import JsonImporter
from core.image.preset_palette import get_preset_palette, get_preset_color_count
from core.scheduling.optimizer import SchedulingOptimizer
from core.scheduling.timing_config import TimingConfig
from core.models.canvas_mode import get_canvas_mode
from ui.widgets.canvas_preview import CanvasPreview


PIPELINE_STAGES = ["upload", "crop", "pixelize", "limit_colors", "generate_json"]


class MainPage(QWidget):
    drawing_data_ready = Signal(object, object, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("MainPage")

        self.json_loaded = False
        self.json_matrix = None
        self.json_palette = None
        self.json_metadata = {}
        self.json_file_path = None

        self.brush_type = "smooth"
        self.brush_size = 1
        self.smooth_sizes = [1, 3, 7, 13, 19, 27]
        self.pixel_sizes = [4, 8, 16, 32]
        self.current_brush_sizes = self.smooth_sizes
        self.press_data = None

        self.canvas_mode = "standard"
        self.canvas_mode_names = {
            "standard": "标准", "book": "书籍", "tv": "电视",
            "game": "游戏", "decoration": "装修",
        }
        self._current_preview_pixmap = None

        self.generated_is_preset = False
        self.drawing_mode = "image"
        self.color_index_matrix = None
        self.color_palette = None

        self._pipeline_stage = 0
        self._orig_image_path = None
        self._fitted_image = None
        self._cropped_image = None
        self._pixelized_image = None
        self._quantized_image = None
        self._pipeline_palette = None
        self._pipeline_matrix = None
        self._pipeline_json = None
        self._crop_offset_x = 0
        self._crop_offset_y = 0

        self.setup_ui()
        self.apply_style()
        self.connect_signals()
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ========== LEFT: 运行日志 ==========
        left_panel = QVBoxLayout()
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setPlaceholderText("操作日志...")
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.log_text, 1)
        log_group.setLayout(log_layout)
        left_panel.addWidget(log_group)

        # ========== MIDDLE: 预览 ==========
        middle_panel = QVBoxLayout()
        self._preview_group = QGroupBox("预览")
        f = self._preview_group.font()
        f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        self._preview_group.setFont(f)
        preview_layout = QVBoxLayout()
        self.canvas_preview = CanvasPreview()
        self.canvas_preview.setMinimumSize(256, 256)
        preview_layout.addWidget(self.canvas_preview, 1)
        self._preview_group.setLayout(preview_layout)
        middle_panel.addWidget(self._preview_group)

        action_layout = QHBoxLayout()
        self.btn_export = QPushButton("\U0001f4be 导出")
        self.btn_export.setEnabled(False)
        self.btn_confirm = QPushButton("\U0001f4cc 定稿")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setObjectName("confirm_btn")
        action_layout.addWidget(self.btn_export)
        action_layout.addWidget(self.btn_confirm)
        middle_panel.addLayout(action_layout)

        # ========== RIGHT ==========
        right_panel = QVBoxLayout()

        # 图片处理设置
        img_group = QGroupBox("\U0001f47e 图片处理设置")
        img_layout = QVBoxLayout()

        cl = QHBoxLayout()
        cl.addWidget(QLabel("画布模式:"))
        self.canvas_mode_combo = QComboBox()
        self.canvas_mode_combo.addItems(["标准", "书籍", "电视", "游戏", "装修"])
        self.canvas_mode_combo.setCurrentIndex(0)
        self.canvas_mode_combo.currentIndexChanged.connect(self._on_canvas_mode_changed)
        cl.addWidget(self.canvas_mode_combo)
        img_layout.addLayout(cl)

        self._color_values = [2, 4, 8, 16, 32, 64, 128, 256]
        self.color_count_label = QLabel("最大颜色数: 16")
        self.color_slider = QSlider(Qt.Horizontal)
        self.color_slider.setRange(0, len(self._color_values) - 1)
        self.color_slider.setValue(3)
        self.color_slider.setTickPosition(QSlider.TicksBelow)
        self.color_slider.setTickInterval(1)
        self.color_slider.setPageStep(1)
        self.color_slider.setSingleStep(1)
        self.color_slider.valueChanged.connect(self._on_color_slider_changed)
        _color_row = QVBoxLayout()
        _color_row.setSpacing(0)
        _color_row.addWidget(self.color_count_label)
        _color_row.addWidget(self.color_slider)
        img_layout.addLayout(_color_row)

        self.btn_upload = QPushButton("\U0001f4c1 上传图片")
        self.btn_crop = QPushButton("\u2702\ufe0f 裁切")
        self.btn_pixelize = QPushButton("\U0001f532 像素化")
        self.btn_limit_colors = QPushButton("\U0001f3a8 限制色彩")
        self.btn_crop.setEnabled(False)
        self.btn_pixelize.setEnabled(False)
        self.btn_limit_colors.setEnabled(False)

        img_layout.addWidget(self.btn_upload)
        img_layout.addWidget(self.btn_crop)
        img_layout.addWidget(self.btn_pixelize)
        img_layout.addWidget(self.btn_limit_colors)

        img_group.setLayout(img_layout)
        right_panel.addWidget(img_group)

        self.btn_open_website = QPushButton("\U0001f310 推荐！打开第三方像素化网页")
        right_panel.addWidget(self.btn_open_website)

        # JSON处理
        json_group = QGroupBox("\U0001f4c4 JSON处理")
        json_layout = QVBoxLayout()

        bl = QHBoxLayout()
        self.btn_smooth_brush = QPushButton("顺滑画笔")
        self.btn_pixel_brush = QPushButton("像素画笔")
        bl.addWidget(self.btn_smooth_brush)
        bl.addWidget(self.btn_pixel_brush)
        json_layout.addLayout(bl)

        self.btn_smooth_brush.setProperty("active", True)
        self.btn_pixel_brush.setProperty("active", False)
        self.btn_smooth_brush.setEnabled(False)
        self.btn_pixel_brush.setEnabled(True)

        self.brush_size_label = QLabel("笔尖大小: 1")
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setRange(0, len(self.current_brush_sizes) - 1)
        self.brush_size_slider.setValue(0)
        self.brush_size_slider.setTickPosition(QSlider.TicksBelow)
        self.brush_size_slider.setTickInterval(1)
        self.brush_size_slider.setPageStep(1)
        self.brush_size_slider.setSingleStep(1)
        self.brush_size_slider.valueChanged.connect(self._on_brush_size_changed)
        _brush_row = QVBoxLayout()
        _brush_row.setSpacing(0)
        _brush_row.addWidget(self.brush_size_label)
        _brush_row.addWidget(self.brush_size_slider)
        json_layout.addLayout(_brush_row)

        gr = QHBoxLayout()
        self.btn_generate_json = QPushButton("\U0001f4dd 生成JSON")
        self.btn_upload_json = QPushButton("\U0001f4c1 上传JSON")
        self.btn_generate_json.setEnabled(False)
        gr.addWidget(self.btn_generate_json)
        gr.addWidget(self.btn_upload_json)
        json_layout.addLayout(gr)

        self.btn_render_json = QPushButton("\u2699\ufe0f 渲染JSON")
        self.btn_render_json.setEnabled(False)
        json_layout.addWidget(self.btn_render_json)

        json_group.setLayout(json_layout)
        right_panel.addWidget(json_group)
        right_panel.addStretch()

        main_layout.addLayout(left_panel, 2)
        main_layout.addLayout(middle_panel, 3)
        main_layout.addLayout(right_panel, 2)

    def apply_style(self):
        self.setStyleSheet("""
            QGroupBox { font-family: "Microsoft YaHei UI"; border: 1px solid #aaa; border-radius: 5px; margin-top: 6px; padding: 2px; background-color: rgba(255, 255, 255, 200); }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; background-color: transparent; font-family: "Microsoft YaHei UI"; font-weight: 500; }
            QPushButton { background-color: rgba(255, 255, 255, 220); border: 1px solid #ccc; border-radius: 5px; padding: 5px; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 255); }
            QPushButton:disabled { background-color: rgba(200, 200, 200, 150); color: #888; }
            QPushButton[active="true"] { background-color: #E60012; color: white; font-weight: bold; border: 1px solid #c00010; }
            QPushButton[active="true"]:hover { background-color: #c00010; }
            QPushButton#confirm_btn { background-color: #E60012; color: white; font-weight: bold; }
            QPushButton#confirm_btn:hover { background-color: #c00010; }
            QPushButton#confirm_btn:disabled { background-color: #aaa; }
            QTextEdit { background-color: rgba(255, 255, 255, 200); }
            QComboBox {
                border: 1px solid #aaa; border-radius: 4px;
                padding: 3px 24px 3px 8px;
                background: rgba(255,255,255,220);
                font-family: "Microsoft YaHei UI"; min-width: 60px;
            }
            QComboBox:hover { border: 1px solid #888; background: rgba(255,255,255,255); }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 20px; border-left: 1px solid #ccc;
                border-top-right-radius: 4px; border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow { width: 10px; height: 10px; }
            QComboBox QAbstractItemView {
                border: 1px solid #aaa; border-radius: 3px;
                padding: 2px; background: rgba(255,255,255,240); outline: none;
            }
        """)

    def connect_signals(self):
        self.color_slider.valueChanged.connect(self._on_color_slider_changed)
        self.btn_upload.clicked.connect(self.on_upload)
        self.btn_crop.clicked.connect(self.on_crop)
        self.btn_pixelize.clicked.connect(self.on_pixelize)
        self.btn_limit_colors.clicked.connect(self.on_limit_colors)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_confirm.clicked.connect(self.on_confirm)
        self.btn_smooth_brush.clicked.connect(self._on_smooth_mode)
        self.btn_pixel_brush.clicked.connect(self._on_pixel_mode)
        self.btn_upload_json.clicked.connect(self.on_upload_json)
        self.btn_render_json.clicked.connect(self.on_render_json)
        self.btn_generate_json.clicked.connect(self.on_generate_json)
        self.btn_open_website.clicked.connect(self.on_open_pixel_website)

    def _on_color_slider_changed(self, v):
        if 0 <= v < len(self._color_values):
            self.color_count_label.setText(f"最大颜色数: {self._color_values[v]}")

    # ========== 管线 ==========

    def _update_stage_buttons(self):
        s = self._pipeline_stage
        self.btn_crop.setEnabled(s >= 1)
        self.btn_pixelize.setEnabled(s >= 2)
        self.btn_limit_colors.setEnabled(s >= 3)
        self.btn_generate_json.setEnabled(s >= 4)

    def _update_preview_title(self):
        mode = get_canvas_mode(self.canvas_mode)
        nm = self.canvas_mode_names.get(self.canvas_mode, "标准")
        if self._pipeline_stage >= 5 and self._pipeline_json:
            j = self._pipeline_json
            self._preview_group.setTitle(
                f"预览 - 画布: {nm} {mode.active_w}x{mode.active_h}  网格: {j['width']}x{j['height']}")
        else:
            self._preview_group.setTitle(
                f"预览 - 画布: {nm} {mode.active_w}x{mode.active_h}")

    def on_upload(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        self._orig_image_path = path
        self._pipeline_stage = 1
        self._update_stage_buttons()
        self._update_preview_title()
        img = Image.open(path).convert("RGBA")
        self.canvas_preview.setSourceImage(img, self.canvas_mode)
        self._current_preview_pixmap = QPixmap(path)
        self.log(f"已上传: {os.path.basename(path)}")

    def on_crop(self):
        fitted = self.canvas_preview.getFittedImage()
        if fitted is None:
            return
        l, t, r, b = self.canvas_preview.getCropPixels()
        self._cropped_image = fitted.crop((l, t, r, b))
        self.log(f"[裁切] fitted={fitted.size} crop=({l},{t},{r},{b}) result={self._cropped_image.size}")
        self._pipeline_stage = 2
        self._update_stage_buttons()
        buf = self._cropped_image.tobytes("raw", "RGBA")
        qi = QImage(buf, self._cropped_image.width, self._cropped_image.height, QImage.Format_RGBA8888)
        self._current_preview_pixmap = QPixmap.fromImage(qi)
        self.canvas_preview.setPixmap(self._current_preview_pixmap)
        self.canvas_preview.setCanvasMode(self.canvas_mode)
        self.canvas_preview.setCropMode(False)
        self._update_preview_title()
        self.btn_export.setEnabled(True)
        self.log(f"裁切完成: {self._cropped_image.width}x{self._cropped_image.height}")

    def on_pixelize(self):
        from core.image.pixelize import pixelize
        if self._cropped_image is None:
            return
        self._pixelized_image = pixelize(self._cropped_image, self.brush_type, self.brush_size)
        self._pipeline_stage = 3
        self._update_stage_buttons()
        buf = self._pixelized_image.tobytes("raw", "RGBA")
        qi = QImage(buf, self._pixelized_image.width, self._pixelized_image.height, QImage.Format_RGBA8888)
        self._current_preview_pixmap = QPixmap.fromImage(qi)
        self.canvas_preview.setPixmap(self._current_preview_pixmap)
        self.log(f"像素化完成: {self.brush_type} {self.brush_size}px")

    def on_limit_colors(self):
        from core.image.quantize import quantize
        if self._pixelized_image is None:
            return
        mc = self._color_values[self.color_slider.value()]
        qi_img, pal, mat = quantize(self._pixelized_image, mc)
        self._quantized_image = qi_img
        self._pipeline_palette = pal
        self._pipeline_matrix = mat
        self._pipeline_stage = 4
        self._update_stage_buttons()
        buf = qi_img.tobytes("raw", "RGBA")
        qi = QImage(buf, qi_img.width, qi_img.height, QImage.Format_RGBA8888)
        self._current_preview_pixmap = QPixmap.fromImage(qi)
        self.canvas_preview.setPixmap(self._current_preview_pixmap)
        self.log(f"限制色彩完成: {len(pal)} 色")

    def on_generate_json(self):
        from core.image.json_builder import matrix_to_json
        if self._pipeline_matrix is None or self._pipeline_palette is None:
            return
        jd = matrix_to_json(self._pipeline_matrix, self._pipeline_palette,
                           self.canvas_mode, self.brush_type, self.brush_size)
        self._pipeline_json = jd
        self.color_index_matrix = np.asarray(self._pipeline_matrix, dtype=np.int16)
        self.color_palette = self._pipeline_palette

        scripts_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(scripts_dir, f"generated_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as fout:
            json.dump(jd, fout, ensure_ascii=False, indent=2)

        self.json_file_path = json_path
        self.json_loaded = True
        self.json_matrix = np.asarray(self._pipeline_matrix, dtype=np.int16)
        self.json_palette = self._pipeline_palette
        self.drawing_mode = "json"
        self.generated_is_preset = False
        self.press_data = [c["press"] for c in jd["palette"]]

        self._pipeline_stage = 5
        self._update_stage_buttons()
        self.btn_render_json.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_confirm.setEnabled(True)
        self._update_preview_title()
        self.log(f"JSON已生成: {json_path}")

    # ========== 第三方 JSON ==========

    def on_upload_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 JSON 文件", "", "JSON 文件 (*.json)")
        if not file_path:
            return
        self.json_file_path = file_path
        self._import_json_with_current_settings()
        if self.json_metadata:
            self._apply_json_brush_settings(self.json_metadata)
            self._apply_json_canvas_settings(self.json_metadata)
        self.log(f"已上传 JSON: {os.path.basename(self.json_file_path)}")
        self.log(f"  画笔: {self.brush_type} {self.brush_size}px, 尺寸: {self.json_metadata['width']}x{self.json_metadata['height']}")
        self.logger.info(f"上传 JSON: {os.path.basename(self.json_file_path)}")

    def _apply_json_brush_settings(self, metadata: dict):
        json_brush_type = metadata.get("json_brush_type")
        json_brush_size = metadata.get("json_brush_size")
        if json_brush_type is None or json_brush_size is None:
            return
        if json_brush_type == "smooth":
            if json_brush_size not in self.smooth_sizes:
                self.logger.warning(f"不支持的顺滑画笔尺寸（JSON）: {json_brush_size}")
                return
            self._on_smooth_mode()
            idx = self.smooth_sizes.index(json_brush_size)
            self.brush_size_slider.setValue(idx)
            self.brush_size = json_brush_size
            self.brush_size_label.setText(f"笔尖大小: {json_brush_size}")
        elif json_brush_type == "pixel":
            if json_brush_size not in self.pixel_sizes:
                self.logger.warning(f"不支持的像素画笔尺寸（JSON）: {json_brush_size}")
                return
            self._on_pixel_mode()
            idx = self.pixel_sizes.index(json_brush_size)
            self.brush_size_slider.setValue(idx)
            self.brush_size = json_brush_size
            self.brush_size_label.setText(f"笔尖大小: {json_brush_size}")

    def _apply_json_canvas_settings(self, metadata: dict):
        canvas_mode_key = metadata.get("canvas_mode")
        if canvas_mode_key and canvas_mode_key != self.canvas_mode:
            self.canvas_mode = canvas_mode_key
            display_name = self.canvas_mode_names.get(canvas_mode_key, "标准")
            idx = self.canvas_mode_combo.findText(display_name)
            if idx >= 0:
                self.canvas_mode_combo.setCurrentIndex(idx)
            self.log(f"  画布模式: {display_name}")

    def _import_json_with_current_settings(self):
        if not self.json_file_path:
            return
        importer = JsonImporter()
        matrix, palette, metadata = importer.load_from_file(
            self.json_file_path, self.brush_type, self.brush_size, canvas_mode=self.canvas_mode,
        )
        if matrix is None:
            QMessageBox.critical(self, "导入失败", metadata.get("error", "未知错误"))
            return
        self.json_matrix = matrix
        self.json_palette = palette
        self.json_metadata = metadata
        self.json_loaded = True
        self.btn_render_json.setEnabled(True)
        self.press_data = metadata.get("press_data")
        self.drawing_mode = "json"
        self.generated_is_preset = metadata.get("all_preset", False)
        self.log(f"JSON 导入完成，有效像素数: {metadata['total_pixels']}")
        self.logger.info(f"渲染 JSON: {os.path.basename(self.json_file_path)}")

    def on_render_json(self):
        if not self.json_loaded or self.json_matrix is None:
            QMessageBox.warning(self, "提示", "请先上传或生成 JSON。")
            return
        self._import_json_with_current_settings()
        if self.json_matrix is None:
            return
        self._update_preview_from_matrix()
        self.btn_export.setEnabled(True)
        self.btn_confirm.setEnabled(True)
        nm = self.canvas_mode_names.get(self.canvas_mode, "标准")
        mode = get_canvas_mode(self.canvas_mode)
        j = self.json_metadata
        if j.get("canvas_mode"):
            nm = self.canvas_mode_names.get(j["canvas_mode"], nm)
            mode = get_canvas_mode(j["canvas_mode"])
        self._preview_group.setTitle(
            f"预览 - 画布: {nm} {mode.active_w}x{mode.active_h}  网格: {j['width']}x{j['height']}")
        self.log("JSON 渲染完成，预览已更新。")

    def _update_preview_from_matrix(self):
        matrix = self.json_matrix
        palette = self.json_palette
        h, w = matrix.shape
        img_array = np.zeros((h, w, 4), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                idx = matrix[y, x]
                if idx >= 0 and idx < len(palette):
                    r, g, b = palette[idx]
                    img_array[y, x] = [r, g, b, 255]
        qimage = QImage(img_array.data, w, h, w * 4, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        self.canvas_preview.setPixmap(pixmap)
        self.canvas_preview.setCanvasMode(self.canvas_mode)
        self._current_preview_pixmap = pixmap
        self.color_index_matrix = matrix
        self.color_palette = palette

    # ========== 导出 / 定稿 ==========

    def on_export(self):
        if self._current_preview_pixmap is None:
            QMessageBox.warning(self, "提示", "没有可导出的内容。")
            return
        if self._pipeline_stage >= 5 and self._pipeline_json:
            default_name = "pixel_image.json"
            save_path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", default_name, "JSON 文件 (*.json)")
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(self._pipeline_json, f, ensure_ascii=False, indent=2)
                self.log(f"JSON已导出: {save_path}")
            return
        default_name = "pixel_image.png"
        if self._orig_image_path:
            base = os.path.splitext(os.path.basename(self._orig_image_path))[0]
            default_name = f"{base}_pixel.png"
        save_path, _ = QFileDialog.getSaveFileName(self, "导出图片", default_name, "PNG 图片 (*.png)")
        if not save_path:
            return
        try:
            self._current_preview_pixmap.save(save_path, "PNG")
            self.log(f"已导出: {save_path}")
        except Exception as e:
            self.logger.error(f"导出失败: {e}")

    def on_confirm(self):
        if self.color_index_matrix is None:
            QMessageBox.warning(self, "提示", "请先生成或渲染 JSON。")
            return

        timing = TimingConfig.snapshot()
        optimizer = SchedulingOptimizer()
        try:
            if self.drawing_mode == "json" and self.brush_size:
                step = self.brush_size
                grid_h = self.color_index_matrix.shape[0] // step
                grid_w = self.color_index_matrix.shape[1] // step
                grid_matrix = self.color_index_matrix[::step, ::step]
            else:
                grid_h = self.color_index_matrix.shape[0]
                grid_w = self.color_index_matrix.shape[1]
                grid_matrix = self.color_index_matrix

            best_schedule, best_desc, logs = optimizer.find_best_schedule(
                grid_matrix,
                self.brush_type if self.drawing_mode == "json" else None,
                self.brush_size if self.drawing_mode == "json" else None,
                self.generated_is_preset, grid_w, grid_h,
                palette=self.color_palette,
                press_data=getattr(self, "press_data", None),
                timing=timing,
            )
            if best_schedule is None:
                QMessageBox.warning(self, "错误", "无法生成调度方案。")
                return

            total_ms = optimizer.estimate_schedule_cost(
                best_schedule,
                self.brush_type if self.drawing_mode == "json" else None,
                self.brush_size if self.drawing_mode == "json" else None,
                self.generated_is_preset, grid_w, grid_h,
                palette=self.color_palette,
                press_data=getattr(self, "press_data", None),
                timing=timing,
            )
            total_sec = total_ms / 1000.0
            minutes = int(total_sec // 60)
            seconds = int(total_sec % 60)
            estimate = {
                "total_ms": total_ms, "best_desc": best_desc,
                "evaluation_log": logs,
                "formatted_time": f"{minutes} 分 {seconds} 秒",
            }
        except Exception as e:
            self.logger.error(f"评估失败: {e}")
            QMessageBox.critical(self, "错误", f"评估绘图耗时失败: {e}")
            return

        if not self._show_estimate_dialog(estimate):
            return

        self.log("准备开始绘图...")
        self.drawing_data_ready.emit(
            self.color_index_matrix, self.color_palette,
            64, self.generated_is_preset,
        )

    def _show_estimate_dialog(self, estimate):
        msg = (
            f"【最优方案】{estimate.get('best_desc', '未知')}\n"
            f"预估总耗时：{estimate.get('formatted_time', '?')}\n\n"
            f"── 所有方案评估 ──\n"
            + "\n".join(estimate.get("evaluation_log", []))
            + "\n\n是否立即开始绘制？"
        )
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("绘图预估")
        msg_box.setText(msg)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.Yes)
        msg_box.setMinimumWidth(550)
        return msg_box.exec() == QMessageBox.Yes

    # ========== brush / canvas utils ==========

    def _on_smooth_mode(self):
        self.brush_type = "smooth"
        self.current_brush_sizes = self.smooth_sizes
        old_value = min(self.brush_size_slider.value(), len(self.smooth_sizes) - 1)
        self.brush_size_slider.setRange(0, len(self.smooth_sizes) - 1)
        self.brush_size_slider.setValue(old_value)
        self.brush_size = self.smooth_sizes[old_value]
        self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")
        self.btn_smooth_brush.setProperty("active", True)
        self.btn_pixel_brush.setProperty("active", False)
        self.btn_smooth_brush.setEnabled(False)
        self.btn_pixel_brush.setEnabled(True)
        self._restyle_buttons()

    def _on_pixel_mode(self):
        self.brush_type = "pixel"
        self.current_brush_sizes = self.pixel_sizes
        old_value = min(self.brush_size_slider.value(), len(self.pixel_sizes) - 1)
        self.brush_size_slider.setRange(0, len(self.pixel_sizes) - 1)
        self.brush_size_slider.setValue(old_value)
        self.brush_size = self.pixel_sizes[old_value]
        self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")
        self.btn_smooth_brush.setProperty("active", False)
        self.btn_pixel_brush.setProperty("active", True)
        self.btn_smooth_brush.setEnabled(True)
        self.btn_pixel_brush.setEnabled(False)
        self._restyle_buttons()

    def _restyle_buttons(self):
        for btn in [self.btn_smooth_brush, self.btn_pixel_brush]:
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_brush_size_changed(self, idx):
        if 0 <= idx < len(self.current_brush_sizes):
            self.brush_size = self.current_brush_sizes[idx]
            self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")

    def _on_canvas_mode_changed(self, idx):
        modes = list(self.canvas_mode_names.keys())
        if 0 <= idx < len(modes):
            self.canvas_mode = modes[idx]
            self.canvas_preview.setCanvasMode(self.canvas_mode)
            self._update_preview_title()

    def on_open_pixel_website(self):
        import webbrowser
        webbrowser.open("https://living-the-grid.com")

    def log(self, message):
        self.log_text.append(message)


class PixelGenWindow(QMainWindow):
    drawing_data_ready = Signal(object, object, int, bool)

    def __init__(self, embed_mode: bool = False):
        super().__init__()
        self.logger = get_logger("PixelGenWindow")
        self.logger.info(f"像素图生成窗口初始化，嵌入模式: {embed_mode}")

        self.embed_mode = embed_mode
        self.main_window = None

        if embed_mode:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setWindowTitle("朋友收集 - 像素绘图")
            self.resize(900, 600)
            self.setMinimumSize(900, 600)
            self.setWindowIcon(QIcon(resource_path("assets/tomodachilife.ico")))

        self.set_background()

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.main_page = MainPage()
        self.main_page.drawing_data_ready.connect(self._on_main_page_drawing_ready)
        self.stacked_widget.addWidget(self.main_page)
        self.stacked_widget.setCurrentWidget(self.main_page)

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def _on_main_page_drawing_ready(
        self, color_index_matrix, color_palette, pixel_size, is_preset
    ):
        if hasattr(self, "main_window") and self.main_window is not None:
            drawing_mode = self.main_page.drawing_mode
            brush_type = self.main_page.brush_type if drawing_mode == "json" else None
            brush_size = self.main_page.brush_size if drawing_mode == "json" else None
            press_data = self.main_page.press_data if drawing_mode == "json" else None
            self.main_window.on_drawing_data_ready(
                color_index_matrix,
                color_palette,
                pixel_size,
                is_preset,
                drawing_mode,
                brush_type,
                brush_size,
                press_data,
            )
        else:
            self.logger.error("main_window 属性不存在或为 None，无法执行绘图")
            QMessageBox.warning(
                self, "错误", "无法找到主窗口，请重新打开像素绘图窗口。"
            )

    def set_main_window(self, main_window):
        self.main_window = main_window
        self.logger.info("已接收主窗口引用")

