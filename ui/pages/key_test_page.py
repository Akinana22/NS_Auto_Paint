"""
按键测试过程页面 v2.2.0
展示测试进度、当前按键，并启动后台测试线程，同时支持手动单步测试。
属于 UI 层页面，依赖 services.testing.test_worker。
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QGridLayout,
    QGroupBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QBrush

from core.hal.controller import EasyConController
from core.hal.constants import SwitchButtons, SwitchHAT
from services.testing.test_worker import KeyTestWorker
from core.utils.logger import get_logger
from core.utils.resource import resource_path


class KeyTestPage(QWidget):
    test_finished = Signal()

    def __init__(self, controller: EasyConController):
        super().__init__()
        self.logger = get_logger("KeyTestPage")
        self.controller = controller
        self.test_worker = None

        self.set_background()
        self.setup_ui()
        self.apply_style()

        # 自动开始测试
        self.start_test()

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
        main_layout.setSpacing(15)

        self.title_label = QLabel("按键测试进行中")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.title_label)

        self.status_label = QLabel("准备开始...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #333;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(400)
        main_layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("background-color: rgba(255, 255, 255, 200);")
        main_layout.addWidget(self.log_text)

        manual_group = QGroupBox("手动单步测试 (点击按钮发送一次按下+释放)")
        manual_layout = QGridLayout()
        manual_layout.setSpacing(8)

        buttons_layout = QGridLayout()
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
            btn.setFixedSize(70, 40)
            btn.clicked.connect(
                lambda checked, n=name, m=mask: self.manual_test_button(n, m)
            )
            row = idx // 4
            col = idx % 4
            buttons_layout.addWidget(btn, row, col)

        hat_layout = QGridLayout()
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
            btn.setFixedSize(70, 40)
            btn.clicked.connect(
                lambda checked, n=name, h=hat: self.manual_test_hat(n, h)
            )
            row = idx // 4
            col = idx % 4
            hat_layout.addWidget(btn, row, col)

        ls_layout = QGridLayout()
        ls_list = [("L↑", 128, 0), ("L↓", 128, 255), ("L←", 0, 128), ("L→", 255, 128)]
        for idx, (name, lx, ly) in enumerate(ls_list):
            btn = QPushButton(name)
            btn.setFixedSize(70, 40)
            btn.clicked.connect(
                lambda checked, n=name, x=lx, y=ly: self.manual_test_lstick(n, x, y)
            )
            row = idx // 4
            col = idx % 4
            ls_layout.addWidget(btn, row, col)

        rs_layout = QGridLayout()
        rs_list = [("R↑", 128, 0), ("R↓", 128, 255), ("R←", 0, 128), ("R→", 255, 128)]
        for idx, (name, rx, ry) in enumerate(rs_list):
            btn = QPushButton(name)
            btn.setFixedSize(70, 40)
            btn.clicked.connect(
                lambda checked, n=name, x=rx, y=ry: self.manual_test_rstick(n, x, y)
            )
            row = idx // 4
            col = idx % 4
            rs_layout.addWidget(btn, row, col)

        manual_layout.addWidget(QLabel("普通按键:"), 0, 0)
        manual_layout.addLayout(buttons_layout, 0, 1)
        manual_layout.addWidget(QLabel("十字键:"), 1, 0)
        manual_layout.addLayout(hat_layout, 1, 1)
        manual_layout.addWidget(QLabel("左摇杆:"), 2, 0)
        manual_layout.addLayout(ls_layout, 2, 1)
        manual_layout.addWidget(QLabel("右摇杆:"), 3, 0)
        manual_layout.addLayout(rs_layout, 3, 1)

        manual_group.setLayout(manual_layout)
        main_layout.addWidget(manual_group)

        # 停止/返回按钮
        self.cancel_btn = QPushButton("停止测试")
        self.cancel_btn.setFixedSize(180, 35)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        main_layout.addWidget(self.cancel_btn, alignment=Qt.AlignCenter)

        self.setLayout(main_layout)

    def on_cancel_clicked(self):
        """处理停止测试/返回按钮点击"""
        if self.cancel_btn.text() == "停止测试":
            if self.test_worker is not None:
                self.test_worker.cancel()
            self.logger.info("用户停止测试")
        else:
            self.test_finished.emit()

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

    def start_test(self):
        """启动测试线程"""
        self.test_worker = KeyTestWorker(self.controller)
        self.test_worker.log_message.connect(self.on_log_message)
        self.test_worker.test_finished.connect(self.on_test_finished)
        self.test_worker.progress_update.connect(self.progress_bar.setValue)
        self.test_worker.start()
        self.cancel_btn.setText("停止测试")
        self.cancel_btn.setEnabled(True)

    def on_log_message(self, message):
        self.status_label.setText(message)
        self.log_text.append(message)

    def on_test_finished(self):
        """测试完成（包括正常完成和用户取消）"""
        self.cancel_btn.setText("返回")
        self.cancel_btn.setEnabled(True)
        if self.test_worker is not None:
            try:
                self.test_worker.log_message.disconnect(self.on_log_message)
            except Exception:
                pass
            try:
                self.test_worker.test_finished.disconnect(self.on_test_finished)
            except Exception:
                pass
            try:
                self.test_worker.progress_update.disconnect(self.progress_bar.setValue)
            except Exception:
                pass
            self.test_worker = None

    def on_cancel(self):
        if self.test_worker is not None:
            self.test_worker.cancel()
        self.logger.info("用户取消测试")

    # ----- 手动测试函数 -----
    def manual_test_button(self, name, mask):
        self.logger.info(f"手动测试 - {name} 按下: mask=0x{mask:04X}")
        self.controller.send_hid_report(buttons=mask)
        QTimer.singleShot(100, lambda: self._manual_release_button(name))

    def _manual_release_button(self, name):
        self.logger.info(f"手动测试 - {name} 释放")
        self.controller.send_hid_report(buttons=0)

    def manual_test_hat(self, name, hat):
        self.logger.info(f"手动测试 - 十字键 {name} 按下: hat={hat}")
        self.controller.send_hid_report(buttons=0, hat=hat)
        QTimer.singleShot(100, lambda: self._manual_release_hat(name))

    def _manual_release_hat(self, name):
        self.logger.info(f"手动测试 - 十字键 {name} 释放")
        self.controller.send_hid_report(buttons=0, hat=SwitchHAT.CENTER)

    def manual_test_lstick(self, name, lx, ly):
        self.logger.info(f"手动测试 - 左摇杆 {name} 按下: LX={lx}, LY={ly}")
        self.controller.send_hid_report(buttons=0, lx=lx, ly=ly)
        QTimer.singleShot(100, lambda: self._manual_release_stick(name, is_left=True))

    def manual_test_rstick(self, name, rx, ry):
        self.logger.info(f"手动测试 - 右摇杆 {name} 按下: RX={rx}, RY={ry}")
        self.controller.send_hid_report(buttons=0, rx=rx, ry=ry)
        QTimer.singleShot(100, lambda: self._manual_release_stick(name, is_left=False))

    def _manual_release_stick(self, name, is_left):
        self.logger.info(f"手动测试 - {name} 释放")
        if is_left:
            self.controller.send_hid_report(buttons=0, lx=128, ly=128)
        else:
            self.controller.send_hid_report(buttons=0, rx=128, ry=128)

    def closeEvent(self, event):
        if self.test_worker is not None:
            self.test_worker.cancel()
        event.accept()
