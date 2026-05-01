"""
设备检测页面 v2.2.0
负责引导用户连接 CH32 设备，自动识别 Bootloader 或正常模式。
包含驱动检测、安装与烧录指引。
属于 UI 层页面，依赖 services 层进行驱动管理。
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QTextEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap, QBrush, QTextOption, QResizeEvent

from services.device.driver_manager import DriverManager
from services.device.serial_scanner import scan_serial_ports
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class DeviceCheckPage(QWidget):
    device_connected = Signal(str)  # "normal" 或 "bootloader"
    restart_requested = Signal()

    # ========== 布局比例参数（可在此调整） ==========
    ICON_TOP_RATIO = 0.25  # 图标顶部距离窗口顶部的比例（相对于窗口高度）
    ICON_SIZE = 128  # 图标边长（像素）
    TITLE_SPACING_RATIO = 0.05  # 标题与图标底部的间距比例（相对于窗口高度）
    TITLE_WIDTH = 300  # 标题宽度（像素）
    TITLE_HEIGHT = 30  # 标题高度（像素）
    STATUS_SPACING_RATIO = 0.03  # 状态标签与标题底部的间距比例（相对于窗口高度）
    STATUS_WIDTH = 300  # 状态标签宽度（像素）
    STATUS_HEIGHT = 25  # 状态标签高度（像素）
    CENTRAL_START_OFFSET = 20  # 中央区域与状态标签底部的固定偏移（像素）
    CENTRAL_BOTTOM_MARGIN = 60  # 中央区域底部预留空间（像素）
    LOG_HEIGHT_RATIO = 0.24  # 日志窗口高度比例（相对于窗口高度）
    # ==============================================

    def __init__(self):
        super().__init__()
        self.logger = get_logger("DeviceCheckPage")
        self.logger.info("设备检测页初始化")

        self.current_state = "ready"

        self.set_background()
        self.setup_ui()

        self.driver_manager = DriverManager()
        self.driver_manager.driver_ready.connect(self.on_driver_ready)
        self.driver_manager.driver_missing.connect(self.on_driver_missing)
        self.driver_manager.bootloader_not_found.connect(self.on_bootloader_not_found)
        self.driver_manager.need_admin.connect(self.on_need_admin)
        self.driver_manager.status_update.connect(self.on_status_update)

        self.handshake_workers = []
        self.found_normal = False

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
        # 中央容器（用于可布局的控件）
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

        self.status_label = QLabel("准备好了吗？", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #333;")

        # 静态提示标签
        self.hint_label = QLabel(
            "请确保接线方式符合其中一条：\n"
            "• 烧录模式：BOOT0置1, BOOT1置0，HUSB 接 PC\n"
            "• 正常模式：BOOT0与BOOT1置0，HUSB 接 PC，另一 USB 口接 NS 底座\n"
            "点击下方按钮开始检测"
        )
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: #666; font-size: 12px;")
        self.hint_label.setWordWrap(True)

        # 滚动日志文本框（透明、无边框，启用滚动条以便查看所有日志）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlainText("")
        self.log_text.setStyleSheet(
            "background-color: transparent; "
            "border: none; "
            "color: #666; "
            "font-size: 12px; "
            "font-family: inherit;"
        )
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.document().setDefaultTextOption(QTextOption(Qt.AlignCenter))
        self.log_text.setVisible(False)

        # 按钮区域（水平横排）
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(20)
        self.button_layout.setAlignment(Qt.AlignCenter)

        self.detect_btn = QPushButton("🔍 开始检测")
        self.detect_btn.setFixedSize(150, 35)
        self.detect_btn.clicked.connect(self.start_detection)

        self.retry_btn = QPushButton("🔄 重新检测")
        self.retry_btn.setFixedSize(150, 35)
        self.retry_btn.clicked.connect(self.retry_detection)
        self.retry_btn.setVisible(False)

        self.install_driver_btn = QPushButton("🔧 安装驱动")
        self.install_driver_btn.setFixedSize(150, 35)
        self.install_driver_btn.clicked.connect(self.on_install_driver_clicked)
        self.install_driver_btn.setVisible(False)

        self.flash_guide_btn = QPushButton("📖 查看烧录指引")
        self.flash_guide_btn.setFixedSize(150, 35)
        self.flash_guide_btn.clicked.connect(self.show_flash_guide)
        self.flash_guide_btn.setVisible(False)

        self.button_layout.addWidget(self.detect_btn)
        self.button_layout.addWidget(self.retry_btn)
        self.button_layout.addWidget(self.install_driver_btn)
        self.button_layout.addWidget(self.flash_guide_btn)

        # 添加到中央布局
        self.central_layout.addWidget(self.hint_label)
        self.central_layout.addWidget(self.log_text)
        self.central_layout.addLayout(self.button_layout)

        # 初始显示静态提示
        self.hint_label.setVisible(True)
        self.log_text.setVisible(False)

        self.update_positions()

    def update_positions(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        # 图标位置（顶部比例）
        icon_y = int(h * self.ICON_TOP_RATIO) - self.ICON_SIZE // 2
        if icon_y < 10:
            icon_y = 10
        icon_x = (w - self.ICON_SIZE) // 2
        self.icon_label.setGeometry(icon_x, icon_y, self.ICON_SIZE, self.ICON_SIZE)

        # 标题位置
        title_y = icon_y + self.ICON_SIZE + int(h * self.TITLE_SPACING_RATIO)
        title_x = (w - self.TITLE_WIDTH) // 2
        self.title_label.setGeometry(
            title_x, title_y, self.TITLE_WIDTH, self.TITLE_HEIGHT
        )

        # 状态标签位置
        status_y = title_y + self.TITLE_HEIGHT + int(h * self.STATUS_SPACING_RATIO)
        status_x = (w - self.STATUS_WIDTH) // 2
        self.status_label.setGeometry(
            status_x, status_y, self.STATUS_WIDTH, self.STATUS_HEIGHT
        )

        # 中央区域位置
        central_y = status_y + self.STATUS_HEIGHT + self.CENTRAL_START_OFFSET
        central_height = h - central_y - self.CENTRAL_BOTTOM_MARGIN
        if central_height < 100:
            central_height = 100
        self.central_widget.setGeometry(0, central_y, w, central_height)

        # 日志窗口高度比例（仅在显示时生效，但预先设置）
        log_height = int(h * self.LOG_HEIGHT_RATIO)
        if log_height < 80:
            log_height = 80
        self.log_text.setFixedHeight(log_height)

        # 输出位置日志
        self.logger.debug(f"状态-{self.current_state}: 图标位置 ({icon_x},{icon_y})")
        self.logger.debug(f"状态-{self.current_state}: 标题位置 ({title_x},{title_y})")
        self.logger.debug(
            f"状态-{self.current_state}: 状态词条位置 ({status_x},{status_y})"
        )
        self.logger.debug(
            f"状态-{self.current_state}: 中央控件起始Y={central_y}, 高度={central_height}"
        )
        self.logger.debug(f"状态-{self.current_state}: 日志窗口高度={log_height}")

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.update_positions()

    def start_detection(self):
        self.logger.info("用户点击开始检测")
        self.current_state = "detecting"
        self.status_label.setText("正在检测设备...")
        # 隐藏静态提示，显示滚动日志
        self.hint_label.setVisible(False)
        self.log_text.setVisible(True)
        self._append_log("正在扫描串口并检测 Bootloader...")
        # 隐藏开始检测按钮，显示其他按钮
        self.detect_btn.setVisible(False)
        self.retry_btn.setVisible(False)
        self.flash_guide_btn.setVisible(False)
        self.install_driver_btn.setVisible(False)
        self.found_normal = False

        self.driver_manager.check_bootloader_and_driver()
        self.update_positions()

    def on_driver_ready(self):
        self.logger.info("驱动就绪，进入 Bootloader 模式")
        self.current_state = "bootloader"
        self.status_label.setText("✅ 设备处于 Bootloader 模式，驱动正常")
        self._append_log("正在进入固件烧录界面...")
        QTimer.singleShot(800, lambda: self.device_connected.emit("bootloader"))
        self.update_positions()

    def on_driver_missing(self, message):
        self.logger.warning(f"驱动缺失: {message}")
        self.status_label.setText("⚠️ 缺少 WinUSB 驱动")
        self._append_log(message)
        # 将“重新检测”按钮改为直接调用 start_detection
        # 注意：此时 retry_btn 原本连接的是 retry_detection，需要重新连接
        try:
            self.retry_btn.clicked.disconnect()
        except:
            pass
        self.retry_btn.clicked.connect(self.start_detection)
        self.retry_btn.setVisible(True)
        # 安装驱动按钮保持可见
        self.install_driver_btn.setVisible(True)
        # 确保其他按钮状态正确
        self.detect_btn.setVisible(False)
        self.flash_guide_btn.setVisible(True)
        self.update_positions()

    def on_bootloader_not_found(self, message):
        self.logger.info(f"未找到 Bootloader 设备: {message}")
        self.current_state = "no_bootloader"
        self.status_label.setText("未检测到 Bootloader 设备")
        self._append_log("正在检测正常工作模式（串口）...")
        self.try_serial_detection()
        self.update_positions()

    def try_serial_detection(self):
        self.logger.info("开始串口检测")
        wch_ports = scan_serial_ports()
        if wch_ports:
            self.current_state = "normal_mode"
            self.status_label.setText("ℹ️ 当前为正常模式")
            self._append_log(
                f"已发现串口: {', '.join(wch_ports)}\n"
                "请按下单片机的reset按钮。\n"
                "如果绿灯闪烁，说明固件已就绪。\n"
                "若未闪烁，请检查usb口是否已接入ns底座"
            )
            self.confirm_firmware_btn = QPushButton("✅ 绿灯闪烁，继续")
            self.confirm_firmware_btn.setFixedSize(150, 35)
            self.confirm_firmware_btn.clicked.connect(
                lambda: self.on_user_confirm_normal(wch_ports[0])
            )
            self.button_layout.addWidget(self.confirm_firmware_btn)
            self.confirm_firmware_btn.setVisible(True)
            self.retry_btn.setVisible(True)
            self.flash_guide_btn.setVisible(True)
        else:
            self.on_no_device()
        self.update_positions()

    def on_user_confirm_normal(self, port):
        self.logger.info(f"用户确认固件正常，端口: {port}")
        self.current_state = "confirmed"
        if hasattr(self, "confirm_firmware_btn"):
            self.confirm_firmware_btn.setVisible(False)
        self.device_connected.emit("normal")
        self.update_positions()

    def on_no_device(self):
        self.logger.warning("未检测到任何设备")
        self.current_state = "no_device"
        self.status_label.setText("⚠️ 未检测到有效设备")
        self._append_log(
            "设备可能未烧录固件，或未处于正常工作模式。\n\n"
            "检查设备是否正确接入，请尝试重新插拔或按下reset键后重新检查\n"
            "还未解决请按照以下步骤进入烧录模式完成烧录：\n"
            "1. 断开 USB 电源\n"
            "2. 将 BOOT0 跳线帽设置为 1（VCC/3.3V），BOOT1 保持 0（GND）\n"
            "3. 通过 HUSB 接口重新上电\n"
            "4. 点击“重新检测”"
        )
        # 将开始检测按钮改为“重新检测”，并连接到开始检测（直接重新检测）
        self.detect_btn.setText("重新检测")
        # 断开原有连接（如果存在）
        try:
            self.detect_btn.clicked.disconnect()
        except:
            pass
        self.detect_btn.clicked.connect(self.start_detection)
        self.detect_btn.setVisible(True)
        # 隐藏原本的重新检测按钮
        self.retry_btn.setVisible(False)
        self.flash_guide_btn.setVisible(True)
        self.update_positions()

    def show_flash_guide(self):
        guide = (
            "【烧录准备步骤】\n\n"
            "1. 断开开发板 USB 电源。\n"
            "2. 将 BOOT0 跳线帽接到 VCC/3.3V（标记为 1）。\n"
            "3. 将 BOOT1 跳线帽保持 GND（标记为 0）。\n"
            "4. 使用 HUSB 接口重新连接 USB 线。\n\n"
            "完成后点击“重新检测”。"
        )
        QMessageBox.information(self, "烧录模式指引", guide)

    def on_install_driver_clicked(self):
        self.logger.info("用户点击安装驱动")
        self.install_driver_btn.setEnabled(False)
        self.status_label.setText("正在安装驱动，请稍候...")
        self._append_log("正在安装驱动...")
        success = self.driver_manager.install_driver()
        self.install_driver_btn.setEnabled(True)
        if success:
            self.logger.info("驱动安装成功")
            self.status_label.setText("✅ 驱动安装成功！")
            self._append_log("驱动安装成功😁\n请点击“重新检测”。")
            self.install_driver_btn.setVisible(False)
            self.retry_btn.setVisible(True)
        else:
            self.logger.error("驱动安装失败")
            self.status_label.setText("❌ 驱动安装失败")
            self._append_log(
                "请尝试以管理员身份运行程序，或手动使用 Zadig 安装 WinUSB 驱动。"
            )
            self.retry_btn.setVisible(True)
        self.update_positions()

    def on_need_admin(self):
        self.logger.warning("需要管理员权限")
        reply = QMessageBox.question(
            self,
            "需要管理员权限",
            "安装 USB 驱动需要管理员权限。\n\n点击“是”将以管理员身份重新启动程序。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.driver_manager.request_admin_privilege():
                QTimer.singleShot(500, lambda: __import__("sys").exit(0))
            else:
                QMessageBox.warning(
                    self, "提示", "无法获取管理员权限，请手动以管理员身份运行程序。"
                )

    def on_status_update(self, message: str):
        self._append_log(message)

    def _append_log(self, message: str):
        current = self.log_text.toPlainText()
        if current.strip() == "":
            self.log_text.setPlainText(message)
        else:
            self.log_text.append(message)
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def retry_detection(self):
        self.logger.info("用户点击重新检测")
        self.restart_requested.emit()
