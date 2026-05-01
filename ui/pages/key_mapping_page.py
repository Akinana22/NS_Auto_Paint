"""
按键映射配置页面 v2.2.0
支持多套配置管理，使用 ConfigManager 存储。
默认配置从 conf/default/key_mapping_default.json 读取。
两列布局 + 半透明白色背景，居中显示，带可调布局比例参数。
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QKeySequenceEdit,
    QMessageBox,
    QScrollArea,
    QInputDialog,
    QLineEdit,
    QFrame,
    QGridLayout,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QKeyEvent

from core.utils.config_manager import ConfigManager
from core.utils.logger import get_logger

logger = get_logger("KeyMappingPage")


class KeyMappingPage(QWidget):
    return_requested = Signal()
    open_config_management_requested = Signal()

    # ========== 布局比例参数（可在此调整） ==========
    TOP_SPACING_RATIO = 0.10  # 标题顶部间距占窗口高度的比例
    BOTTOM_SPACING_RATIO = 0.07  # 底部按钮底部间距占窗口高度的比例
    PANEL_WIDTH = 600  # 映射面板宽度（像素）
    PANEL_HORIZONTAL_PADDING = 40  # 面板内部左右边距
    PANEL_VERTICAL_PADDING = 30  # 面板内部上下边距
    # ==============================================

    def __init__(self):
        super().__init__()
        self.logger = get_logger("KeyMappingPage")
        self.config_manager = ConfigManager("key_mapping")
        default_config = self.config_manager.get_default_config_data()
        if default_config and "mapping" in default_config:
            self.default_mapping = default_config["mapping"]
        else:
            raise FileNotFoundError("默认按键映射配置文件缺失或格式错误")
        self.current_mapping = {}
        self.key_edits = {}
        self._load_current_config()
        self.setup_ui()
        self.apply_style()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _load_current_config(self):
        active = self.config_manager.get_active_config()
        data = active.get("data", {})
        if data and "mapping" in data:
            self.current_mapping = data["mapping"].copy()
        else:
            self.current_mapping = self.default_mapping.copy()
        for key in self.default_mapping:
            if key not in self.current_mapping:
                self.current_mapping[key] = self.default_mapping[key]

    def _refresh_ui_from_mapping(self):
        for name, edit in self.key_edits.items():
            edit.setKeySequence(QKeySequence(self.current_mapping.get(name, Qt.Key_A)))

    def _save_and_apply(self, new_name=None, old_name=None):
        active = self.config_manager.get_active_config()
        current_filename = active.get("filename")
        current_display_name = active.get("name")
        is_default = current_filename is None

        config_data = {
            "version": 1,
            "type": "key_mapping",
            "mapping": self.current_mapping,
        }

        if is_default:
            # 从默认创建新配置
            if new_name is None:
                return False, "default_config_needs_name"
            filename = self.config_manager.create_config(new_name, config_data)
            if filename is None:
                return False, "配置名可能已存在或无效"
            self.config_manager.set_active_config(filename)
            return True, f"已创建并激活配置「{new_name}」"
        else:
            if new_name is None or new_name == current_display_name:
                # 保存当前配置
                if self.config_manager.update_config(current_filename, config_data):
                    return True, f"已更新配置「{current_display_name}」"
                else:
                    return False, "更新配置失败"
            else:
                # 创建新配置，不删除旧配置
                filename = self.config_manager.create_config(new_name, config_data)
                if filename is None:
                    return False, f"配置名「{new_name}」已存在或无效"
                self.config_manager.set_active_config(filename)
                return True, f"已创建新配置「{new_name}」并激活（原配置保留）"

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(20)

        # 顶部弹性空间（根据比例参数调整）
        top_spacer = QWidget()
        top_spacer.setFixedHeight(
            int(self.height() * self.TOP_SPACING_RATIO) if self.height() > 0 else 60
        )
        main_layout.addWidget(top_spacer)

        # 标题
        title = QLabel("自定义按键映射")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #2c2c2c; background: transparent; border: none;"
        )
        main_layout.addWidget(title)

        # 当前配置名
        current_name = self.config_manager.get_current_config_display_name()
        self.config_label = QLabel(f"当前配置：{current_name}")
        self.config_label.setAlignment(Qt.AlignCenter)
        self.config_label.setStyleSheet(
            "color: #666; background: transparent; border: none;"
        )
        main_layout.addWidget(self.config_label)

        # 滚动区域（透明背景）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(self.PANEL_WIDTH)

        # 滚动区域内部容器
        scroll_content = QWidget()
        scroll_content.setAttribute(Qt.WA_TranslucentBackground, True)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignCenter)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # 半透明白色背景面板
        panel = QFrame()
        panel.setFixedWidth(self.PANEL_WIDTH - 20)  # 留出滚动条空间
        panel.setStyleSheet(
            """
            QFrame {
                background-color: rgba(255, 255, 255, 210);
                border: 1px solid #ccc;
                border-radius: 15px;
            }
            """
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setAlignment(Qt.AlignCenter)
        panel_layout.setContentsMargins(
            self.PANEL_HORIZONTAL_PADDING,
            self.PANEL_VERTICAL_PADDING,
            self.PANEL_HORIZONTAL_PADDING,
            self.PANEL_VERTICAL_PADDING,
        )
        panel_layout.setSpacing(15)

        # 两列网格布局
        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(10)
        grid.setAlignment(Qt.AlignCenter)

        # 按键顺序：左列9项，右列9项
        left_column = ["A", "B", "X", "Y", "L", "R", "ZL", "ZR", "Plus"]
        right_column = [
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

        for row, name in enumerate(left_column):
            label = QLabel(f"{name}：")
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #333; background: transparent; border: none;"
            )

            edit = QKeySequenceEdit()
            edit.setMaximumSequenceLength(1)
            edit.setFixedWidth(100)
            edit.setKeySequence(QKeySequence(self.current_mapping.get(name, Qt.Key_A)))
            edit.keySequenceChanged.connect(
                lambda seq, n=name: self._on_key_changed(n, seq)
            )
            self.key_edits[name] = edit

            grid.addWidget(label, row, 0, Qt.AlignRight)
            grid.addWidget(edit, row, 1, Qt.AlignLeft)

        for row, name in enumerate(right_column):
            label = QLabel(f"{name}：")
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #333; background: transparent; border: none;"
            )

            edit = QKeySequenceEdit()
            edit.setMaximumSequenceLength(1)
            edit.setFixedWidth(100)
            edit.setKeySequence(QKeySequence(self.current_mapping.get(name, Qt.Key_A)))
            edit.keySequenceChanged.connect(
                lambda seq, n=name: self._on_key_changed(n, seq)
            )
            self.key_edits[name] = edit

            grid.addWidget(label, row, 2, Qt.AlignRight)
            grid.addWidget(edit, row, 3, Qt.AlignLeft)

        panel_layout.addLayout(grid)
        scroll_layout.addWidget(panel)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, alignment=Qt.AlignCenter)

        # 中间弹性空间
        main_layout.addStretch()

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        self.save_btn = QPushButton("💾 保存并应用")
        self.save_btn.clicked.connect(self._on_save)

        self.restore_btn = QPushButton("🔄 恢复默认")
        self.restore_btn.clicked.connect(self._on_restore)

        self.manage_btn = QPushButton("📂 管理配置")
        self.manage_btn.clicked.connect(self._on_manage)

        self.return_btn = QPushButton("↩️ 返回")
        self.return_btn.clicked.connect(self.on_return)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addWidget(self.manage_btn)
        btn_layout.addWidget(self.return_btn)
        btn_layout.setAlignment(Qt.AlignCenter)

        main_layout.addLayout(btn_layout)

        # 底部弹性空间
        bottom_spacer = QWidget()
        bottom_spacer.setFixedHeight(
            int(self.height() * self.BOTTOM_SPACING_RATIO) if self.height() > 0 else 40
        )
        main_layout.addWidget(bottom_spacer)

        self.setLayout(main_layout)

    def apply_style(self):
        self.setStyleSheet(
            """
            QLabel { 
                color: #2c2c2c; 
                background: transparent; 
                border: none; 
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #aaa;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 255); }
            QPushButton:pressed { background-color: #4CAF50; color: white; }
            QKeySequenceEdit {
                background-color: #ffffff;
                border: 1px solid #aaa;
                border-radius: 3px;
                padding: 4px;
                color: #333;
                font-size: 12px;
            }
            QKeySequenceEdit:focus {
                border: 1px solid #4CAF50;
                background-color: #ffffff;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
        """
        )

    def _on_key_changed(self, name, seq):
        if seq.count() > 0:
            key = seq[0].key()
            if key:
                self.current_mapping[name] = key

    def _on_save(self):
        active = self.config_manager.get_active_config()
        current_name = active.get("name", "default")

        text, ok = QInputDialog.getText(
            self, "保存配置", "请输入配置名：", QLineEdit.Normal, current_name
        )
        if not ok:
            return
        new_name = text.strip()
        if not new_name:
            QMessageBox.warning(self, "提示", "配置名不能为空")
            return

        success, msg = self._save_and_apply(new_name)
        if success:
            QMessageBox.information(self, "成功", msg)
            self.config_label.setText(
                f"当前配置：{self.config_manager.get_current_config_display_name()}"
            )
            self._load_current_config()
            self._refresh_ui_from_mapping()
        else:
            if msg == "default_config_needs_name":
                QMessageBox.warning(
                    self, "提示", "当前是默认配置，请为新配置输入名称。"
                )
            else:
                QMessageBox.critical(self, "错误", f"保存失败：{msg}")

    def _on_restore(self):
        if self.config_manager.restore_default():
            self._load_current_config()
            self._refresh_ui_from_mapping()
            self.config_label.setText(
                f"当前配置：{self.config_manager.get_current_config_display_name()}"
            )
            QMessageBox.information(self, "成功", "已恢复默认按键映射。")
        else:
            QMessageBox.critical(self, "错误", "恢复默认失败。")

    def _on_manage(self):
        self.logger.info("请求打开配置管理页面")
        self.open_config_management_requested.emit()

    def on_return(self):
        self.return_requested.emit()

    def keyPressEvent(self, event: QKeyEvent):
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        event.accept()
