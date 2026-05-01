"""
可悬停放大的图标标签控件 v2.2.0
提供鼠标悬停平滑缩放效果，支持播放/暂停两种图标状态。
用于音乐控制按钮等场景，独立于任何页面，可在多个 UI 中复用。

使用方式：
    from ui.widgets.hover_label import HoverLabel
    btn = HoverLabel()
    btn.set_icons(play_pixmap, pause_pixmap)
    btn.mousePressEvent = custom_click_handler
"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve


class HoverLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.default_size = QSize(64, 64)
        self.hover_size = QSize(80, 80)
        self.resize(self.default_size)
        self.setMinimumSize(16, 16)
        self.setMaximumSize(200, 200)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

        self.animation = QPropertyAnimation(self, b"size")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)
        self.animation.valueChanged.connect(self._on_animation_value_changed)
        self.animation.finished.connect(self._on_animation_finished)

        self.play_pixmap = None
        self.pause_pixmap = None
        self.is_playing = False

    def set_icons(self, play_pixmap, pause_pixmap):
        self.play_pixmap = play_pixmap
        self.pause_pixmap = pause_pixmap
        self.update_icon(self.default_size)

    def set_playing_state(self, playing):
        self.is_playing = playing
        self.update_icon(self.size())

    def update_icon(self, size):
        if self.play_pixmap is None or self.pause_pixmap is None:
            self.setText("🔊" if self.is_playing else "🔇")
            font_size = size.width() // 2
            self.setStyleSheet(
                f"font-size: {font_size}px; background: transparent; border: none;"
            )
            return
        pixmap = self.play_pixmap if self.is_playing else self.pause_pixmap
        scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def enterEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.size())
        self.animation.setEndValue(self.hover_size)
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.stop()
        self.animation.setStartValue(self.size())
        self.animation.setEndValue(self.default_size)
        self.animation.start()
        super().leaveEvent(event)

    def _on_animation_value_changed(self, value):
        size = (
            value if isinstance(value, QSize) else QSize(value.width(), value.height())
        )
        self.update_icon(size)

    def _on_animation_finished(self):
        self.update_icon(self.size())
