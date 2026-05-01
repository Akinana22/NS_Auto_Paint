"""
主窗口 v2.2.0
标签页容器，负责工具选择、设备检测、固件烧录、像素绘图与手柄模拟的调度。
不包含绘图、通信或路径评估等业务逻辑。
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QTabBar,
)
import ctypes
from PySide6.QtGui import QIcon, QPixmap, QBrush
from PySide6.QtCore import QTimer, Qt

from ui.pages.tool_select_page import ToolSelectPage
from ui.windows.pixel_gen_window import PixelGenWindow
from ui.windows.gamepad_window import GamepadWindow

from core.hal.controller import EasyConController
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = get_logger("MainWindow")
        self.logger.info("主窗口初始化（标签页模式 v2.2.0）")

        self.setWindowTitle("NS Auto Painter")
        self.resize(900, 600)
        self.setMinimumSize(900, 600)
        icon_path = resource_path("assets/joycon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.set_background()

        # 全局手柄控制器（状态持久化）
        self.gamepad_controller = EasyConController()

        # 创建标签页容器
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tab_widget)

        # 工具选择页（固定标签，不可关闭）
        self.tool_page = ToolSelectPage()
        self.tool_page.tool_selected.connect(self.on_tool_selected)
        self._add_fixed_tab(self.tool_page, "🛠️ 工具选择")

        # 窗口实例引用
        self.gamepad_tab_instance = None
        self.pixel_tab_instance = None

        self._setup_system_menu()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg0.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def _add_fixed_tab(self, widget, title):
        index = self.tab_widget.addTab(widget, title)
        close_btn = self.tab_widget.tabBar().tabButton(index, QTabBar.RightSide)
        if close_btn:
            close_btn.hide()
        return index

    def _add_closable_tab(self, widget, title, icon_path=None):
        index = self.tab_widget.addTab(widget, title)
        if icon_path:
            self.tab_widget.setTabIcon(index, QIcon(icon_path))
        self.tab_widget.setCurrentIndex(index)
        return index

    def on_tool_selected(self, tool_name):
        self.logger.info(f"选择工具: {tool_name}")

        if tool_name == "dream_life":
            if self.pixel_tab_instance is None:
                self.logger.info("创建新的像素绘图实例")
                self.pixel_tab_instance = PixelGenWindow(embed_mode=True)
                self.pixel_tab_instance.set_main_window(self)
            else:
                self.logger.info("复用已有的像素绘图实例")

            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == self.pixel_tab_instance:
                    self.tab_widget.setCurrentIndex(i)
                    return

            self._add_closable_tab(
                self.pixel_tab_instance,
                "朋友收集",
                resource_path("assets/tomodachilife.ico"),
            )

        elif tool_name == "splatoon":
            QMessageBox.information(self, "提示", "斯普拉遁功能开发中，敬请期待！")

        elif tool_name == "gamepad":
            if self.gamepad_tab_instance is None:
                self.logger.info("创建新的模拟手柄实例")
                self.gamepad_tab_instance = GamepadWindow(
                    self.gamepad_controller, embed_mode=True
                )
            else:
                self.logger.info("复用已有的模拟手柄实例")

            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == self.gamepad_tab_instance:
                    self.tab_widget.setCurrentIndex(i)
                    return

            self._add_closable_tab(
                self.gamepad_tab_instance, "模拟手柄", resource_path("assets/nspro.ico")
            )

    def _on_tab_close_requested(self, index):
        widget = self.tab_widget.widget(index)

        if widget == self.tool_page:
            return

        self.logger.info(f"关闭标签页: {self.tab_widget.tabText(index)}")

        if widget == self.gamepad_tab_instance:
            self.tab_widget.removeTab(index)
            self.logger.info("模拟手柄标签页已关闭，实例保留")
            return

        if widget == self.pixel_tab_instance:
            self.tab_widget.removeTab(index)
            self.logger.info("像素绘图标签页已关闭，实例保留")
            return

        self.tab_widget.removeTab(index)
        widget.deleteLater()

    def _on_tab_changed(self, index):
        pass

    def on_drawing_data_ready(
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
            f"MainWindow.on_drawing_data_ready 被调用，is_preset={is_preset}, "
            f"drawing_mode={drawing_mode}, brush_type={brush_type}, brush_size={brush_size}"
        )
        if not self.gamepad_controller.is_connected():
            self.logger.error("控制器未连接，无法执行绘图")
            QMessageBox.warning(self, "未连接设备", "请先连接单片机后再执行绘图。")
            return

        if self.gamepad_tab_instance is None:
            self.logger.info("创建新的模拟手柄实例以执行绘图")
            self.gamepad_tab_instance = GamepadWindow(
                self.gamepad_controller, embed_mode=True
            )
            self._add_closable_tab(
                self.gamepad_tab_instance, "模拟手柄", resource_path("assets/nspro.ico")
            )
            QTimer.singleShot(
                200,
                lambda: self._send_drawing_to_gamepad(
                    color_index_matrix,
                    color_palette,
                    pixel_size,
                    is_preset,
                    drawing_mode,
                    brush_type,
                    brush_size,
                    press_data,
                ),
            )
        else:
            found = False
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == self.gamepad_tab_instance:
                    self.tab_widget.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                self._add_closable_tab(
                    self.gamepad_tab_instance,
                    "模拟手柄",
                    resource_path("assets/nspro.ico"),
                )
            self.logger.info("模拟手柄实例已存在，直接发送绘图数据")
            self._send_drawing_to_gamepad(
                color_index_matrix,
                color_palette,
                pixel_size,
                is_preset,
                drawing_mode,
                brush_type,
                brush_size,
                press_data,
            )

    def _send_drawing_to_gamepad(
        self,
        color_index_matrix,
        color_palette,
        pixel_size,
        is_preset,
        drawing_mode,
        brush_type,
        brush_size,
        press_data,
    ):
        if self.gamepad_tab_instance:
            self.gamepad_tab_instance.start_drawing_with_data(
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
            self.logger.error("游戏手柄窗口不存在")

    def closeEvent(self, event):
        self.logger.info("主窗口关闭，清理资源")
        if hasattr(self, "virtual_gamepad_page") and self.virtual_gamepad_page:
            self.virtual_gamepad_page.stop_drawing()
        if self.gamepad_tab_instance:
            self.gamepad_tab_instance.close()
            self.gamepad_tab_instance.deleteLater()
        if self.pixel_tab_instance:
            self.pixel_tab_instance.close()
            self.pixel_tab_instance.deleteLater()
        from services.audio_manager import AudioManager

        audio = AudioManager()
        audio.stop()
        event.accept()

    def _setup_system_menu(self):
        """在系统菜单中添加自定义项（右键标题栏可见）"""
        if hasattr(ctypes, "windll"):
            hwnd = int(self.winId())
            hMenu = ctypes.windll.user32.GetSystemMenu(hwnd, False)
            if hMenu:
                ctypes.windll.user32.AppendMenuW(hMenu, 0x800, 0, None)  # 分隔线
                ctypes.windll.user32.AppendMenuW(hMenu, 0x0, 1000, "关于(&A)")
                ctypes.windll.user32.AppendMenuW(hMenu, 0x0, 1001, "联系作者(&E)")
                ctypes.windll.user32.AppendMenuW(hMenu, 0x0, 1002, "请作者喝咖啡(&B)")

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0112:
                if msg.wParam == 1000:
                    self.show_about()
                    return True, 0
                elif msg.wParam == 1001:
                    self.show_contact()
                    return True, 0
                elif msg.wParam == 1002:
                    self.show_coffee()
                    return True, 0
        return super().nativeEvent(eventType, message)

    def show_about(self):
        QMessageBox.about(
            self,
            "关于 NS Auto Painter",
            "NS Auto Painter v2.2.0\n\n"
            "用于 NS 的自动像素绘图工具。\n"
            "基于 CH32F103 单片机模拟 Switch Pro 手柄。\n\n"
            "作者：Akinana\n",
        )

    def show_contact(self):
        QMessageBox.about(
            self,
            "联系作者",
            "如有问题或建议，请通过以下方式联系：\n\n\n" "邮箱: 1912665242@qq.com",
        )

    def show_coffee(self):
        """显示请喝咖啡的对话框，包含两个二维码图片及各自说明"""
        from PySide6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QVBoxLayout,
            QLabel,
            QSpacerItem,
            QSizePolicy,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("请作者喝咖啡 ☕")
        dialog.setFixedSize(520, 300)  # 稍增高一些

        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)  # 用间隔器控制间距，设为0

        # 顶部文字
        text_label = QLabel("如果觉得软件好用，欢迎请作者喝杯咖啡！")
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet(
            "font-size: 13px; color: #333; background: transparent;"
        )
        layout.addWidget(text_label)

        # 文字与二维码之间的间隔
        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )

        # 两个二维码水平排列，每个下方有文字说明
        qr_layout = QHBoxLayout()
        qr_layout.setSpacing(0)

        # 支付宝二维码及其说明
        zfb_vbox = QVBoxLayout()
        zfb_vbox.setSpacing(8)  # 二维码与文字之间的间距

        zfb_path = resource_path("assets/zfb.png")
        zfb_pix = QPixmap(zfb_path)
        if not zfb_pix.isNull():
            zfb_pix = zfb_pix.scaled(
                160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        zfb_label = QLabel()
        zfb_label.setPixmap(zfb_pix)
        zfb_label.setAlignment(Qt.AlignCenter)

        zfb_text = QLabel("支付宝")
        zfb_text.setAlignment(Qt.AlignCenter)
        zfb_text.setStyleSheet("font-size: 12px; color: #888; background: transparent;")

        zfb_vbox.addWidget(zfb_label)
        zfb_vbox.addWidget(zfb_text)

        # 微信二维码及其说明
        wx_vbox = QVBoxLayout()
        wx_vbox.setSpacing(8)

        wx_path = resource_path("assets/wx.png")
        wx_pix = QPixmap(wx_path)
        if not wx_pix.isNull():
            wx_pix = wx_pix.scaled(
                160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        wx_label = QLabel()
        wx_label.setPixmap(wx_pix)
        wx_label.setAlignment(Qt.AlignCenter)

        wx_text = QLabel("微信")
        wx_text.setAlignment(Qt.AlignCenter)
        wx_text.setStyleSheet("font-size: 12px; color: #888; background: transparent;")

        wx_vbox.addWidget(wx_label)
        wx_vbox.addWidget(wx_text)

        qr_layout.addLayout(zfb_vbox)
        qr_layout.addLayout(wx_vbox)

        layout.addLayout(qr_layout)

        # 底部弹性空间，使整体偏上，距底部更远
        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        dialog.setLayout(layout)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.exec()
