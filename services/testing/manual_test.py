"""
手动测试处理器 v2.2.0
封装所有手动测试函数，提供统一调用接口。
支持按键计数功能。
属于 services/testing 层，依赖 QtCore 定时器但不依赖 UI 组件。
"""

from PySide6.QtCore import QTimer, QObject, Signal
from core.hal.constants import SwitchHAT
from core.utils.logger import get_logger


class ManualTestHandler(QObject):
    # 计数更新信号，发送计数字典 {按键名: 次数}
    counts_updated = Signal(dict)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.logger = get_logger("ManualTestHandler")

        self._counting = False
        self._counts = {}  # 按键名 -> 次数

    # ---------- 计数控制 ----------
    def start_counting(self):
        self._counting = True
        self.logger.info("开始按键计数")

    def stop_counting(self):
        self._counting = False
        self.logger.info("停止按键计数")

    def reset_counts(self):
        self._counts.clear()
        self.counts_updated.emit(self._counts)
        self.logger.info("已清空计数")

    def is_counting(self) -> bool:
        return self._counting

    def get_counts(self) -> dict:
        return self._counts.copy()

    # ---------- 内部计数更新 ----------
    def _increment_count(self, name: str):
        if not self._counting:
            return
        self._counts[name] = self._counts.get(name, 0) + 1
        self.counts_updated.emit(self._counts)

    # ---------- 测试方法（增加计数调用）----------
    def test_button(self, name: str, mask: int):
        self.logger.info(f"手动测试 - {name} 按下: mask=0x{mask:04X}")
        self._increment_count(name)
        self.controller.send_hid_report(buttons=mask)
        QTimer.singleShot(100, lambda: self._release_button(name))

    def _release_button(self, name: str):
        self.logger.info(f"手动测试 - {name} 释放")
        self.controller.send_hid_report(buttons=0)

    def test_hat(self, name: str, hat: int):
        self.logger.info(f"手动测试 - 十字键 {name} 按下: hat={hat}")
        self._increment_count(name)
        self.controller.send_hid_report(buttons=0, hat=hat)
        QTimer.singleShot(100, lambda: self._release_hat(name))

    def _release_hat(self, name: str):
        self.logger.info(f"手动测试 - 十字键 {name} 释放")
        self.controller.send_hid_report(buttons=0, hat=SwitchHAT.CENTER)

    def test_lstick(self, name: str, lx: int, ly: int):
        self.logger.info(f"手动测试 - 左摇杆 {name} 按下: LX={lx}, LY={ly}")
        self._increment_count(name)
        self.controller.send_hid_report(buttons=0, lx=lx, ly=ly)
        QTimer.singleShot(100, lambda: self._release_stick(name, is_left=True))

    def test_rstick(self, name: str, rx: int, ry: int):
        self.logger.info(f"手动测试 - 右摇杆 {name} 按下: RX={rx}, RY={ry}")
        self._increment_count(name)
        self.controller.send_hid_report(buttons=0, rx=rx, ry=ry)
        QTimer.singleShot(100, lambda: self._release_stick(name, is_left=False))

    def _release_stick(self, name: str, is_left: bool):
        self.logger.info(f"手动测试 - {name} 释放")
        if is_left:
            self.controller.send_hid_report(buttons=0, lx=128, ly=128)
        else:
            self.controller.send_hid_report(buttons=0, rx=128, ry=128)
