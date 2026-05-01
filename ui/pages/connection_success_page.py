"""
连接成功庆祝页面 v2.2.0
展示静态logo背景、交替线条、花朵不停下落，整体可点击进入虚拟手柄。
音乐控制按钮与工具选择页样式一致，状态同步。
属于 UI 层页面，依赖 services.audio_manager 和 ui.widgets.hover_label。
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QBrush, QIcon, QMouseEvent
import random
import os

from core.utils.logger import get_logger
from core.utils.resource import resource_path
from services.audio_manager import AudioManager
from ui.widgets.hover_label import HoverLabel


class ConnectionSuccessPage(QWidget):
    virtual_gamepad_requested = Signal()

    def __init__(self):
        super().__init__()
        self.logger = get_logger("ConnectionSuccessPage")
        self.logger.info("连接成功庆祝页面初始化")

        # 音频管理器（单例，与工具选择页共享）
        self.audio = AudioManager()
        # 连接状态变化信号
        self.audio.state_changed.connect(self.update_audio_button_state)

        # 音乐控制按钮（使用 HoverLabel）
        self.audio_btn = HoverLabel(self)
        self.audio_btn.move(10, 10)
        self.audio_btn.raise_()

        # 加载图标
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

        self.line_timer = QTimer()
        self.line_timer.timeout.connect(self._toggle_line)
        self.current_line = None

        self.fall_timer = QTimer()
        self.fall_timer.timeout.connect(self._update_flowers_position)
        self.flower_labels = []

        self.set_background()
        self.setup_ui()
        self._start_celebration()

    def update_audio_button_state(self):
        """根据当前播放状态更新按钮图标"""
        is_playing = self.audio.is_playing()
        self.audio_btn.set_playing_state(is_playing)

    def on_audio_clicked(self, event: QMouseEvent):
        """点击音乐按钮切换播放/暂停"""
        self.audio.toggle()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(0, 10, 0, 60)

        self.canvas = QWidget()
        self.canvas.setFixedSize(600, 600)
        self.canvas.setStyleSheet("background: transparent;")
        self.canvas.setCursor(Qt.PointingHandCursor)
        self.canvas.mousePressEvent = self._on_canvas_clicked

        icon_y = 112
        line_offset_y = icon_y - 172

        self.static_logo = QLabel(self.canvas)
        icon = QIcon(resource_path("assets/nspro.ico"))
        if not icon.isNull():
            self.static_logo.setPixmap(icon.pixmap(256, 256))
        else:
            self.static_logo.setText("🎮")
        self.static_logo.setAlignment(Qt.AlignCenter)
        self.static_logo.setStyleSheet(
            "font-size: 120px; color: #333; background: transparent;"
        )
        self.static_logo.setGeometry(172, icon_y, 256, 256)
        self.static_logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.icon_label = QLabel(self.canvas)
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(256, 256))
        else:
            self.icon_label.setText("🎮")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet(
            "font-size: 120px; color: #333; background: transparent;"
        )
        self.icon_label.setGeometry(172, icon_y, 256, 256)
        self.icon_label.setCursor(Qt.PointingHandCursor)

        self.line_a = QLabel(self.canvas)
        pix_a = QPixmap(resource_path("assets/content_panel_drama_01_lines_a.png"))
        if not pix_a.isNull():
            pix_a = pix_a.scaled(600, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.line_a.setPixmap(pix_a)
        self.line_a.setAlignment(Qt.AlignCenter)
        self.line_a.setStyleSheet("background: transparent;")
        self.line_a.setGeometry(0, line_offset_y, 600, 600)
        self.line_a.hide()

        self.line_b = QLabel(self.canvas)
        pix_b = QPixmap(resource_path("assets/content_panel_drama_01_lines_b.png"))
        if not pix_b.isNull():
            pix_b = pix_b.scaled(600, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.line_b.setPixmap(pix_b)
        self.line_b.setAlignment(Qt.AlignCenter)
        self.line_b.setStyleSheet("background: transparent;")
        self.line_b.setGeometry(0, line_offset_y, 600, 600)
        self.line_b.hide()

        main_layout.addWidget(self.canvas, alignment=Qt.AlignCenter)

        # 文字容器
        text_panel = QFrame()
        text_panel.setStyleSheet(
            """
            QFrame {
                background-color: rgba(255, 255, 255, 180);
                border-radius: 20px;
                padding: 15px 30px;
            }
        """
        )
        panel_layout = QVBoxLayout(text_panel)
        panel_layout.setAlignment(Qt.AlignCenter)
        panel_layout.setSpacing(6)

        title = QLabel("🎊连接成功🎉")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #333; background: transparent;")
        panel_layout.addWidget(title)

        hint = QLabel("点击花瓣进入模拟手柄界面按 A 唤醒手柄")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #555; background: transparent;")
        panel_layout.addWidget(hint)

        main_layout.addWidget(text_panel, alignment=Qt.AlignCenter)
        self.setLayout(main_layout)

    def resizeEvent(self, event):
        # 将音乐按钮固定在左上角
        self.audio_btn.move(10, 10)
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # 每次显示时同步按钮状态
        self.update_audio_button_state()
        self.audio_btn.raise_()

    def _start_celebration(self):
        self.current_line = "a"
        self.line_a.show()
        self.line_b.hide()
        self.line_timer.start(500)
        # 播放庆祝音效（自动开始播放）
        self.audio.play()
        self.logger.info("播放庆祝音效")

        self._clear_flowers()
        flower_images = [
            resource_path("assets/flower_green.png"),
            resource_path("assets/flower_orange.png"),
            resource_path("assets/flower_pink.png"),
        ]
        num_flowers = random.randint(6, 10)
        for _ in range(num_flowers):
            self._create_flower(flower_images, random_start=True)

        self.fall_timer.start(16)

    def _create_flower(self, flower_images, random_start=True, max_attempts=100):
        img_path = random.choice(flower_images)
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
        flower = QLabel(self.canvas)
        flower.setPixmap(
            pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        flower.setStyleSheet("background: transparent;")

        # 避让区域
        icon_rect_x = (172, 172 + 256)
        icon_rect_y = (112, 112 + 256)
        padding = 20
        avoid_x_min = icon_rect_x[0] - padding
        avoid_x_max = icon_rect_x[1] + padding
        avoid_y_min = icon_rect_y[0] - padding
        avoid_y_max = icon_rect_y[1] + padding

        attempts = 0
        while attempts < max_attempts:
            x = random.randint(10, 550)
            y = random.randint(0, 600) if random_start else 0
            if avoid_x_min < x < avoid_x_max and avoid_y_min < y < avoid_y_max:
                attempts += 1
                continue
            break
        else:
            x, y = 20, 20 if random_start else 0

        flower.move(x, y)
        flower.speed = random.uniform(1.0, 2.5)
        flower.show()
        self.flower_labels.append(flower)

    def _update_flowers_position(self):
        icon_rect_x = (172, 172 + 256)
        icon_rect_y = (112, 112 + 256)
        padding = 20
        avoid_x_min = icon_rect_x[0] - padding
        avoid_x_max = icon_rect_x[1] + padding

        for flower in self.flower_labels:
            current_pos = flower.pos()
            new_y = current_pos.y() + flower.speed
            if new_y > 600:
                new_y = -40
                new_x = random.randint(10, 550)
                attempts = 0
                while avoid_x_min < new_x < avoid_x_max and attempts < 50:
                    new_x = random.randint(10, 550)
                    attempts += 1
                flower.move(new_x, new_y)
                flower.speed = random.uniform(1.0, 2.5)
            else:
                flower.move(current_pos.x(), new_y)

    def _clear_flowers(self):
        for flower in self.flower_labels:
            flower.deleteLater()
        self.flower_labels.clear()

    def _toggle_line(self):
        if self.current_line == "a":
            self.line_a.hide()
            self.line_b.show()
            self.current_line = "b"
        else:
            self.line_b.hide()
            self.line_a.show()
            self.current_line = "a"

    def _on_canvas_clicked(self, event):
        self.virtual_gamepad_requested.emit()

    def closeEvent(self, event):
        self.line_timer.stop()
        self.fall_timer.stop()
        self._clear_flowers()
        event.accept()
