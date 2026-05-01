"""
通用配置管理 UI 组件 v2.2.0
用于管理某个功能类型的用户配置（列表、重命名、激活、删除）
提供应用/返回机制，应用时校验配置名冲突并保存修改
新增：显示当前生效的配置名称，禁止使用 "default" 作为配置名
背景改为半透明白色
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PySide6.QtCore import Signal, Qt
from typing import Dict, List, Optional
from core.utils.config_manager import ConfigManager
from core.utils.logger import get_logger


class ConfigManagementPage(QWidget):
    """通用配置管理页面"""

    applied = Signal()  # 应用成功时发射
    return_requested = Signal()  # 返回上一页时发射

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.cm = config_manager
        self.logger = get_logger("ConfigManagementPage")
        self.setWindowTitle(f"管理{self._get_type_display()}配置")

        self.original_configs: List[Dict[str, str]] = []
        self.current_configs: List[Dict[str, str]] = []
        self.active_filename: Optional[str] = None
        self.deleted_filenames = set()
        self.renamed_map = {}

        self._load_data()
        self.setup_ui()
        self.apply_style()
        self._populate_list()

        # 背景透明化，让父级背景透出
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _get_type_display(self) -> str:
        type_map = {"key_mapping": "按键映射"}
        return type_map.get(self.cm.config_type, self.cm.config_type)

    def _load_data(self):
        self.original_configs = self.cm.list_configs()
        self.current_configs = [c.copy() for c in self.original_configs]
        active = self.cm.get_active_config()
        self.active_filename = active.get("filename")
        self.deleted_filenames.clear()
        self.renamed_map.clear()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # 显示当前生效的配置
        current_name = self.cm.get_current_config_display_name()
        self.current_config_label = QLabel(f"当前生效配置：{current_name}")
        self.current_config_label.setWordWrap(True)
        self.current_config_label.setAlignment(Qt.AlignCenter)
        self.current_config_label.setStyleSheet(
            "color: #2c2c2c; font-weight: bold; margin-bottom: 10px; background: transparent;"
        )
        layout.addWidget(self.current_config_label)

        self.info_label = QLabel(
            "可修改配置名、激活或删除配置。所有修改需点击「应用」后生效。"
        )
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(
            "color: #666; font-size: 12px; background: transparent;"
        )
        layout.addWidget(self.info_label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: rgba(255, 255, 255, 200);
                border: 1px solid #aaa;
                border-radius: 8px;
            }
            """
        )
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        self.return_btn = QPushButton("返回")
        self.apply_btn = QPushButton("应用")
        self.return_btn.clicked.connect(self.return_requested.emit)
        self.apply_btn.clicked.connect(self.on_apply)
        btn_layout.addWidget(self.return_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

    def apply_style(self):
        self.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #aaa;
                border-radius: 5px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 255);
            }
            QPushButton:pressed {
                background-color: #4CAF50;
                color: white;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #aaa;
                border-radius: 3px;
                padding: 4px;
            }
            QLabel {
                background: transparent;
            }
        """
        )

    def _populate_list(self):
        self.list_widget.clear()
        for idx, cfg in enumerate(self.current_configs):
            name = cfg["name"]
            filename = cfg["filename"]
            item = QListWidgetItem()
            self.list_widget.addItem(item)

            widget = QWidget()
            widget.setStyleSheet("background: transparent;")
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 2, 5, 2)

            name_edit = QLineEdit(name)
            name_edit.textChanged.connect(
                lambda text, i=idx, fn=filename: self._on_name_changed(i, fn, text)
            )
            name_edit.setMinimumWidth(150)
            layout.addWidget(name_edit)

            activate_btn = QPushButton("激活")
            if self.active_filename == filename:
                activate_btn.setEnabled(False)
                activate_btn.setText("已激活")
                activate_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            else:
                activate_btn.clicked.connect(
                    lambda checked, fn=filename: self._set_active(fn)
                )
            layout.addWidget(activate_btn)

            del_btn = QPushButton("删除")
            del_btn.clicked.connect(
                lambda checked, i=idx, fn=filename: self._mark_for_deletion(i, fn)
            )
            layout.addWidget(del_btn)

            widget.setLayout(layout)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)
            cfg["_name_edit"] = name_edit
            cfg["_activate_btn"] = activate_btn

    def _on_name_changed(self, idx: int, filename: str, new_text: str):
        if idx < 0 or idx >= len(self.current_configs):
            return
        old_name = self.current_configs[idx]["name"]
        if new_text == old_name:
            if old_name in self.renamed_map:
                del self.renamed_map[old_name]
        else:
            self.renamed_map[old_name] = new_text
        self.current_configs[idx]["name"] = new_text

    def _set_active(self, filename: str):
        self.active_filename = filename
        self._populate_list()
        current_name = self.cm.get_current_config_display_name()
        self.current_config_label.setText(f"当前生效配置：{current_name}")

    def _mark_for_deletion(self, idx: int, filename: str):
        if idx < 0 or idx >= len(self.current_configs):
            return
        self.deleted_filenames.add(filename)
        self.current_configs.pop(idx)
        if self.active_filename == filename:
            self.active_filename = None
        self._populate_list()

    def _validate_changes(self) -> bool:
        name_to_filename = {}
        for cfg in self.current_configs:
            name = cfg["name"]
            filename = cfg["filename"]
            if name.lower() == "default":
                QMessageBox.warning(
                    self, "无效的配置名", "配置名不能为 'default'，请重新命名。"
                )
                return False
            if name in name_to_filename:
                return False
            name_to_filename[name] = filename
        return True

    def _highlight_conflicts(self):
        name_counts = {}
        for cfg in self.current_configs:
            name = cfg["name"]
            name_counts[name] = name_counts.get(name, 0) + 1
        for i in range(self.list_widget.count()):
            widget = self.list_widget.itemWidget(self.list_widget.item(i))
            if widget:
                name_edit = widget.findChild(QLineEdit)
                if name_edit:
                    name = name_edit.text()
                    if name.lower() == "default" or name_counts.get(name, 0) > 1:
                        name_edit.setStyleSheet("border: 1px solid red;")
                    else:
                        name_edit.setStyleSheet("")
        if any(cnt > 1 for cnt in name_counts.values()):
            self.info_label.setText("配置名存在重复，请修改后重新应用。")
            self.info_label.setStyleSheet("color: red; background: transparent;")
        elif any(name.lower() == "default" for name in name_counts):
            self.info_label.setText("配置名不能为 'default'，请修改后重新应用。")
            self.info_label.setStyleSheet("color: red; background: transparent;")
        else:
            self.info_label.setText(
                "可修改配置名、激活或删除配置。所有修改需点击「应用」后生效。"
            )
            self.info_label.setStyleSheet("color: #666; background: transparent;")

    def on_apply(self):
        if not self._validate_changes():
            self._highlight_conflicts()
            QMessageBox.warning(
                self, "配置名无效", "配置名重复或使用了 'default'，请修改后再应用。"
            )
            return

        # 1. 删除标记为删除的配置（ConfigManager.delete_config 会同步更新 manifest）
        for filename in self.deleted_filenames:
            name_to_del = None
            for cfg in self.original_configs:
                if cfg["filename"] == filename:
                    name_to_del = cfg["name"]
                    break
            if name_to_del:
                if not self.cm.delete_config(name_to_del):
                    self.logger.error(f"删除配置失败: {name_to_del}")
                    QMessageBox.critical(self, "错误", f"删除配置 {name_to_del} 失败")
                    return

        # 2. 根据当前界面中的名称（已包含重命名）重建 manifest 中的 mappings
        manifest = self.cm._read_manifest()
        new_mappings = {}
        for cfg in self.current_configs:
            new_mappings[cfg["name"]] = cfg["filename"]
        manifest["mappings"] = new_mappings

        # 3. 激活设置
        if self.active_filename is not None:
            manifest["active"] = self.active_filename
        else:
            manifest["active"] = None
        self.cm._write_manifest(manifest)

        QMessageBox.information(self, "成功", "配置已应用")
        self.applied.emit()
        self.return_requested.emit()
