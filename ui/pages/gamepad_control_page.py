"""
手柄控制页面 v2.2.0
负责手柄连接操作，包含静态 logo、连接按钮以及重新检测功能。
属于 UI 层页面，依赖 core.hal 进行控制器通信。
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QBrush, QIcon

from core.hal.controller import EasyConController
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class GamepadControlPage(QWidget):
    connection_success = Signal()  # 连接成功信号
    restart_detection_requested = Signal()  # 重新检测信号
    virtual_gamepad_requested = Signal()

    def __init__(self, controller: EasyConController):
        super().__init__()
        self.logger = get_logger("GamepadControlPage")
        self.controller = controller

        self.set_background()
        self.setup_ui()

        self.update_connect_button(False)

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # 静态logo（不可点击）
        self.icon_label = QLabel()
        icon = QIcon(resource_path("assets/nspro.ico"))
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(128, 128))
        else:
            self.icon_label.setText("🎮")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 60px; color: #333;")

        # 标题
        self.title_label = QLabel("CH32F103C8T6")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)

        # 新增重新检测按钮
        self.restart_btn = QPushButton("🔄 重新检测")
        self.restart_btn.setFixedSize(180, 40)
        self.restart_btn.clicked.connect(self.on_restart_clicked)

        # 连接按钮
        self.connect_btn = QPushButton()
        self.connect_btn.setFixedSize(180, 40)
        self.connect_btn.clicked.connect(self.on_connect_clicked)

        # 提示标签
        self.hint_label = QLabel(
            "请确认：\n"
            "• HUSB 已接入 PC\n"
            "• 另一 USB 口已接入 NS 底座\n"
            "• 固件正常运行（绿灯闪烁）"
        )
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: #666; font-size: 12px;")
        self.hint_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(
            self.restart_btn, alignment=Qt.AlignCenter
        )  # 重新检测按钮在连接按钮上方
        layout.addWidget(self.connect_btn, alignment=Qt.AlignCenter)
        layout.addWidget(self.hint_label)

        self.setLayout(layout)

    def on_restart_clicked(self):
        self.logger.info("用户点击重新检测")
        self.restart_detection_requested.emit()

    def on_connect_clicked(self):
        if self.controller.is_connected():
            self.logger.info("设备已连接，忽略重复连接请求")
            return

        self.logger.info("用户请求连接单片机")
        success = self.controller.connect()
        if success:
            self.logger.info("首次连接成功")
            self.update_connect_button(True)
            self.connection_success.emit()
            return

        self.logger.warning("首次连接失败，等待 2 秒后重试...")
        QTimer.singleShot(2000, self._retry_connect)

    def _retry_connect(self):
        self.logger.info("尝试第二次连接")
        success = self.controller.connect()
        if success:
            self.logger.info("第二次连接成功")
            self.update_connect_button(True)
            self.connection_success.emit()
        else:
            self.logger.error("两次连接尝试均失败")
            self.update_connect_button(False)
            QMessageBox.warning(
                self,
                "连接失败",
                "无法连接到设备。\n\n请尝试按下单片机的 RESET 键后重试。",
            )

    def update_connect_button(self, connected: bool):
        if connected:
            self.connect_btn.setText("✅ 已连接")
            self.connect_btn.setEnabled(False)
        else:
            self.connect_btn.setText("🔌 自动连接")
            self.connect_btn.setEnabled(True)
