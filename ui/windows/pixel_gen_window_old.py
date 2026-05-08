"""
像素图生成窗口 v2.3.0
用于"朋友收集梦想生活"像素绘图工具。
可嵌入标签页或独立窗口显示。
支持预设/自定义调色盘，JSON 第三方导入，以及最优调度预估。
"""

import os
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QSlider,
    QFileDialog,
    QTextEdit,
    QMessageBox,
    QScrollArea,
    QComboBox,
    QCheckBox,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QIcon, QBrush, QImage, QWheelEvent, QFont

from core.utils.logger import get_logger
from core.utils.resource import resource_path
from core.image.json_importer import JsonImporter
from core.image.preset_palette import get_preset_palette, get_preset_color_count
from services.image_worker import ImageProcessWorkerPyx
from core.scheduling.optimizer import SchedulingOptimizer
from core.scheduling.timing_config import TimingConfig
from ui.widgets.canvas_preview import CanvasPreview


class MainPage(QWidget):
    """像素绘图主页面"""

    # 信号扩展：增加 is_preset 参数（后续参数通过 PixelGenWindow 属性传递）
    drawing_data_ready = Signal(object, object, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("MainPage")
        self.use_preset_palette = True  # 默认使用预设调色盘
        self.preset_color_values = [2, 4, 8, 16, 32]
        self.custom_color_values = [4, 8, 16, 32, 64, 128, 256]
        self.current_color_values = self.preset_color_values

        # JSON 导入相关状态
        self.json_loaded = False
        self.json_matrix = None
        self.json_palette = None
        self.json_metadata = {}
        self.json_file_path = None

        # 画笔参数（默认顺滑 1px）
        self.brush_type = "smooth"
        self.brush_size = 1
        self.smooth_sizes = [1, 3, 7, 13, 19, 27]
        self.pixel_sizes = [4, 8, 16, 32]
        self.current_brush_sizes = self.smooth_sizes

        # 自定义模式的 HSV 按键次数数据
        self.press_data = None

        self.setup_ui()
        self.apply_style()
        self.connect_signals()
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 保存生成时固化的调色板类型
        self.generated_is_preset = True
        # 绘图模式：image 或 json
        self.drawing_mode = "image"
        # 画布模式
        self.canvas_mode = "standard"
        self.canvas_mode_names = {
            "standard": "标准",
            "book": "书籍",
            "tv": "电视",
            "game": "游戏",
            "decoration": "装修",
        }
        self._current_preview_pixmap: QPixmap | None = None

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ========== 左侧面板：运行日志 ==========
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

        # ========== 中间预览 ==========
        middle_panel = QVBoxLayout()
        preview_group = QGroupBox("预览 (256x256)")
        f = preview_group.font()
        f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        preview_group.setFont(f)
        preview_layout = QVBoxLayout()
        self.canvas_preview = CanvasPreview()
        self.canvas_preview.setMinimumSize(256, 256)
        preview_layout.addWidget(self.canvas_preview, 1)
        preview_group.setLayout(preview_layout)
        middle_panel.addWidget(preview_group)

        action_layout = QHBoxLayout()
        self.btn_export = QPushButton("💾 导出")
        self.btn_export.setEnabled(False)
        self.btn_confirm = QPushButton("📌 定稿")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setObjectName("confirm_btn")
        action_layout.addWidget(self.btn_export)
        action_layout.addWidget(self.btn_confirm)
        middle_panel.addLayout(action_layout)

        # ========== 右侧面板：将原“生成的脚本”替换为“JSON导入” ==========
        right_panel = QVBoxLayout()

        # ---- 像素化设置 ----
        settings_group = QGroupBox("👾像素化设置")
        settings_layout = QVBoxLayout()

        mode_layout = QHBoxLayout()
        self.btn_preset_palette = QPushButton("预设调色盘")
        self.btn_custom_palette = QPushButton("自定义调色盘")
        mode_layout.addWidget(self.btn_preset_palette)
        mode_layout.addWidget(self.btn_custom_palette)
        settings_layout.addLayout(mode_layout)

        self.btn_preset_palette.setProperty("active", True)
        self.btn_custom_palette.setProperty("active", False)
        self.btn_preset_palette.setEnabled(False)
        self.btn_custom_palette.setEnabled(True)

        self.pixel_size_label = QLabel("像素图大小: 64")
        self.pixel_size_slider = QSlider(Qt.Horizontal)
        self.pixel_size_slider.setRange(0, 3)
        self.pixel_size_slider.setValue(1)
        self.pixel_size_slider.setTickPosition(QSlider.TicksBelow)
        self.pixel_size_slider.setTickInterval(1)
        self.pixel_size_slider.setPageStep(1)
        self.pixel_size_slider.setSingleStep(1)
        self.pixel_size_values = [32, 64, 128, 256]

        self.color_count_label = QLabel("最大颜色数: 16")
        self.color_slider = QSlider(Qt.Horizontal)
        self.color_slider.setRange(0, len(self.current_color_values) - 1)
        self.color_slider.setValue(3)
        self.color_slider.setTickPosition(QSlider.TicksBelow)
        self.color_slider.setTickInterval(1)
        self.color_slider.setPageStep(1)
        self.color_slider.setSingleStep(1)

        settings_layout.addWidget(self.pixel_size_label)
        settings_layout.addWidget(self.pixel_size_slider)
        settings_layout.addWidget(self.color_count_label)
        settings_layout.addWidget(self.color_slider)
        settings_group.setLayout(settings_layout)

        right_panel.addWidget(settings_group)

        self.btn_upload = QPushButton("📁 上传图片")
        self.btn_generate = QPushButton("⚙️ 生成像素图")
        self.btn_generate.setEnabled(False)
        self.btn_open_website = QPushButton("🌐 推荐！打开第三方像素化网页")

        right_panel.addWidget(self.btn_upload)
        right_panel.addWidget(self.btn_generate)
        right_panel.addWidget(self.btn_open_website)

        # ---- JSON 导入设置 ----
        json_group = QGroupBox("📄 JSON 导入")
        json_layout = QVBoxLayout()

        # 画笔类型切换按钮（对应预设/自定义调色盘）
        brush_mode_layout = QHBoxLayout()
        self.btn_smooth_brush = QPushButton("顺滑画笔")
        self.btn_pixel_brush = QPushButton("像素画笔")
        brush_mode_layout.addWidget(self.btn_smooth_brush)
        brush_mode_layout.addWidget(self.btn_pixel_brush)
        json_layout.addLayout(brush_mode_layout)

        # 激活样式（默认顺滑激活）
        self.btn_smooth_brush.setProperty("active", True)
        self.btn_pixel_brush.setProperty("active", False)
        self.btn_smooth_brush.setEnabled(False)
        self.btn_pixel_brush.setEnabled(True)

        # 笔尖大小滑块（对应像素图大小滑块）
        self.brush_size_label = QLabel("笔尖大小: 1")
        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setRange(0, len(self.current_brush_sizes) - 1)
        self.brush_size_slider.setValue(0)  # 默认索引0，对应1像素
        self.brush_size_slider.setTickPosition(QSlider.TicksBelow)
        self.brush_size_slider.setTickInterval(1)
        self.brush_size_slider.setPageStep(1)
        self.brush_size_slider.setSingleStep(1)

        json_layout.addWidget(self.brush_size_label)
        json_layout.addWidget(self.brush_size_slider)

        # 画布模式选择
        canvas_mode_layout = QHBoxLayout()
        canvas_mode_layout.addWidget(QLabel("画布模式:"))
        self.canvas_mode_combo = QComboBox()
        self.canvas_mode_combo.addItems(["标准", "书籍", "电视", "游戏", "装修"])
        self.canvas_mode_combo.setCurrentIndex(0)
        self.canvas_mode_combo.currentIndexChanged.connect(self._on_canvas_mode_changed)
        canvas_mode_layout.addWidget(self.canvas_mode_combo)
        json_layout.addLayout(canvas_mode_layout)

        # 上传 JSON 按钮（对应上传图片）
        self.btn_upload_json = QPushButton("📁 上传 JSON")
        # 渲染 JSON 按钮（对应生成像素图）
        self.btn_render_json = QPushButton("⚙️ 渲染 JSON")
        self.btn_render_json.setEnabled(False)

        json_layout.addWidget(self.btn_upload_json)
        json_layout.addWidget(self.btn_render_json)
        json_group.setLayout(json_layout)

        right_panel.addWidget(json_group)

        # ========== 组装主布局 ==========
        main_layout.addLayout(left_panel, 2)
        main_layout.addLayout(middle_panel, 3)
        main_layout.addLayout(right_panel, 2)

    def apply_style(self):
        # 样式表保持不变
        self.setStyleSheet("""
            QGroupBox { font-family: "Microsoft YaHei UI"; border: 1px solid #aaa; border-radius: 5px; margin-top: 10px; background-color: rgba(255, 255, 255, 200); }
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
                border: 1px solid #aaa;
                border-radius: 4px;
                padding: 3px 24px 3px 8px;
                background: rgba(255,255,255,220);
                font-family: "Microsoft YaHei UI";
                min-width: 60px;
            }
            QComboBox:hover { border: 1px solid #888; background: rgba(255,255,255,255); }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border-left: 1px solid #ccc;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #aaa;
                border-radius: 3px;
                padding: 2px;
                background: rgba(255,255,255,240);
                outline: none;
            }
        """)

    def connect_signals(self):
        self.pixel_size_slider.valueChanged.connect(
            lambda v: self.pixel_size_label.setText(
                f"像素图大小: {self.pixel_size_values[v]}"
            )
        )
        self.color_slider.valueChanged.connect(self._on_color_slider_changed)
        self.btn_upload.clicked.connect(self.on_upload)
        self.btn_generate.clicked.connect(self.on_generate)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_confirm.clicked.connect(self.on_confirm)
        self.btn_preset_palette.clicked.connect(self._on_preset_mode)
        self.btn_custom_palette.clicked.connect(self._on_custom_mode)

        # JSON 导入区域信号
        self.btn_smooth_brush.clicked.connect(self._on_smooth_mode)
        self.btn_pixel_brush.clicked.connect(self._on_pixel_mode)
        self.brush_size_slider.valueChanged.connect(self._on_brush_size_changed)
        self.btn_upload_json.clicked.connect(self.on_upload_json)
        self.btn_render_json.clicked.connect(self.on_render_json)

        # 新增：打开像素化网页按钮
        self.btn_open_website.clicked.connect(self.on_open_pixel_website)

    # ---------- 原有槽函数（保持不变） ----------
    def _on_color_slider_changed(self, v):
        if 0 <= v < len(self.current_color_values):
            self.color_count_label.setText(
                f"最大颜色数: {self.current_color_values[v]}"
            )

    def _on_preset_mode(self):
        self.use_preset_palette = True
        self.btn_preset_palette.setProperty("active", True)
        self.btn_custom_palette.setProperty("active", False)
        self.btn_preset_palette.setEnabled(False)
        self.btn_custom_palette.setEnabled(True)
        self._update_button_style()

        old_value = self.current_color_values[self.color_slider.value()]
        self.current_color_values = self.preset_color_values
        new_index = self._closest_index(old_value, self.preset_color_values)
        self.color_slider.setRange(0, len(self.current_color_values) - 1)
        self.color_slider.setValue(new_index)
        self._on_color_slider_changed(new_index)

    def _on_custom_mode(self):
        self.use_preset_palette = False
        self.btn_preset_palette.setProperty("active", False)
        self.btn_custom_palette.setProperty("active", True)
        self.btn_preset_palette.setEnabled(True)
        self.btn_custom_palette.setEnabled(False)
        self._update_button_style()

        old_value = self.current_color_values[self.color_slider.value()]
        self.current_color_values = self.custom_color_values
        new_index = self._closest_index(old_value, self.custom_color_values)
        self.color_slider.setRange(0, len(self.current_color_values) - 1)
        self.color_slider.setValue(new_index)
        self._on_color_slider_changed(new_index)

    def _closest_index(self, value, values):
        closest_idx = 0
        min_diff = abs(value - values[0])
        for i, v in enumerate(values):
            diff = abs(value - v)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        return closest_idx

    def _update_button_style(self):
        self.btn_preset_palette.style().unpolish(self.btn_preset_palette)
        self.btn_preset_palette.style().polish(self.btn_preset_palette)
        self.btn_custom_palette.style().unpolish(self.btn_custom_palette)
        self.btn_custom_palette.style().polish(self.btn_custom_palette)
        # 同时更新 JSON 区域按钮样式
        self.btn_smooth_brush.style().unpolish(self.btn_smooth_brush)
        self.btn_smooth_brush.style().polish(self.btn_smooth_brush)
        self.btn_pixel_brush.style().unpolish(self.btn_pixel_brush)
        self.btn_pixel_brush.style().polish(self.btn_pixel_brush)

    # ---------- JSON 导入区域槽函数 ----------
    def _on_smooth_mode(self):
        self.brush_type = "smooth"
        self.btn_smooth_brush.setProperty("active", True)
        self.btn_pixel_brush.setProperty("active", False)
        self.btn_smooth_brush.setEnabled(False)
        self.btn_pixel_brush.setEnabled(True)
        self._update_button_style()

        self.current_brush_sizes = self.smooth_sizes
        old_index = self.brush_size_slider.value()
        if old_index >= len(self.current_brush_sizes):
            old_index = 0
        self.brush_size_slider.setRange(0, len(self.current_brush_sizes) - 1)
        self.brush_size_slider.setValue(old_index)
        self.brush_size = self.current_brush_sizes[old_index]
        self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")

    def _on_pixel_mode(self):
        self.brush_type = "pixel"
        self.btn_smooth_brush.setProperty("active", False)
        self.btn_pixel_brush.setProperty("active", True)
        self.btn_smooth_brush.setEnabled(True)
        self.btn_pixel_brush.setEnabled(False)
        self._update_button_style()

        self.current_brush_sizes = self.pixel_sizes
        old_index = self.brush_size_slider.value()
        if old_index >= len(self.current_brush_sizes):
            old_index = 0
        self.brush_size_slider.setRange(0, len(self.current_brush_sizes) - 1)
        self.brush_size_slider.setValue(old_index)
        self.brush_size = self.current_brush_sizes[old_index]
        self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")

    def _on_brush_size_changed(self, idx):
        if 0 <= idx < len(self.current_brush_sizes):
            self.brush_size = self.current_brush_sizes[idx]
            self.brush_size_label.setText(f"笔尖大小: {self.brush_size}")

    def _on_canvas_mode_changed(self, idx):
        modes = list(self.canvas_mode_names.keys())
        if 0 <= idx < len(modes):
            self.canvas_mode = modes[idx]
            self.canvas_preview.setCanvasMode(self.canvas_mode)

    def on_upload_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", "", "JSON 文件 (*.json)"
        )
        if not file_path:
            return
        self.json_file_path = file_path
        self._import_json_with_current_settings()
        if self.json_metadata:
            self._apply_json_brush_settings(self.json_metadata)
            self._apply_json_canvas_settings(self.json_metadata)

        self.log(f"已上传 JSON: {os.path.basename(self.json_file_path)}")
        self.log(
            f"  画笔: {self.brush_type} {self.brush_size}px, 尺寸: {self.json_metadata['width']}x{self.json_metadata['height']}"
        )
        self.logger.info(f"上传 JSON: {os.path.basename(self.json_file_path)}")

    def _apply_json_brush_settings(self, metadata: dict):
        """
        根据 JSON 导入的 brush 字段自动设置画笔 UI（允许用户后续修改）。
        仅当 json_brush_type 和 json_brush_size 有效且合法时才执行。
        """
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
        """根据 JSON 导入的 canvas 字段自动设置画布模式 UI。"""
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
            self.json_file_path,
            self.brush_type,
            self.brush_size,
            canvas_mode=self.canvas_mode,
        )
        if matrix is None:
            QMessageBox.critical(self, "导入失败", metadata.get("error", "未知错误"))
            return

        self.json_matrix = matrix
        self.json_palette = palette
        self.json_metadata = metadata
        self.json_loaded = True
        self.btn_render_json.setEnabled(True)

        # 保存 press_data（自定义模式下的 HSV 按键次数）
        self.press_data = metadata.get("press_data")

        self.log(f"已上传 JSON: {os.path.basename(self.json_file_path)}")
        self.log(
            f"  画笔: {self.brush_type} {self.brush_size}px, 尺寸: {metadata['width']}x{metadata['height']}"
        )
        self.logger.info(f"上传 JSON: {os.path.basename(self.json_file_path)}")

    def on_render_json(self):
        if not self.json_loaded or self.json_matrix is None:
            QMessageBox.warning(self, "提示", "请先上传 JSON 文件。")
            return
        # 使用当前画笔设置重新导入（确保与滑块一致）
        self._import_json_with_current_settings()
        if self.json_matrix is None:
            return
        # 更新预览
        self._update_preview_from_matrix()
        self.drawing_mode = "json"
        self.generated_is_preset = self.json_metadata.get("all_preset", True)
        self.btn_export.setEnabled(True)
        self.btn_confirm.setEnabled(True)
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
                else:
                    img_array[y, x] = [0, 0, 0, 0]
        qimage = QImage(img_array.data, w, h, w * 4, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        self.canvas_preview.setPixmap(pixmap)
        self.canvas_preview.setCanvasMode(self.canvas_mode)
        self._current_preview_pixmap = pixmap
        # 同时更新内部变量供定稿使用
        self.color_index_matrix = matrix
        self.color_palette = palette

    # ---------- 原有图像处理槽函数（保持不变） ----------
    def on_upload(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return
        self.original_image_path = file_path
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "错误", "无法加载图片，请检查文件格式。")
            return
        self.pixel_image = None
        self.color_palette = None
        self.color_index_matrix = None
        self.canvas_preview.setPixmap(pixmap)
        self.canvas_preview.setCanvasMode(self.canvas_mode)
        self._current_preview_pixmap = pixmap
        self.btn_generate.setEnabled(True)
        self.log(f"已上传图片: {os.path.basename(file_path)}")
        self.logger.info(f"上传图片: {os.path.basename(file_path)}")
        self.btn_generate.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.btn_confirm.setEnabled(False)
        self.drawing_mode = "image"

    def on_open_pixel_website(self):
        """打开推荐的像素化网页"""
        import webbrowser

        url = "https://living-the-grid.gozapp.dev/"
        webbrowser.open(url)
        self.log(f"已打开网页: {url}")
        self.logger.info(f"用户点击跳转像素化网页: {url}")

    def on_generate(self):
        if not self.original_image_path:
            return
        mode_str = "预设调色盘" if self.use_preset_palette else "自定义调色盘"
        self.log(f"开始生成像素图（使用 Pyxelate，{mode_str}）...")
        self.logger.info(f"开始生成像素图（Pyxelate），{mode_str}")
        self.btn_generate.setEnabled(False)
        self.drawing_mode = "image"
        QTimer.singleShot(50, self.process_image)

    def process_image(self):
        target_colors = self.current_color_values[self.color_slider.value()]
        self.generated_is_preset = self.use_preset_palette

        self.worker = ImageProcessWorkerPyx(
            self.original_image_path,
            self.pixel_size_values[self.pixel_size_slider.value()],
            target_colors,
            use_preset=self.generated_is_preset,
            canvas_mode=self.canvas_mode,
        )
        self.worker.finished.connect(self.on_image_processed)
        self.worker.error.connect(self.on_image_error)
        self.worker.start()

    def on_image_processed(self, result, unique_colors):
        pixel_image, color_palette, color_index_matrix = result
        self.pixel_image = pixel_image
        self.color_palette = color_palette
        self.color_index_matrix = color_index_matrix

        data = pixel_image.tobytes("raw", "RGBA")
        qimage = QImage(
            data, pixel_image.width, pixel_image.height, QImage.Format_RGBA8888
        )
        pixmap = QPixmap.fromImage(qimage)
        self.canvas_preview.setPixmap(pixmap)
        self.canvas_preview.setCanvasMode(self.canvas_mode)
        self._current_preview_pixmap = pixmap

        pixel_size = self.pixel_size_values[self.pixel_size_slider.value()]
        target_colors = self.current_color_values[self.color_slider.value()]
        actual_colors = len(color_palette)
        self.log(
            f"像素化完成。像素图大小: {pixel_size}, 目标颜色数: {target_colors}, 实际颜色数: {actual_colors}"
        )
        self.logger.info(f"像素化完成: pixel_size={pixel_size}, colors={actual_colors}")

        self.btn_export.setEnabled(True)
        self.btn_confirm.setEnabled(True)
        self.btn_generate.setEnabled(True)

    def on_image_error(self, error_msg):
        self.log(f"处理失败: {error_msg}")
        self.logger.error(f"图片处理失败: {error_msg}")
        QMessageBox.critical(self, "错误", f"图片处理失败:\n{error_msg}")
        self.btn_generate.setEnabled(True)

    # ---------- 导出 ----------
    def on_export(self):
        if self.color_index_matrix is None:
            QMessageBox.warning(self, "提示", "没有可导出的像素图，请先生成或渲染。")
            return
        default_name = "pixel_image.png"
        if hasattr(self, "original_image_path") and self.original_image_path:
            base = os.path.splitext(os.path.basename(self.original_image_path))[0]
            default_name = f"{base}_pixel.png"
        elif self.json_file_path:
            base = os.path.splitext(os.path.basename(self.json_file_path))[0]
            default_name = f"{base}_rendered.png"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出像素图", default_name, "PNG 图片 (*.png)"
        )
        if not save_path:
            return
        try:
            self._current_preview_pixmap.save(save_path, "PNG")
            self.log(f"像素图已导出: {save_path}")
            self.logger.info(f"像素图已导出: {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")
            self.log(f"导出失败: {str(e)}")
            self.logger.error(f"导出失败: {e}")

    # ---------- 定稿（使用统一优化器评估） ----------
    def on_confirm(self):
        if self.color_index_matrix is None:
            QMessageBox.warning(self, "提示", "请先生成像素图。")
            return

        # 冻结当前时序参数快照，评估期间不受 UI 修改影响
        timing = TimingConfig.snapshot()

        # 使用调度优化器评估最优方案
        try:
            optimizer = SchedulingOptimizer()
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
                self.generated_is_preset,
                grid_w,
                grid_h,
                palette=self.color_palette,
                press_data=getattr(self, "press_data", None),
                timing=timing,
            )
            if best_schedule is None:
                QMessageBox.warning(self, "错误", "无法生成调度方案，请检查数据。")
                return

            total_ms = optimizer.estimate_schedule_cost(
                best_schedule,
                self.brush_type if self.drawing_mode == "json" else None,
                self.brush_size if self.drawing_mode == "json" else None,
                self.generated_is_preset,
                grid_w,
                grid_h,
                palette=self.color_palette,
                press_data=getattr(self, "press_data", None),
                timing=timing,
            )
            total_sec = total_ms / 1000.0
            minutes = int(total_sec // 60)
            seconds = int(total_sec % 60)

            estimate = {
                "total_ms": total_ms,
                "best_desc": best_desc,
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
        self.logger.info("准备通知主窗口进行绘图...")
        pixel_size = self.pixel_size_values[self.pixel_size_slider.value()]
        self.drawing_data_ready.emit(
            self.color_index_matrix,
            self.color_palette,
            pixel_size,
            self.generated_is_preset,
        )

    def _show_estimate_dialog(self, estimate):
        total_sec = estimate.get("total_ms", 0) / 1000.0
        minutes = int(total_sec // 60)
        seconds = int(total_sec % 60)

        log_lines = estimate.get("evaluation_log", [])
        log_text = "\n".join(log_lines)

        msg = (
            f"【最优方案】{estimate.get('best_desc', '未知')}\n"
            f"预估总耗时：{minutes} 分 {seconds} 秒\n\n"
            f"── 所有方案评估 ──\n"
            f"{log_text}\n\n"
            f"是否立即开始绘制？"
        )

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("绘图预估")
        msg_box.setText(msg)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.Yes)
        msg_box.setMinimumWidth(550)

        reply = msg_box.exec()
        return reply == QMessageBox.Yes

    def log(self, message):
        self.log_text.append(message)


class PixelGenWindow(QMainWindow):
    # 信号扩展：增加 is_preset 参数
    drawing_data_ready = Signal(object, object, int, bool)

    def __init__(self, embed_mode: bool = False):
        super().__init__()
        self.logger = get_logger("PixelGenWindow")
        self.logger.info(f"像素图生成窗口初始化，嵌入模式: {embed_mode}")

        self.embed_mode = embed_mode
        self.main_window = None

        # ----- 嵌入模式适配 -----
        if embed_mode:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setWindowTitle("朋友收集 - 像素绘图")
            self.resize(900, 600)
            self.setMinimumSize(900, 600)
            self.setWindowIcon(QIcon(resource_path("assets/tomodachilife.ico")))

        # 背景设置（嵌入和独立模式均需）
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
            # 从 main_page 获取绘图模式、画笔参数和 press_data
            drawing_mode = self.main_page.drawing_mode
            brush_type = self.main_page.brush_type if drawing_mode == "json" else None
            brush_size = self.main_page.brush_size if drawing_mode == "json" else None
            press_data = self.main_page.press_data if drawing_mode == "json" else None
            # 调用主窗口的扩展方法（需在主窗口已实现）
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
