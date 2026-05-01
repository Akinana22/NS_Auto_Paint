"""
固件烧录页面 v2.2.0
负责引导用户烧录 CH32 固件。
使用统一的 resource_path 获取固件和工具路径，无私有路径方法。
属于 UI 层页面，依赖 services 层进行烧录。
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QBrush, QResizeEvent
import os
import sys

from services.device.flash_worker import FlashWorker
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class FirmwareCheckPage(QWidget):
    check_finished = Signal(bool)  # 完成时发射，用于返回设备检测页

    # ========== 布局比例参数（可在此调整） ==========
    ICON_TOP_RATIO = 0.25
    ICON_SIZE = 128
    TITLE_SPACING_RATIO = 0.05
    TITLE_WIDTH = 300
    TITLE_HEIGHT = 30
    STATUS_SPACING_RATIO = 0.03
    STATUS_WIDTH = 300
    STATUS_HEIGHT = 25
    CENTRAL_START_OFFSET = 20
    CENTRAL_BOTTOM_MARGIN = 60
    # ==============================================

    def __init__(self, mode="bootloader"):
        super().__init__()
        self.logger = get_logger("FirmwareCheckPage")
        self.logger.info(f"固件烧录页初始化，模式: {mode}")
        self.mode = mode
        # 统一使用 resource_path 获取工具和固件路径
        self.wchisp_path = resource_path("tools/wchisp.exe")
        self.default_firmware_path = resource_path("firmware/CH32F103C8T6.hex")
        self.worker = None
        self.current_state = "ready"

        self.set_background()
        self.setup_ui()

        if self.mode == "bootloader":
            self.prepare_for_flash()
        else:
            self.check_firmware()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)
        self.setStyleSheet("")

    def setup_ui(self):
        self.central_widget = QWidget(self)
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setAlignment(Qt.AlignCenter)
        self.central_layout.setSpacing(20)

        # 顶部控件（手动定位）
        self.icon_label = QLabel(self)
        pixmap = QPixmap(resource_path("assets/nspro.png"))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.ICON_SIZE,
                self.ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.icon_label.setPixmap(pixmap)
        else:
            self.icon_label.setText("🎮")
        self.icon_label.setAlignment(Qt.AlignCenter)

        self.title_label = QLabel("CH32F103C8T6", self)
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("正在检测固件...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #333;")

        self.chip_info_label = QLabel("", self)
        self.chip_info_label.setAlignment(Qt.AlignCenter)
        self.chip_info_label.setStyleSheet("font-size: 12px; color: #555;")

        # 按钮和进度条（放入中央布局）
        self.btn_flash = QPushButton("🔥 开始烧录")
        self.btn_flash.setFixedSize(200, 40)
        self.btn_flash.clicked.connect(self.on_flash_clicked)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(300)

        self.central_layout.addWidget(self.chip_info_label)
        self.central_layout.addWidget(self.btn_flash, alignment=Qt.AlignCenter)
        self.central_layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        # 初始状态：显示烧录按钮
        self.btn_flash.setVisible(True)

        self.update_positions()

    def update_positions(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        icon_y = int(h * self.ICON_TOP_RATIO) - self.ICON_SIZE // 2
        if icon_y < 10:
            icon_y = 10
        icon_x = (w - self.ICON_SIZE) // 2
        self.icon_label.setGeometry(icon_x, icon_y, self.ICON_SIZE, self.ICON_SIZE)

        title_y = icon_y + self.ICON_SIZE + int(h * self.TITLE_SPACING_RATIO)
        title_x = (w - self.TITLE_WIDTH) // 2
        self.title_label.setGeometry(
            title_x, title_y, self.TITLE_WIDTH, self.TITLE_HEIGHT
        )

        status_y = title_y + self.TITLE_HEIGHT + int(h * self.STATUS_SPACING_RATIO)
        status_x = (w - self.STATUS_WIDTH) // 2
        self.status_label.setGeometry(
            status_x, status_y, self.STATUS_WIDTH, self.STATUS_HEIGHT
        )

        central_y = status_y + self.STATUS_HEIGHT + self.CENTRAL_START_OFFSET
        central_height = h - central_y - self.CENTRAL_BOTTOM_MARGIN
        if central_height < 100:
            central_height = 100
        self.central_widget.setGeometry(0, central_y, w, central_height)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.update_positions()

    def prepare_for_flash(self):
        self.current_state = "bootloader_ready"
        self.status_label.setText("✅ 设备已处于 Bootloader 模式")
        self.chip_info_label.setText("准备就绪，可开始烧录")
        self.btn_flash.setVisible(True)
        self.update_positions()

    def check_firmware(self):
        self.prepare_for_flash()

    def on_flash_clicked(self):
        self.logger.info("用户点击开始烧录")
        if not os.path.exists(self.default_firmware_path):
            self.logger.error(f"固件文件不存在: {self.default_firmware_path}")
            QMessageBox.critical(
                self, "错误", f"默认固件文件不存在:\n{self.default_firmware_path}"
            )
            return

        reply = QMessageBox.question(
            self,
            "确认烧录",
            f"即将烧录固件:\n{os.path.basename(self.default_firmware_path)}\n\n"
            "请确保设备已处于 Bootloader 模式（BOOT0=1），\n否则烧录将失败。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.logger.info("用户取消烧录")
            return

        self.btn_flash.setEnabled(False)
        self.status_label.setText("正在烧录固件，请勿断开设备...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.worker = FlashWorker(
            self.wchisp_path, "flash", [self.default_firmware_path]
        )
        self.worker.flash_progress.connect(self.on_flash_progress)
        self.worker.flash_finished.connect(self.on_flash_finished)
        self.worker.start()

    def on_flash_progress(self, percent, msg):
        self.progress_bar.setValue(percent)
        self.status_label.setText(msg)

    def on_flash_finished(self, success, msg):
        self.logger.info(f"烧录完成，成功: {success}，消息: {msg}")
        self.btn_flash.setEnabled(True)
        self.progress_bar.setVisible(False)

        if success:
            QMessageBox.information(
                self,
                "烧录完成",
                "固件烧录成功！\n\n"
                "请按以下步骤操作以进入工作模式：\n"
                "1. 断开 USB 电源。\n"
                "2. 将 BOOT0 跳线帽恢复为 GND（0）。\n"
                "3. 重新连接 USB。\n\n"
                "点击“确定”返回设备检测。",
                QMessageBox.Ok,
            )
            self.check_finished.emit(True)
        else:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("烧录失败")
            msg_box.setText(f"烧录过程中出现错误:\n{msg}\n\n是否重试？")
            retry_btn = msg_box.addButton("重新烧录", QMessageBox.AcceptRole)
            back_btn = msg_box.addButton("返回检测", QMessageBox.RejectRole)
            msg_box.setDefaultButton(retry_btn)
            msg_box.exec()
            if msg_box.clickedButton() == retry_btn:
                # 重置按钮状态和进度条
                self.btn_flash.setEnabled(True)
                self.progress_bar.setVisible(False)
                self.progress_bar.setValue(0)
                # 延迟调用，避免嵌套事件循环问题
                QTimer.singleShot(0, self.on_flash_clicked)
            else:
                self.check_finished.emit(True)
