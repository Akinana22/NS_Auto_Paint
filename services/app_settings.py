"""
应用设置管理模块 v2.2.0
使用 QSettings 持久化存储用户偏好（如按键映射）
"""

from PySide6.QtCore import QSettings, Qt


class AppSettings:
    """应用设置管理类，封装 QSettings 操作"""

    def __init__(self):
        self.settings = QSettings("NSAutoPainter", "VirtualGamepad")

    def load_key_mapping(self) -> dict:
        """
        从 QSettings 加载按键映射。
        :return: 字典 {按键名称: Qt.Key 值}
        """
        default_mapping = {
            "A": Qt.Key_Z,
            "B": Qt.Key_X,
            "X": Qt.Key_C,
            "Y": Qt.Key_V,
            "L": Qt.Key_Q,
            "R": Qt.Key_E,
            "ZL": Qt.Key_1,
            "ZR": Qt.Key_4,
            "Plus": Qt.Key_Return,
            "Minus": Qt.Key_Backspace,
            "Home": Qt.Key_H,
            "Capture": Qt.Key_J,
            "L3": Qt.Key_F,
            "R3": Qt.Key_G,
            "Up": Qt.Key_W,
            "Down": Qt.Key_S,
            "Left": Qt.Key_A,
            "Right": Qt.Key_D,
        }

        mapping = {}
        for name, default_key in default_mapping.items():
            saved = self.settings.value(f"keymap/{name}", default_key.value)
            if isinstance(saved, str):
                saved = int(saved)
            mapping[name] = Qt.Key(saved)
        return mapping

    def save_key_mapping(self, mapping: dict):
        """
        保存按键映射到 QSettings。
        :param mapping: 字典 {按键名称: Qt.Key 值}
        """
        for name, key in mapping.items():
            self.settings.setValue(f"keymap/{name}", key.value)

    def restore_default_mapping(self) -> dict:
        """
        恢复默认按键映射并保存。
        :return: 默认映射字典
        """
        default_mapping = {
            "A": Qt.Key_Z,
            "B": Qt.Key_X,
            "X": Qt.Key_C,
            "Y": Qt.Key_V,
            "L": Qt.Key_Q,
            "R": Qt.Key_E,
            "ZL": Qt.Key_1,
            "ZR": Qt.Key_4,
            "Plus": Qt.Key_Return,
            "Minus": Qt.Key_Backspace,
            "Home": Qt.Key_H,
            "Capture": Qt.Key_J,
            "L3": Qt.Key_F,
            "R3": Qt.Key_G,
            "Up": Qt.Key_W,
            "Down": Qt.Key_S,
            "Left": Qt.Key_A,
            "Right": Qt.Key_D,
        }
        self.save_key_mapping(default_mapping)
        return default_mapping
