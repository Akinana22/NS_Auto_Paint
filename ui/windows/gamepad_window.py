"""
模拟手柄主窗口 v2.2.0
包含设备检测、固件烧录、手柄连接和虚拟手柄的完整流程。
支持嵌入模式（作为普通控件嵌入标签页）。
- 扩展绘图数据接口，传递调色板类型标识 (is_preset)
"""

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from PySide6.QtGui import QIcon, QPixmap, QBrush, Qt
from PySide6.QtCore import QTimer

from ui.pages.device_check_page import DeviceCheckPage
from ui.pages.firmware_check_page import FirmwareCheckPage
from ui.pages.gamepad_control_page import GamepadControlPage
from ui.pages.virtual_gamepad_page import VirtualGamepadPage
from ui.pages.connection_success_page import ConnectionSuccessPage

from core.hal.controller import EasyConController
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class GamepadWindow(QMainWindow):
    def __init__(self, controller: EasyConController, embed_mode: bool = False):
        super().__init__()
        self.logger = get_logger("GamepadWindow")
        self.logger.info(f"模拟手柄窗口初始化，嵌入模式: {embed_mode}")

        self.controller = controller
        self.embed_mode = embed_mode

        # ----- 嵌入模式适配 -----
        if embed_mode:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setWindowTitle("单片机模拟手柄")
            self.resize(900, 600)
            self.setMinimumSize(900, 600)
            icon_path = resource_path("assets/nspro.ico")
            self.setWindowIcon(QIcon(icon_path))

        self.success_page = None
        self.pending_drawing_data = None

        self.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #aaa;
                border-radius: 5px;
                margin-top: 10px;
                background-color: rgba(255, 255, 255, 200);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 255);
            }
            QPushButton:pressed {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:disabled {
                background-color: rgba(200, 200, 200, 150);
                color: #888;
            }
            QProgressBar {
                border: 1px solid #aaa;
                border-radius: 3px;
                text-align: center;
                background-color: rgba(255, 255, 255, 200);
            }
            QProgressBar::chunk {
                background-color: #E60012;
                border-radius: 2px;
            }
            QTextEdit {
                background-color: rgba(255, 255, 255, 200);
            }
            QLabel {
                background-color: transparent;
                color: #2c2c2c;
            }
        """
        )

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.set_background()

        self.device_page = None
        self.firmware_page = None
        self.control_page = None
        self.virtual_gamepad_page = None

        self.create_device_page()

        if self.controller.is_connected():
            QTimer.singleShot(50, self._restore_connected_state)

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    # ================== 设备检测页安全清理 ==================
    def _cleanup_device_page(self):
        """安全移除设备检测页，终止其后台线程"""
        if self.device_page is not None:
            # 终止可能正在运行的 WMI 检测线程
            dm = self.device_page.driver_manager
            if dm.worker is not None and dm.worker.isRunning():
                dm.worker.quit()
                dm.worker.wait(2000)
            # 断开信号连接
            try:
                self.device_page.device_connected.disconnect()
            except Exception:
                pass
            try:
                self.device_page.restart_requested.disconnect()
            except Exception:
                pass
            # 从栈中移除并销毁
            idx = self.stacked_widget.indexOf(self.device_page)
            if idx >= 0:
                self.stacked_widget.removeWidget(self.device_page)
            self.device_page.deleteLater()
            self.device_page = None

    # ================== 设备检测页创建 ==================
    def create_device_page(self):
        self.logger.info("创建设备检测页面")
        self.device_page = DeviceCheckPage()
        self.device_page.device_connected.connect(self.on_device_connected)
        self.device_page.restart_requested.connect(self.recreate_device_page)
        self.stacked_widget.addWidget(self.device_page)
        self.stacked_widget.setCurrentIndex(0)

    def recreate_device_page(self):
        """重新创建设备检测页，并自动开始扫描（烧录成功/返回检测时调用）"""
        self.logger.info("重新创建设备检测页面")
        # 1. 清空所有页面
        while self.stacked_widget.count() > 0:
            widget = self.stacked_widget.widget(0)
            self.stacked_widget.removeWidget(widget)
            widget.deleteLater()
        # 2. 重置页面引用
        self.firmware_page = None
        self.control_page = None
        self.virtual_gamepad_page = None
        self.success_page = None
        # 3. 创建新的设备检测页
        self.create_device_page()
        # 4. 自动开始检测
        self.device_page.start_detection()

    def _restore_connected_state(self):
        """控制器已连接时直接进入成功页"""
        self.logger.info("控制器已连接，直接进入连接成功页面")
        self.stacked_widget.removeWidget(self.device_page)
        self.device_page.deleteLater()
        self.device_page = None
        self.success_page = ConnectionSuccessPage()
        self.success_page.virtual_gamepad_requested.connect(
            self.on_virtual_gamepad_requested
        )
        self.stacked_widget.addWidget(self.success_page)
        self.stacked_widget.setCurrentWidget(self.success_page)

    def on_device_connected(self, mode, port=None):
        self.logger.info(f"设备已连接，模式: {mode}, 端口: {port}")
        if mode == "normal":
            self.show_control_page()
        elif mode == "bootloader":
            self.logger.info("进入固件烧录页面")
            self.firmware_page = FirmwareCheckPage(mode="bootloader")
            self.firmware_page.check_finished.connect(self.on_firmware_check_finished)
            if self.stacked_widget.count() > 1:
                self.stacked_widget.removeWidget(self.stacked_widget.widget(1))
            self.stacked_widget.insertWidget(1, self.firmware_page)
            self.stacked_widget.setCurrentWidget(self.firmware_page)

    def on_firmware_check_finished(self, is_ok):
        self.logger.info(f"固件烧录完成，成功: {is_ok}")
        if is_ok:
            self.recreate_device_page()

    def show_control_page(self):
        self.logger.info("进入手柄控制页面")
        self.control_page = GamepadControlPage(self.controller)
        self.control_page.connection_success.connect(self.show_success_page)
        self.control_page.restart_detection_requested.connect(
            self._restart_to_device_page
        )
        self.stacked_widget.addWidget(self.control_page)
        self.stacked_widget.setCurrentWidget(self.control_page)

    def show_success_page(self):
        self.logger.info("进入连接成功庆祝页面")
        self.success_page = ConnectionSuccessPage()
        self.success_page.virtual_gamepad_requested.connect(
            self.on_virtual_gamepad_requested
        )
        if self.control_page:
            self.stacked_widget.removeWidget(self.control_page)
            self.control_page.deleteLater()
            self.control_page = None
        self.stacked_widget.addWidget(self.success_page)
        self.stacked_widget.setCurrentWidget(self.success_page)

    def on_virtual_gamepad_requested(self):
        self.logger.info("用户请求虚拟手柄页面")
        if not self.controller.is_connected():
            QMessageBox.warning(self, "未连接设备", "请先连接单片机后再使用虚拟手柄。")
            return

        if self.virtual_gamepad_page is None:
            self.virtual_gamepad_page = VirtualGamepadPage(self.controller)
            self.virtual_gamepad_page.return_requested.connect(
                self.on_return_from_virtual_gamepad
            )
            self.virtual_gamepad_page.restart_detection_requested.connect(
                self._restart_to_device_page
            )
            self.stacked_widget.addWidget(self.virtual_gamepad_page)
        self.stacked_widget.setCurrentWidget(self.virtual_gamepad_page)

        if self.pending_drawing_data:
            QTimer.singleShot(100, self._start_pending_drawing)

    def on_return_from_virtual_gamepad(self):
        self.logger.info("从虚拟手柄页面返回")
        if self.success_page:
            self.stacked_widget.setCurrentWidget(self.success_page)

    # ========== 外部调用接口 ==========
    def start_drawing_with_data(
        self,
        color_index_matrix,
        color_palette,
        pixel_size,
        is_preset,
        drawing_mode="image",
        brush_type=None,
        brush_size=None,
        press_data=None,
    ):
        self.logger.info(
            f"收到外部绘图请求，is_preset={is_preset}, drawing_mode={drawing_mode}, "
            f"brush_type={brush_type}, brush_size={brush_size}"
        )
        self.pending_drawing_data = (
            color_index_matrix,
            color_palette,
            pixel_size,
            is_preset,
            drawing_mode,
            brush_type,
            brush_size,
            press_data,
        )
        if self.stacked_widget.currentWidget() == self.virtual_gamepad_page:
            self._start_pending_drawing()
        else:
            if self.virtual_gamepad_page is None:
                self.virtual_gamepad_page = VirtualGamepadPage(self.controller)
                self.virtual_gamepad_page.return_requested.connect(
                    self.on_return_from_virtual_gamepad
                )
                self.virtual_gamepad_page.restart_detection_requested.connect(
                    self._restart_to_device_page
                )
                self.stacked_widget.addWidget(self.virtual_gamepad_page)
            self.stacked_widget.setCurrentWidget(self.virtual_gamepad_page)
            QTimer.singleShot(100, self._start_pending_drawing)

    def _start_pending_drawing(self):
        if self.pending_drawing_data:
            (
                matrix,
                palette,
                size,
                is_preset,
                drawing_mode,
                brush_type,
                brush_size,
                press_data,
            ) = self.pending_drawing_data
            self.pending_drawing_data = None
            self.logger.info(
                f"开始执行绘图任务，is_preset={is_preset}, drawing_mode={drawing_mode}, "
                f"brush_type={brush_type}, brush_size={brush_size}"
            )
            self.virtual_gamepad_page.start_drawing(
                matrix,
                palette,
                size,
                is_preset,
                drawing_mode,
                brush_type,
                brush_size,
                press_data,
            )
        else:
            self.logger.warning("没有待执行的绘图数据")

    # ========== 重新检测（统一入口）==========
    def _restart_to_device_page(self):
        """其他页面请求重新检测时的完整重置流程"""
        self.logger.info("执行重新检测，返回设备检测页")
        if self.controller.is_connected():
            self.controller.disconnect()
        # 安全清理当前设备页
        self._cleanup_device_page()
        # 清空所有其他页面
        while self.stacked_widget.count() > 0:
            widget = self.stacked_widget.widget(0)
            self.stacked_widget.removeWidget(widget)
            widget.deleteLater()
        self.firmware_page = None
        self.control_page = None
        self.virtual_gamepad_page = None
        self.success_page = None
        # 重建设备检测页
        self.create_device_page()
        self.device_page.start_detection()

    def closeEvent(self, event):
        self.logger.info("模拟手柄窗口关闭，保持控制器状态")
        event.accept()

    def open_config_management_page(self, config_manager, return_page):
        self.logger.info("打开配置管理页面")
        from ui.pages.config_management_page import ConfigManagementPage

        manage_page = ConfigManagementPage(config_manager, self)
        manage_page.applied.connect(lambda: self._refresh_key_mapping_page(return_page))
        manage_page.return_requested.connect(
            lambda: self._return_to_page(manage_page, return_page)
        )
        self.stacked_widget.addWidget(manage_page)
        self.stacked_widget.setCurrentWidget(manage_page)

    def _return_to_page(self, current_page, target_page):
        self.logger.info("返回上一级页面")
        self.stacked_widget.removeWidget(current_page)
        current_page.deleteLater()
        self.stacked_widget.setCurrentWidget(target_page)

    def _refresh_key_mapping_page(self, key_mapping_page):
        if key_mapping_page and hasattr(key_mapping_page, "_load_current_config"):
            key_mapping_page._load_current_config()
            key_mapping_page._refresh_ui_from_mapping()
            key_mapping_page.config_label.setText(
                f"当前配置：{key_mapping_page.config_manager.get_current_config_display_name()}"
            )
