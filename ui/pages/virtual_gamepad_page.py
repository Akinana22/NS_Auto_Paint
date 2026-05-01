"""
虚拟手柄页面 v2.2.0
包含手动按键测试（支持键盘映射）、自动按键测试、按键映射入口、按键计数功能。
新增：绘图执行（由像素窗口定稿后自动调用），支持预设调色盘模式。
布局优化：日志区与手动测试区左右并列，高度固定；日志右键菜单支持清除、全选、复制。
绘图执行与断点恢复全部通过 services.drawing_executor.DrawingExecutor 完成，
UI 不直接操作调度器或指令生成器。
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QGridLayout,
    QGroupBox,
    QProgressBar,
    QSlider,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QBrush, QKeyEvent, QAction, QKeySequence

from core.hal.controller import EasyConController
from core.hal.constants import SwitchButtons, SwitchHAT
from core.utils.logger import get_logger
from core.utils.resource import resource_path
from core.utils.config_manager import ConfigManager
from core.scripting.checkpoint_manager import CheckpointManager
from core.scheduling.timing_config import TimingConfig
from services.testing.auto_test import AutoTestController
from services.testing.manual_test import ManualTestHandler
from services.app_settings import AppSettings
from services.drawing_executor import DrawingExecutor
from ui.pages.key_mapping_page import KeyMappingPage


class VirtualGamepadPage(QWidget):
    return_requested = Signal()
    restart_detection_requested = Signal()

    def __init__(self, controller: EasyConController):
        super().__init__()
        self.logger = get_logger("VirtualGamepadPage")
        self.controller = controller

        self.auto_test_ctrl = AutoTestController(controller)
        self.manual_handler = ManualTestHandler(controller)
        self.settings = AppSettings()
        self._load_key_mapping_from_config()

        # 绘图执行服务（异步）
        self.drawing_executor = DrawingExecutor(controller)
        self.drawing_executor.log_signal.connect(self._on_drawing_log)
        self.drawing_executor.progress_signal.connect(self._on_drawing_progress)
        self.drawing_executor.finished_signal.connect(self._on_drawing_finished)
        self.drawing_executor.error_signal.connect(self._on_drawing_error)

        self.button_states = {
            name: False
            for name in [
                "A",
                "B",
                "X",
                "Y",
                "L",
                "R",
                "ZL",
                "ZR",
                "Plus",
                "Minus",
                "Home",
                "Capture",
                "L3",
                "R3",
                "Up",
                "Down",
                "Left",
                "Right",
            ]
        }
        self.button_widgets = {}

        self.set_background()
        self.setup_ui()
        self.apply_style()
        self.setFocusPolicy(Qt.StrongFocus)

        # 自动测试信号
        self.auto_test_ctrl.status_changed.connect(self.status_label.setText)
        self.auto_test_ctrl.log_message.connect(self._on_auto_log)
        self.auto_test_ctrl.progress_changed.connect(self.progress_bar.setValue)
        self.auto_test_ctrl.test_finished.connect(self._on_auto_test_finished)
        self.manual_handler.counts_updated.connect(self._on_counts_updated)

    def _load_key_mapping_from_config(self):
        """从 ConfigManager 加载当前激活的按键映射，若失败则回退到 AppSettings 默认"""
        try:
            cm = ConfigManager("key_mapping")
            active = cm.get_active_config()
            data = active.get("data", {})
            if data and "mapping" in data:
                self.key_mapping = data["mapping"].copy()
                return
        except Exception:
            pass
        # 回退到 QSettings 默认值
        self.key_mapping = self.settings.load_key_mapping()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg1.webp"))
        if not pixmap.isNull():
            brush = QBrush(pixmap)
            palette = self.palette()
            palette.setBrush(self.backgroundRole(), brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def update_connection_status(self):
        if self.controller.is_connected():
            self.status_label.setText("虚拟手柄就绪")
            self.status_label.setStyleSheet("font-size: 14px; color: #333;")
        else:
            self.status_label.setText("⚠️ 未连接设备，请点击「重新检测」按钮")
            self.status_label.setStyleSheet("font-size: 14px; color: red;")

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setSpacing(15)

        self.status_label = QLabel("虚拟手柄就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #333;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(400)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        # ---------- 三栏布局：手动测试 | 时序参数 | 日志 ----------
        split_layout = QHBoxLayout()
        split_layout.setSpacing(10)

        # 左侧：手动测试面板，固定宽度
        manual_group = QGroupBox("手动测试（点击按钮或按键盘映射键）")
        manual_group.setFixedWidth(330)
        manual_layout = QGridLayout()
        manual_layout.setSpacing(5)
        manual_layout.setContentsMargins(10, 15, 10, 10)

        buttons_layout = QGridLayout()
        buttons_layout.setHorizontalSpacing(5)
        buttons_layout.setVerticalSpacing(3)
        btn_list = [
            ("A", SwitchButtons.A),
            ("B", SwitchButtons.B),
            ("X", SwitchButtons.X),
            ("Y", SwitchButtons.Y),
            ("L", SwitchButtons.L),
            ("R", SwitchButtons.R),
            ("ZL", SwitchButtons.ZL),
            ("ZR", SwitchButtons.ZR),
            ("+", SwitchButtons.PLUS),
            ("-", SwitchButtons.MINUS),
            ("HOME", SwitchButtons.HOME),
            ("截图", SwitchButtons.CAPTURE),
            ("L3", SwitchButtons.LCLICK),
            ("R3", SwitchButtons.RCLICK),
        ]
        for idx, (name, mask) in enumerate(btn_list):
            btn = QPushButton(name)
            btn.setFixedSize(60, 28)
            btn.clicked.connect(
                lambda checked, n=name, m=mask: self.manual_handler.test_button(n, m)
            )
            self.button_widgets[name] = btn
            row = idx // 4
            col = idx % 4
            buttons_layout.addWidget(btn, row, col)

        hat_layout = QGridLayout()
        hat_layout.setHorizontalSpacing(5)
        hat_layout.setVerticalSpacing(3)
        hat_list = [
            ("↑", SwitchHAT.TOP),
            ("↓", SwitchHAT.BOTTOM),
            ("←", SwitchHAT.LEFT),
            ("→", SwitchHAT.RIGHT),
            ("↖", SwitchHAT.TOP_LEFT),
            ("↗", SwitchHAT.TOP_RIGHT),
            ("↙", SwitchHAT.BOTTOM_LEFT),
            ("↘", SwitchHAT.BOTTOM_RIGHT),
        ]
        for idx, (name, hat) in enumerate(hat_list):
            btn = QPushButton(name)
            btn.setFixedSize(60, 28)
            btn.clicked.connect(
                lambda checked, n=name, h=hat: self.manual_handler.test_hat(n, h)
            )
            self.button_widgets[name] = btn
            row = idx // 4
            col = idx % 4
            hat_layout.addWidget(btn, row, col)

        ls_layout = QGridLayout()
        ls_layout.setHorizontalSpacing(5)
        ls_layout.setVerticalSpacing(3)
        ls_list = [("L↑", 128, 0), ("L↓", 128, 255), ("L←", 0, 128), ("L→", 255, 128)]
        for idx, (name, lx, ly) in enumerate(ls_list):
            btn = QPushButton(name)
            btn.setFixedSize(60, 28)
            btn.clicked.connect(
                lambda checked, n=name, x=lx, y=ly: self.manual_handler.test_lstick(
                    n, x, y
                )
            )
            self.button_widgets[name] = btn
            row = idx // 4
            col = idx % 4
            ls_layout.addWidget(btn, row, col)

        rs_layout = QGridLayout()
        rs_layout.setHorizontalSpacing(5)
        rs_layout.setVerticalSpacing(3)
        rs_list = [("R↑", 128, 0), ("R↓", 128, 255), ("R←", 0, 128), ("R→", 255, 128)]
        for idx, (name, rx, ry) in enumerate(rs_list):
            btn = QPushButton(name)
            btn.setFixedSize(60, 28)
            btn.clicked.connect(
                lambda checked, n=name, x=rx, y=ry: self.manual_handler.test_rstick(
                    n, x, y
                )
            )
            self.button_widgets[name] = btn
            row = idx // 4
            col = idx % 4
            rs_layout.addWidget(btn, row, col)

        manual_layout.addWidget(QLabel("普通按键:"), 0, 0, Qt.AlignRight)
        manual_layout.addLayout(buttons_layout, 0, 1)
        manual_layout.addWidget(QLabel("十字键:"), 1, 0, Qt.AlignRight)
        manual_layout.addLayout(hat_layout, 1, 1)
        manual_layout.addWidget(QLabel("左摇杆:"), 2, 0, Qt.AlignRight)
        manual_layout.addLayout(ls_layout, 2, 1)
        manual_layout.addWidget(QLabel("右摇杆:"), 3, 0, Qt.AlignRight)
        manual_layout.addLayout(rs_layout, 3, 1)

        manual_group.setLayout(manual_layout)
        split_layout.addWidget(manual_group)

        # 中间：时序参数调节面板
        timing_group = QGroupBox("时序参数调节 (ms)")
        timing_group.setFixedWidth(250)
        timing_layout = QVBoxLayout()
        timing_layout.setSpacing(8)

        self._create_timing_slider(
            timing_layout,
            "按键间隔",
            50,
            500,
            TimingConfig.key_interval_ms,
            lambda v: TimingConfig.set_params(key_interval=v),
        )
        self._create_timing_slider(
            timing_layout,
            "等待间隔",
            50,
            500,
            TimingConfig.wait_interval_ms,
            lambda v: TimingConfig.set_params(wait_interval=v),
        )
        self._create_timing_slider(
            timing_layout,
            "绘制间隔",
            50,
            500,
            TimingConfig.draw_ms,
            lambda v: TimingConfig.set_params(draw=v),
        )
        self._create_timing_slider(
            timing_layout,
            "按压保持",
            10,
            100,
            TimingConfig.press_hold_ms,
            lambda v: TimingConfig.set_params(press_hold=v),
        )

        timing_group.setLayout(timing_layout)
        split_layout.addWidget(timing_group)

        # 右侧：日志区域，无尺寸限制
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("操作日志...")
        self.log_text.setStyleSheet("background-color: rgba(255, 255, 255, 200);")
        self._setup_log_context_menu()
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        split_layout.addWidget(log_group, 1)

        main_layout.addLayout(split_layout)

        hint = QLabel("键盘映射: 可在「按键映射」中自定义")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 11px; color: #666;")
        main_layout.addWidget(hint)

        # ---------- 底部按钮栏 ----------
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)

        self.count_btn = QPushButton("📊 开始计数")
        self.count_btn.setFixedSize(110, 40)
        self.count_btn.clicked.connect(self.on_count_clicked)

        self.restart_btn = QPushButton("🔄 重新检测")
        self.restart_btn.setFixedSize(110, 40)
        self.restart_btn.clicked.connect(self.on_restart_clicked)

        right_btn_layout = QHBoxLayout()
        right_btn_layout.setSpacing(20)

        self.auto_test_btn = QPushButton("🧪 自动测试")
        self.auto_test_btn.setFixedSize(110, 40)
        self.auto_test_btn.clicked.connect(self.on_auto_test_clicked)

        self.mapping_btn = QPushButton("⌨️ 按键映射")
        self.mapping_btn.setFixedSize(110, 40)
        self.mapping_btn.clicked.connect(self.on_mapping_clicked)

        self.stop_drawing_btn = QPushButton("⏹️ 停止绘图")
        self.stop_drawing_btn.setFixedSize(110, 40)
        self.stop_drawing_btn.setEnabled(False)
        self.stop_drawing_btn.clicked.connect(self.stop_drawing)

        # 恢复绘图按钮
        self.restore_drawing_btn = QPushButton("🔄 恢复绘图")
        self.restore_drawing_btn.setFixedSize(110, 40)
        self.restore_drawing_btn.setEnabled(False)
        self.restore_drawing_btn.clicked.connect(self.on_restore_drawing_clicked)

        self.return_btn = QPushButton("↩️ 返回")
        self.return_btn.setFixedSize(110, 40)
        self.return_btn.clicked.connect(self.on_return_clicked)

        right_btn_layout.addWidget(self.auto_test_btn)
        right_btn_layout.addWidget(self.mapping_btn)
        right_btn_layout.addWidget(self.stop_drawing_btn)
        right_btn_layout.addWidget(self.restore_drawing_btn)
        right_btn_layout.addWidget(self.return_btn)

        bottom_layout.addWidget(self.count_btn)
        bottom_layout.addWidget(self.restart_btn)
        bottom_layout.addStretch()
        bottom_layout.addLayout(right_btn_layout)

        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

        self.update_button_styles()

    def _create_timing_slider(
        self, parent_layout, name, min_val, max_val, default_val, callback
    ):
        """创建一个带标签的滑块，用于调节时序参数"""
        label = QLabel(f"{name}: {default_val}")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 11px; color: #333; background: transparent;")

        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(10)
        slider.valueChanged.connect(
            lambda v, lbl=label, cb=callback: [lbl.setText(f"{name}: {v}"), cb(v)]
        )

        parent_layout.addWidget(label)
        parent_layout.addWidget(slider)

    def _setup_log_context_menu(self):
        self.log_text.setContextMenuPolicy(Qt.ActionsContextMenu)

        select_all_action = QAction("全选", self.log_text)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self.log_text.selectAll)
        self.log_text.addAction(select_all_action)

        copy_action = QAction("复制", self.log_text)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.log_text.copy)
        self.log_text.addAction(copy_action)

        clear_action = QAction("清除", self.log_text)
        clear_action.triggered.connect(self.log_text.clear)
        self.log_text.addAction(clear_action)

    def apply_style(self):
        self.setStyleSheet(
            """
            QLabel { color: #2c2c2c; }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #aaa;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d0d0d0; }
            QPushButton:pressed { background-color: #4CAF50; color: white; }
            QProgressBar {
                border: 1px solid #aaa;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #E60012;
                border-radius: 2px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #aaa;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """
        )

    def update_button_styles(self):
        for name, btn in self.button_widgets.items():
            if self.button_states.get(name, False):
                btn.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #4CAF50;
                        border: 2px solid #2E7D32;
                        border-radius: 5px;
                        font-weight: bold;
                        color: white;
                    }
                """
                )
            else:
                btn.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #e0e0e0;
                        border: 1px solid #aaa;
                        border-radius: 5px;
                        font-weight: bold;
                        color: #333;
                    }
                """
                )

    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        key = event.key()
        for name, mapped_key in self.key_mapping.items():
            if key == mapped_key:
                self.button_states[name] = True
                self.update_button_styles()
                self._trigger_by_name(name)
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        key = event.key()
        for name, mapped_key in self.key_mapping.items():
            if key == mapped_key:
                self.button_states[name] = False
                self.update_button_styles()
                event.accept()
                return
        super().keyReleaseEvent(event)

    def _trigger_by_name(self, name: str):
        btn_map = {
            "A": SwitchButtons.A,
            "B": SwitchButtons.B,
            "X": SwitchButtons.X,
            "Y": SwitchButtons.Y,
            "L": SwitchButtons.L,
            "R": SwitchButtons.R,
            "ZL": SwitchButtons.ZL,
            "ZR": SwitchButtons.ZR,
            "Plus": SwitchButtons.PLUS,
            "Minus": SwitchButtons.MINUS,
            "Home": SwitchButtons.HOME,
            "Capture": SwitchButtons.CAPTURE,
            "L3": SwitchButtons.LCLICK,
            "R3": SwitchButtons.RCLICK,
        }
        if name in btn_map:
            self.manual_handler.test_button(name, btn_map[name])
            return
        hat_map = {
            "Up": SwitchHAT.TOP,
            "Down": SwitchHAT.BOTTOM,
            "Left": SwitchHAT.LEFT,
            "Right": SwitchHAT.RIGHT,
        }
        if name in hat_map:
            self.manual_handler.test_hat(name, hat_map[name])
            return
        if name == "LUp":
            self.manual_handler.test_lstick("L↑", 128, 0)
        elif name == "LDown":
            self.manual_handler.test_lstick("L↓", 128, 255)
        elif name == "LLeft":
            self.manual_handler.test_lstick("L←", 0, 128)
        elif name == "LRight":
            self.manual_handler.test_lstick("L→", 255, 128)
        elif name == "RUp":
            self.manual_handler.test_rstick("R↑", 128, 0)
        elif name == "RDown":
            self.manual_handler.test_rstick("R↓", 128, 255)
        elif name == "RLeft":
            self.manual_handler.test_rstick("R←", 0, 128)
        elif name == "RRight":
            self.manual_handler.test_rstick("R→", 255, 128)

    # ---------- 自动测试 ----------
    def on_auto_test_clicked(self):
        if self.auto_test_ctrl.is_running():
            self.auto_test_ctrl.stop_test()
            self.auto_test_btn.setText("🧪 自动测试")
            self.progress_bar.setVisible(False)
        else:
            reply = QMessageBox.information(
                self,
                "自动测试",
                "即将开始自动按键测试。\n\n"
                "请先在 Switch 上打开：\n"
                "「设置」→「手柄与外设」→「检查输入设备」→「检查按键」\n\n"
                "点击「确定」开始测试。",
                QMessageBox.Ok | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                return
            self.auto_test_btn.setText("⏹️ 停止测试")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.auto_test_ctrl.start_test()

    def _on_auto_log(self, message: str):
        self.log_text.append(message)

    def _on_auto_test_finished(self):
        self.auto_test_btn.setText("🧪 自动测试")
        self.progress_bar.setVisible(False)

    # ---------- 按键映射 ----------
    def on_mapping_clicked(self):
        self.logger.info("进入按键映射页面")
        mapping_page = KeyMappingPage()
        mapping_page.return_requested.connect(self.on_mapping_return)
        mapping_page.open_config_management_requested.connect(
            lambda: self._on_open_config_management(mapping_page)
        )
        main_window = self._get_main_window()
        if main_window:
            main_window.stacked_widget.addWidget(mapping_page)
            main_window.stacked_widget.setCurrentWidget(mapping_page)
            self._mapping_page = mapping_page
            mapping_page.setFocus()

    def _on_open_config_management(self, mapping_page):
        self.logger.info("请求打开配置管理页面")
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, "open_config_management_page"):
            main_window.open_config_management_page(
                mapping_page.config_manager, mapping_page
            )

    def on_mapping_return(self):
        self.logger.info("从按键映射页面返回")
        self._load_key_mapping_from_config()  # 重新从 ConfigManager 加载
        main_window = self._get_main_window()
        if main_window and hasattr(self, "_mapping_page"):
            main_window.stacked_widget.removeWidget(self._mapping_page)
            self._mapping_page.deleteLater()
            del self._mapping_page
        main_window.stacked_widget.setCurrentWidget(self)
        self.setFocus()

    def _get_main_window(self):
        from PySide6.QtWidgets import QMainWindow

        parent = self.parent()
        while parent:
            if isinstance(parent, QMainWindow):
                return parent
            parent = parent.parent()
        return None

    # ---------- 计数 ----------
    def on_count_clicked(self):
        if self.manual_handler.is_counting():
            self.manual_handler.stop_counting()
            self.count_btn.setText("📊 开始计数")
        else:
            self.manual_handler.reset_counts()
            self.manual_handler.start_counting()
            self.count_btn.setText("⏹️ 停止计数")
            self._update_count_display({})

    def _on_counts_updated(self, counts: dict):
        self._update_count_display(counts)

    def _update_count_display(self, counts: dict):
        if not counts:
            msg = "[计数] 暂无按键计数"
        else:
            items = [f"{name}: {cnt}" for name, cnt in sorted(counts.items())]
            msg = "[计数] " + " | ".join(items)
        self.log_text.append(msg)

    # ---------- 绘图执行（委托 DrawingExecutor） ----------
    def start_drawing(
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
        """开始绘图任务"""
        if not self.controller.is_connected():
            QMessageBox.warning(self, "未连接设备", "请先连接单片机后再执行绘图。")
            return

        if self.drawing_executor.is_running():
            reply = QMessageBox.question(
                self,
                "绘图进行中",
                "已有绘图任务正在执行，是否停止当前任务并开始新绘图？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.stop_drawing()
            else:
                return

        # 清除旧断点（开始新任务）
        (
            self.drawing_executor.checkpoint_mgr.delete()
            if hasattr(self.drawing_executor, "checkpoint_mgr")
            else None
        )
        self.restore_drawing_btn.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.stop_drawing_btn.setEnabled(True)
        self.status_label.setText("正在生成脚本...")

        # 异步开始绘图，传递 press_data
        self.drawing_executor.start_drawing(
            color_index_matrix,
            color_palette,
            pixel_size,
            is_preset,
            brush_type,
            brush_size,
            press_data,
        )

    def stop_drawing(self):
        """停止当前绘图任务（会自动保存断点）"""
        self.drawing_executor.stop_drawing()
        self.stop_drawing_btn.setEnabled(False)
        self.status_label.setText("虚拟手柄就绪")
        self.progress_bar.setVisible(False)
        self._check_checkpoint_and_update_ui()

    def _on_drawing_log(self, message: str):
        self.log_text.append(message)

    def _on_drawing_progress(self, percent: int):
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"正在绘图... {percent}%")

    def _on_drawing_finished(self):
        self.progress_bar.setVisible(False)
        self.stop_drawing_btn.setEnabled(False)
        self.status_label.setText("绘图完成")
        self.log_text.append("[绘图] 脚本执行完毕")
        self._check_checkpoint_and_update_ui()

    def _on_drawing_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.stop_drawing_btn.setEnabled(False)
        self.status_label.setText("绘图错误")
        self.log_text.append(f"[绘图错误] {msg}")
        self._check_checkpoint_and_update_ui()

    # ---------- 断点恢复 ----------
    def on_restore_drawing_clicked(self):
        if not self.controller.is_connected():
            QMessageBox.warning(self, "未连接设备", "请先连接单片机后再恢复绘图。")
            return

        # 弹出三选一确认对话框
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("恢复绘图")
        msg_box.setText("检测到未完成的绘图断点。\n请选择恢复方式：")
        continue_btn = msg_box.addButton("从暂停恢复", QMessageBox.YesRole)
        restart_btn = msg_box.addButton("从保存恢复", QMessageBox.NoRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.setDefaultButton(continue_btn)
        msg_box.exec()

        clicked_btn = msg_box.clickedButton()
        if clicked_btn == continue_btn:
            # 从暂停恢复：直接从断点行继续执行当前脚本
            success = self.drawing_executor.resume_continue()
            if success:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(0)
                self.stop_drawing_btn.setEnabled(True)
                self.status_label.setText("从断点继续绘图...")
                self.restore_drawing_btn.setEnabled(False)
            else:
                QMessageBox.warning(self, "恢复失败", "无法继续执行，请检查断点文件。")
        elif clicked_btn == restart_btn:
            # 重新开始绘制：使用修改后的矩阵生成新脚本
            success = self.drawing_executor.resume_new_drawing()
            if success:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(0)
                self.stop_drawing_btn.setEnabled(True)
                self.status_label.setText("重新开始绘图...")
                self.restore_drawing_btn.setEnabled(False)
            else:
                QMessageBox.warning(self, "恢复失败", "无法重新开始，请检查断点文件。")
        elif clicked_btn == cancel_btn:
            # 取消：不做任何操作
            pass

    def _check_checkpoint_and_update_ui(self):
        """检测断点文件是否存在，更新恢复按钮的启用状态"""
        checker = CheckpointManager()
        if checker.has_checkpoint():
            self.restore_drawing_btn.setEnabled(True)
            self.restore_drawing_btn.setToolTip("存在未完成的绘图断点，点击恢复")
        else:
            self.restore_drawing_btn.setEnabled(False)
            self.restore_drawing_btn.setToolTip("没有可恢复的断点")

    # ---------- 返回与重启 ----------
    def on_return_clicked(self):
        if self.auto_test_ctrl.is_running():
            self.auto_test_ctrl.stop_test()
        if self.manual_handler.is_counting():
            self.manual_handler.stop_counting()
        self.stop_drawing()
        self.return_requested.emit()

    def closeEvent(self, event):
        if self.auto_test_ctrl.is_running():
            self.auto_test_ctrl.stop_test()
        if self.manual_handler.is_counting():
            self.manual_handler.stop_counting()
        self.stop_drawing()
        event.accept()

    def on_restart_clicked(self):
        self.logger.info("用户点击重新检测")
        self.restart_detection_requested.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_connection_status()
        self._check_checkpoint_and_update_ui()
