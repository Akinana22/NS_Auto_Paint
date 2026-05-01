import sys
import time

# 极简启动画面所需的最小导入
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QBrush, QPalette, QIcon, QTextCursor
from core.utils.resource import resource_path

try:
    from ctypes import windll

    myappid = "com.akinana.nsautopainter.1.0"
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass


class MinimalSplash(QWidget):
    """
    极简启动画面：完全不依赖项目其他模块，瞬间显示。
    包含项目介绍、免责声明、开源依赖声明、确认与退出按钮。
    """

    confirmed = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("assets/joycon.ico")))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(580, 650)
        self.set_background()
        self.setup_ui()
        self.center_on_screen()

    def set_background(self):
        pixmap = QPixmap(resource_path("assets/bg0.webp"))
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            brush = QBrush(scaled)
            palette = self.palette()
            palette.setBrush(QPalette.Window, brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 30, 40, 30)

        # 标题
        title = QLabel("NS Auto Painter")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #E60012; background: transparent;"
        )
        layout.addWidget(title)

        # 副标题
        subtitle = QLabel("单片机模拟手柄 · 自动像素绘图")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #333; background: transparent; margin-bottom: 10px;"
        )
        layout.addWidget(subtitle)

        # 介绍文字
        intro = QLabel(
            "本工具基于 CH32F103 单片机模拟 Switch Pro 手柄，\n"
            "实现《朋友收集 梦想生活》游戏内自动像素绘图。\n"
            "支持本地图片像素化、预设/自定义调色盘、\n"
            "以及第三方 JSON 像素画导入。"
        )
        intro.setAlignment(Qt.AlignCenter)
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px; color: #2c2c2c; background: transparent;")
        layout.addWidget(intro)

        # 分隔线
        sep1 = QLabel("——————————————————————————")
        sep1.setAlignment(Qt.AlignCenter)
        sep1.setStyleSheet("color: #aaa; background: transparent;")
        layout.addWidget(sep1)

        # 免责声明
        disclaimer = QLabel(
            "【免责声明】\n"
            "本软件为个人开发学习用途，仅供技术交流与研究使用，\n"
            "严禁用于任何商业目的。\n"
            "本软件非任天堂官方产品，与任天堂株式会社无任何关联。\n"
            "本软件使用的外链与本人无任何联系，仅为操作方便引入。\n"
            "使用者需自行承担因使用本软件而产生的一切后果，\n"
            "开发者不承担任何法律责任。"
        )
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(
            "font-size: 11px; color: #666; background: transparent;"
        )
        layout.addWidget(disclaimer)

        sep2 = QLabel("——————————————————————————")
        sep2.setAlignment(Qt.AlignCenter)
        sep2.setStyleSheet("color: #aaa; background: transparent;")
        layout.addWidget(sep2)

        # 开源声明小标题
        credits_title = QLabel("—— 开源声明 ——")
        credits_title.setAlignment(Qt.AlignCenter)
        credits_title.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #555; background: transparent;"
        )
        layout.addWidget(credits_title)

        # 开源依赖声明（更新至最终讨论版本）
        credits_text = (
            "【使用的开源依赖】\n"
            "PySide6 (LGPL)  ·  NumPy (BSD)  ·  Pillow (MIT-CMU)\n"
            "scikit-learn (BSD)  ·  scikit-image (BSD)  ·  Pyxelate (MIT)\n"
            "pyserial (BSD)  ·  WMI (MIT)  ·  pywin32 (PSF)\n"
            "\n"
            "【集成的开源工具】\n"
            "wchisp (MIT/GPL-2.0) —— WCH ISP 命令行烧录工具\n"
            "上述工具版权归各自原作者所有。\n"
            "\n"
            "【内置驱动说明】\n"
            "本软件内置的 CH32 设备驱动程序由 libusbK 生成，\n"
            "驱动签名证书及 INF 文件提取自官方 Zadig 工具。\n"
            "为便于命令行静默安装，证书已预先导出并内置。\n"
            "该证书仅用于驱动签名，不会影响系统整体安全。\n"
            "\n"
            "【内置固件说明】\n"
            "CH32F103 固件来自伊机控 (EasyCon) 开源项目 (GPL-3.0)\n"
            "版权归原作者所有，源代码获取地址：\n"
            "https://github.com/EasyConNS/EasyMCU_CH32\n"
            "\n"
            "感谢所有开源贡献者！"
        )

        self.credits_edit = QTextEdit()
        self.credits_edit.setPlainText(credits_text)
        self.credits_edit.setReadOnly(True)
        self.credits_edit.setFrameShape(QTextEdit.NoFrame)
        self.credits_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.credits_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.credits_edit.setFocusPolicy(Qt.NoFocus)
        self.credits_edit.setStyleSheet(
            """
            QTextEdit {
                background: transparent;
                color: #444;
                font-size: 10px;
                border: none;
                selection-background-color: rgba(200, 200, 200, 100);
            }
        """
        )
        # 设置文本居中对齐
        cursor = self.credits_edit.textCursor()
        cursor.select(QTextCursor.Document)
        block_format = cursor.blockFormat()
        block_format.setAlignment(Qt.AlignCenter)
        cursor.mergeBlockFormat(block_format)
        self.credits_edit.setTextCursor(cursor)
        self.credits_edit.moveCursor(QTextCursor.Start)
        self.credits_edit.setFixedHeight(160)
        layout.addWidget(self.credits_edit)

        # 加载状态标签（初始隐藏）
        self.loading_label = QLabel()
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(
            "font-size: 12px; color: #E60012; background: transparent; font-weight: bold;"
        )
        self.loading_label.setVisible(False)
        layout.addWidget(self.loading_label)

        # 按钮区域
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)

        self.confirm_btn = QPushButton("我已知晓，进入主界面")
        self.confirm_btn.setFixedSize(200, 40)
        self.confirm_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #E60012;
                color: white;
                font-weight: bold;
                border: 1px solid #c00010;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #c00010; }
            QPushButton:disabled { background-color: #aaa; border: 1px solid #888; }
        """
        )
        self.confirm_btn.clicked.connect(self._on_confirm)

        self.quit_btn = QPushButton("退出")
        self.quit_btn.setFixedSize(200, 40)
        self.quit_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #aaa;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 255); }
        """
        )
        self.quit_btn.clicked.connect(self._on_quit)

        btn_layout.addWidget(self.confirm_btn, alignment=Qt.AlignCenter)
        btn_layout.addWidget(self.quit_btn, alignment=Qt.AlignCenter)
        layout.addLayout(btn_layout)

    def center_on_screen(self):
        screen_geometry = self.screen().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def _on_confirm(self):
        self.confirmed.emit()

    def _on_quit(self):
        self.quit_requested.emit()

    def show_loading(self, show: bool):
        self.loading_label.setText("正在初始化，请稍候...")
        self.loading_label.setVisible(show)
        self.confirm_btn.setEnabled(not show)


# ========== 程序入口 ==========
if __name__ == "__main__":
    import sys
    import time

    app = QApplication(sys.argv)
    splash = MinimalSplash()
    splash.show()
    app.processEvents()
    actual_start = time.time()

    app.setStyleSheet(
        """
        QMessageBox { background-color: #f5f5f5; }
        QMessageBox QPushButton {
            background-color: #ffffff; border: 1px solid #cccccc;
            border-radius: 4px; padding: 6px 12px; min-width: 80px;
            font-size: 13px; color: #333333;
        }
        QMessageBox QPushButton:hover {
            background-color: #e6e6e6; border: 1px solid #adadad;
        }
        QMessageBox QPushButton:pressed {
            background-color: #c8e6c9; border: 1px solid #8c8c8c;
        }
        QMessageBox QPushButton:default {
            background-color: #e0e0e0; border: 1px solid #b0b0b0;
        }
    """
    )

    window_ref = [None]

    def create_and_show_main():
        splash.show_loading(True)
        app.processEvents()
        t1 = time.time()
        from ui.main_window import MainWindow  # 从 UI 模块导入

        window_ref[0] = MainWindow()
        print(f"[主线程] MainWindow 实例化耗时: {time.time() - t1:.2f}s")
        splash.close()
        window_ref[0].show()
        print(f"[前台] 启动总耗时: {time.time() - actual_start:.2f}s")

    def on_confirm():
        QTimer.singleShot(50, create_and_show_main)

    splash.confirmed.connect(on_confirm)
    splash.quit_requested.connect(app.quit)
    sys.exit(app.exec())
