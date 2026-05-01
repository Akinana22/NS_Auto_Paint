"""
按键测试工作线程 v2.2.0
基于 QTimer 状态机，可安全取消。
属于 services/testing 层，依赖 QtCore。
"""

from PySide6.QtCore import QObject, QTimer, Signal

from core.hal.constants import SwitchButtons, SwitchHAT
from core.utils.logger import get_logger


class KeyTestWorker(QObject):
    log_message = Signal(str)
    test_finished = Signal()
    progress_update = Signal(int)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.logger = get_logger("KeyTestWorker")
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._execute_next)
        self._sequence = []
        self._current_index = 0
        self._cancelled = False

    def _build_sequence(self):
        """构建测试步骤序列：普通按键 -> 十字键 -> HOME -> 左摇杆顺序 -> 右摇杆顺序"""
        seq = []

        # 普通按键测试顺序：A B X Y L R ZL ZR + - 截图
        button_tests = [
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
            ("截图", SwitchButtons.CAPTURE),
        ]
        for name, mask in button_tests:
            seq.append(
                (
                    f"按下 {name}",
                    lambda m=mask: self.controller.send_hid_report(buttons=m),
                )
            )
            seq.append(("等待50ms", lambda: True))
            seq.append(
                (f"释放 {name}", lambda: self.controller.send_hid_report(buttons=0))
            )
            seq.append(("等待1秒", lambda: True))

        # 十字键测试：上 下 左 右
        hat_tests = [
            ("上", SwitchHAT.TOP),
            ("下", SwitchHAT.BOTTOM),
            ("左", SwitchHAT.LEFT),
            ("右", SwitchHAT.RIGHT),
        ]
        for name, hat in hat_tests:
            seq.append(
                (
                    f"按下十字键 {name}",
                    lambda h=hat: self.controller.send_hid_report(buttons=0, hat=h),
                )
            )
            seq.append(("等待50ms", lambda: True))
            seq.append(
                (
                    f"释放十字键 {name}",
                    lambda: self.controller.send_hid_report(
                        buttons=0, hat=SwitchHAT.CENTER
                    ),
                )
            )
            seq.append(("等待1秒", lambda: True))

        # HOME 放在摇杆之前，避免摇杆误操作导致退出
        seq.append(
            (
                "按下 HOME",
                lambda: self.controller.send_hid_report(buttons=SwitchButtons.HOME),
            )
        )
        seq.append(("等待50ms", lambda: True))
        seq.append(("释放 HOME", lambda: self.controller.send_hid_report(buttons=0)))
        seq.append(("等待1秒", lambda: True))

        # 左摇杆顺序测试：右 → 下 → 左 → 上
        left_stick_order = [
            ("LStick →", 255, 128),
            ("LStick ↓", 128, 255),
            ("LStick ←", 0, 128),
            ("LStick ↑", 128, 0),
        ]
        for name, lx, ly in left_stick_order:
            seq.append(
                (
                    f"按下 {name}",
                    lambda lx=lx, ly=ly: self.controller.send_hid_report(
                        buttons=0, lx=lx, ly=ly
                    ),
                )
            )
            seq.append(("等待50ms", lambda: True))
            seq.append(
                (
                    f"释放 {name}",
                    lambda: self.controller.send_hid_report(buttons=0, lx=128, ly=128),
                )
            )
            seq.append(("等待1秒", lambda: True))

        # 右摇杆顺序测试：左 → 下 → 右 → 上
        right_stick_order = [
            ("RStick ←", 0, 128),
            ("RStick ↓", 128, 255),
            ("RStick →", 255, 128),
            ("RStick ↑", 128, 0),
        ]
        for name, rx, ry in right_stick_order:
            seq.append(
                (
                    f"按下 {name}",
                    lambda rx=rx, ry=ry: self.controller.send_hid_report(
                        buttons=0, rx=rx, ry=ry
                    ),
                )
            )
            seq.append(("等待50ms", lambda: True))
            seq.append(
                (
                    f"释放 {name}",
                    lambda: self.controller.send_hid_report(buttons=0, rx=128, ry=128),
                )
            )
            seq.append(("等待1秒", lambda: True))

        return seq

    def start(self):
        self._sequence = self._build_sequence()
        self._current_index = 0
        self._cancelled = False
        self.log_message.emit("=== 开始按键测试 ===")
        self.logger.info("开始按键测试")
        self._execute_next()

    def cancel(self):
        self._cancelled = True
        self._timer.stop()
        self.log_message.emit("=== 测试已取消 ===")
        self.logger.info("按键测试被用户取消")
        self.test_finished.emit()

    def _execute_next(self):
        if self._cancelled:
            return
        if self._current_index >= len(self._sequence):
            self.log_message.emit("=== 按键测试完成 ===")
            self.logger.info("按键测试完成")
            self.test_finished.emit()
            return

        total = len(self._sequence)
        progress = int((self._current_index / total) * 100)
        self.progress_update.emit(progress)

        desc, func = self._sequence[self._current_index]
        self._current_index += 1

        self.log_message.emit(f"[测试] {desc}")
        self.logger.info(f"执行步骤: {desc}")

        try:
            func()
        except Exception as e:
            self.logger.error(f"步骤异常: {desc}, 错误: {e}")

        # 根据描述决定延时
        if "等待1秒" in desc:
            self._timer.start(1000)
        elif "等待50ms" in desc:
            self._timer.start(50)
        else:
            self._timer.start(10)  # 其他步骤极短延时
