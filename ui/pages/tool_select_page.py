"""
工具选择页 v2.2.0
展示可用的绘图工具（模拟手柄、朋友收集、斯普拉遁），
包含浮动动画效果和背景音乐控制按钮。
属于 UI 层 widgets，依赖 QtWidgets / QtCore / QtGui。
"""

import os
import math
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QPixmap, QBrush, QTransform, QMouseEvent

from core.utils.logger import get_logger
from services.audio_manager import AudioManager
from core.utils.resource import resource_path
from ui.widgets.hover_label import HoverLabel


# ---------- 主页面 ----------
class ToolSelectPage(QWidget):
    tool_selected = Signal(str)
    connect_requested = Signal()
    virtual_gamepad_requested = Signal()

    def __init__(self):
        super().__init__()
        self.logger = get_logger("ToolSelectPage")
        self.logger.info("工具选择页初始化")

        self.audio = AudioManager()
        self.audio.state_changed.connect(self.update_audio_button_state)
        if not self.audio.load_random_from_folder(resource_path("musics")):
            self.logger.warning("musics 文件夹中没有可播放的音频文件")

        self.set_background()
        self._pending_animations = []
        self.icon_animations = []
        self.setup_ui()
        self.apply_style()
        self._start_float_animations()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg0.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(30)
        main_layout.setContentsMargins(10, 80, 10, 30)

        # ---------- 音频控制按钮（自定义 HoverLabel）----------
        self.audio_btn = HoverLabel(self)
        self.audio_btn.move(10, 10)
        self.audio_btn.raise_()

        # 加载图标（原始尺寸，不在此处缩放）
        play_path = resource_path("assets/open_logo.png")
        pause_path = resource_path("assets/close_logo.png")
        play_pix = None
        pause_pix = None
        if os.path.exists(play_path):
            play_pix = QPixmap(play_path)
        else:
            self.logger.warning(f"缺少图标: {play_path}")
        if os.path.exists(pause_path):
            pause_pix = QPixmap(pause_path)
        else:
            self.logger.warning(f"缺少图标: {pause_path}")

        self.audio_btn.set_icons(play_pix, pause_pix)

        # 设置点击事件
        self.audio_btn.mousePressEvent = self.on_audio_clicked

        # 初始状态同步
        self.update_audio_button_state()

        # ---------- 标题 ----------
        self.title_label = QLabel("请选择要使用的工具")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.title_label)

        # ---------- 工具按钮区域 ----------
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(40)

        self.btn_gamepad = self._create_tool_button(
            resource_path("assets/nspro.png"), "模拟手柄", "gamepad"
        )
        tools_layout.addWidget(self.btn_gamepad)

        self.btn_dream = self._create_tool_button(
            resource_path("assets/tomodachilife.webp"), "朋友收集", "dream_life"
        )
        tools_layout.addWidget(self.btn_dream)

        self.btn_splatoon = self._create_tool_button(
            resource_path("assets/splatoon.png"), "斯普拉遁", "splatoon"
        )
        tools_layout.addWidget(self.btn_splatoon)

        tools_layout.setAlignment(Qt.AlignCenter)
        main_layout.addLayout(tools_layout)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_tool_button(self, image_path, text, tool_name, emoji=None):
        btn = QPushButton()
        btn.setFixedSize(220, 260)
        btn.setObjectName("tool_btn")
        btn.clicked.connect(lambda: self.tool_selected.emit(tool_name))

        layout = QVBoxLayout(btn)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 20)

        layout.addStretch()

        icon_label = QLabel()
        base_pixmap = None
        if emoji:
            icon_label.setText(emoji)
            icon_label.setStyleSheet("font-size: 80px;")
        elif image_path:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                base_pixmap = pixmap.scaled(
                    160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                transform = QTransform()
                transform.rotate(10)
                rotated_pixmap = base_pixmap.transformed(
                    transform, Qt.SmoothTransformation
                )
                icon_label.setPixmap(rotated_pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(icon_label.styleSheet() + " background: transparent;")

        layout.addWidget(icon_label, alignment=Qt.AlignCenter)

        layout.addStretch()

        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2c2c2c; background: transparent;"
        )
        layout.addWidget(text_label, alignment=Qt.AlignBottom | Qt.AlignHCenter)

        if base_pixmap:
            phase = hash(icon_label) % 628 / 100.0
            self._pending_animations.append((icon_label, phase))

        return btn

    def apply_style(self):
        bg_path = resource_path("assets/bg1.webp").replace("\\", "/")
        self.setStyleSheet(
            f"""
            QPushButton#tool_btn {{
                border: 3px solid #E60012;
                border-radius: 20px;
                background-image: url("{bg_path}");
                background-repeat: repeat-xy;
            }}
            QPushButton#tool_btn:hover {{
                border: 3px solid #c00010;
            }}
            """
        )

    def _start_float_animations(self):
        for icon_label, phase in self._pending_animations:
            self.icon_animations.append((icon_label, phase))
        self._pending_animations.clear()

        if self.icon_animations:
            self.float_timer = QTimer()
            self.float_timer.timeout.connect(self._update_float)
            self.float_timer.start(16)
            self._float_time = 0.0

    def _update_float(self):
        self._float_time += 0.04
        for icon_label, phase in self.icon_animations:
            y_offset = int(6 * math.sin(self._float_time + phase))
            icon_label.setStyleSheet(
                f"margin-top: {y_offset}px; background: transparent;"
            )

    # ---------- 音频控制 ----------
    def update_audio_button_state(self):
        is_playing = self.audio.is_playing()
        self.audio_btn.set_playing_state(is_playing)

    def on_audio_clicked(self, event: QMouseEvent):
        print("[ToolSelectPage] Audio button clicked")
        self.audio.toggle()
        # 状态更新会由信号触发 update_audio_button_state，无需手动调用

    def resizeEvent(self, event):
        self.audio_btn.move(10, 10)
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_audio_button_state()
        self.audio_btn.raise_()

    def closeEvent(self, event):
        if hasattr(self, "float_timer"):
            self.float_timer.stop()
        self.icon_animations.clear()
        event.accept()
