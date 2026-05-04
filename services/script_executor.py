"""
脚本执行器 v2.3.0
解析符合官方 EasyCon 脚本语法的文本，逐条发送 HID 报告到单片机。
通过 log_signal 输出每条指令的人类可读描述，并在停止时动态计算安全等待时间。
指令闭环保证：按键的 按下 → 保持 → 释放 过程不会被停止信号打断。
支持通过 execute() 传入 timing 快照，未传则回退 TimingConfig 类属性。
"""

import time
import threading
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal

from core.hal.controller import EasyConController
from core.hal.constants import SwitchButtons, SwitchHAT
from core.utils.logger import get_logger
from core.scheduling.timing_config import TimingConfig, TimingSnapshot


class ScriptExecutor(QObject):
    """脚本执行器，在后台线程中逐行执行脚本"""

    log_signal = Signal(str)  # 日志消息
    progress_signal = Signal(int)  # 当前行号（0‑based）
    finished_signal = Signal()  # 脚本结束
    error_signal = Signal(str)  # 脚本错误

    BUTTON_MAP = {
        "A": SwitchButtons.A,
        "B": SwitchButtons.B,
        "X": SwitchButtons.X,
        "Y": SwitchButtons.Y,
        "L": SwitchButtons.L,
        "R": SwitchButtons.R,
        "ZL": SwitchButtons.ZL,
        "ZR": SwitchButtons.ZR,
        "MINUS": SwitchButtons.MINUS,
        "PLUS": SwitchButtons.PLUS,
        "LCLICK": SwitchButtons.LCLICK,
        "RCLICK": SwitchButtons.RCLICK,
        "HOME": SwitchButtons.HOME,
        "CAPTURE": SwitchButtons.CAPTURE,
    }

    HAT_MAP = {
        "UP": SwitchHAT.TOP,
        "DOWN": SwitchHAT.BOTTOM,
        "LEFT": SwitchHAT.LEFT,
        "RIGHT": SwitchHAT.RIGHT,
    }

    def __init__(self, controller: EasyConController):
        super().__init__()
        self.controller = controller
        self.logger = get_logger("ScriptExecutor")
        self._stop_flag = False
        self._thread: Optional[threading.Thread] = None
        self._current_line = 0
        self._timing: Optional[TimingSnapshot] = None

    def execute(self, script: str, start_line: int = 0, timing: Optional[TimingSnapshot] = None):
        if self._thread and self._thread.is_alive():
            self.logger.warning("已有脚本正在执行")
            return
        self._timing = timing
        self._stop_flag = False
        self._thread = threading.Thread(
            target=self._run, args=(script, start_line), daemon=True
        )
        self._thread.start()

    def stop(self):
        """停止当前脚本执行，动态计算安全等待以保证当前按键完整释放"""
        # 因为按键闭环已受保护，但仍然保留安全等待作为双保险
        min_interval = min(TimingConfig.key_interval_ms, TimingConfig.draw_ms)
        wait_ms = (TimingConfig.press_hold_ms + min_interval) // 2
        time.sleep(wait_ms / 1000.0)
        self._stop_flag = True
        if self._thread:
            self._thread.join(timeout=1.0)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- 后台线程 ----------
    def _run(self, script: str, start_line: int):
        self.logger.info(f"开始执行脚本，起始行: {start_line}")
        lines = script.splitlines()
        self._current_line = 0

        for line_num in range(start_line, len(lines)):
            if self._stop_flag:
                self.logger.info("脚本被用户停止")
                self.error_signal.emit("脚本被用户停止")
                return

            self._current_line = line_num
            self.progress_signal.emit(line_num)

            raw_line = lines[line_num].strip()
            if not raw_line or raw_line.startswith("#"):
                if raw_line.startswith("#"):
                    self.log_signal.emit(raw_line)
                continue

            log_msg = self._describe_line(raw_line)
            if log_msg:
                self.log_signal.emit(log_msg)

            try:
                self._execute_line(raw_line)
            except Exception as e:
                err_msg = f"第 {line_num+1} 行执行失败: {raw_line} - {e}"
                self.logger.error(err_msg)
                self.error_signal.emit(err_msg)
                return

        self.logger.info("脚本执行完毕")
        self.finished_signal.emit()

    # ---------- 人类可读描述 ----------
    def _describe_line(self, line: str) -> str:
        """将一行脚本命令转换为简短说明"""
        cfg = self._timing or TimingConfig
        if "#" in line:
            line = line[: line.find("#")].strip()
        if not line:
            return ""

        upper = line.upper()
        parts = upper.split()
        if parts[0] == "WAIT" or parts[0].isdigit():
            ms = (
                parts[0]
                if parts[0].isdigit()
                else (parts[1] if len(parts) > 1 else "?")
            )
            return f"等待 {ms}ms"

        if parts[0] in self.BUTTON_MAP or parts[0] in self.HAT_MAP:
            btn = parts[0]
            if len(parts) >= 2:
                arg = parts[1]
                if arg == "DOWN":
                    return f"按住 {btn}"
                elif arg == "UP":
                    return f"释放 {btn}"
                else:
                    return (
                        f"操作 {btn} (按压{cfg.press_hold_ms}ms, 间隔{arg}ms)"
                    )
            return f"按下 {btn} (默认)"

        if parts[0] in ("LS", "RS"):
            stick = "左摇杆" if parts[0] == "LS" else "右摇杆"
            if len(parts) < 2:
                return "[警告] 摇杆指令缺少参数"
            param = parts[1]
            if param == "RESET":
                return f"{stick} 复位"
            direction = param
            dur = ""
            if "," in param:
                dir_part, dur_part = param.split(",", 1)
                direction = dir_part
                dur = dur_part
            elif len(parts) >= 3:
                dur = parts[2]
            if dur:
                return f"{stick} {direction} {dur}ms"
            return f"{stick} {direction} (持续)"

        return f"执行: {line}"

    # ---------- 指令解析与执行 ----------
    def _execute_line(self, line: str):
        """解析并执行一行指令"""
        cfg = self._timing or TimingConfig
        if "#" in line:
            line = line[: line.find("#")].strip()
        if not line:
            return

        upper = line.upper()
        parts = upper.split()
        cmd = parts[0]

        # WAIT
        if cmd == "WAIT" or cmd.isdigit():
            if cmd == "WAIT" and len(parts) > 1:
                ms = int(parts[1])
            else:
                ms = int(cmd)
            if ms > 0:
                self._wait(ms)
            return

        # PRINT / ALERT
        if cmd in ("PRINT", "ALERT"):
            return

        # 按键指令 --- 关键修改：保证按下-保持-释放闭环不受停止信号影响
        if cmd in self.BUTTON_MAP or cmd in self.HAT_MAP:
            duration = cfg.key_interval_ms
            down_only = False
            up_only = False

            if len(parts) >= 2:
                arg = parts[1]
                if arg == "DOWN":
                    down_only = True
                elif arg == "UP":
                    up_only = True
                else:
                    try:
                        duration = int(arg)
                    except ValueError:
                        raise ValueError(f"无效的按键持续时间: {arg}")

            if down_only:
                self._press(cmd)
            elif up_only:
                self._release(cmd)
            else:
                # 1. 按下
                self._press(cmd)
                # 2. 保持时间（不可中断）
                self._wait(cfg.press_hold_ms, force=True)
                # 3. 释放（无论停止标志如何，都执行）
                self._release(cmd)
                # 4. 剩余等待（可中断，用于响应停止请求）
                remaining = duration - cfg.press_hold_ms
                if remaining > 0:
                    self._wait(remaining)
            return

        # 摇杆指令
        if cmd in ("LS", "RS"):
            if len(parts) < 2:
                raise ValueError("摇杆指令缺少参数")
            param = parts[1]
            if param == "RESET":
                self._reset_stick(cmd)
                return

            direction = param
            duration = None
            if "," in param:
                dir_part, dur_part = param.split(",", 1)
                direction = dir_part
                duration = int(dur_part)
            elif len(parts) >= 3:
                try:
                    duration = int(parts[2])
                except ValueError:
                    pass

            if direction in ("UP", "DOWN", "LEFT", "RIGHT"):
                self._move_stick(cmd, direction, duration)
            else:
                self.log_signal.emit(f"[警告] 角度摇杆未支持: {line}")
            return

        self.log_signal.emit(f"[警告] 忽略未知指令: {line}")

    # ---------- 底层操作 ----------
    def _press(self, btn: str):
        if btn in self.HAT_MAP:
            hat = self.HAT_MAP[btn]
            self.controller.send_hid_report(hat=hat)
        elif btn in self.BUTTON_MAP:
            mask = self.BUTTON_MAP[btn]
            self.controller.send_hid_report(buttons=mask)
        else:
            self.logger.warning(f"未知按键: {btn}")

    def _release(self, btn: str):
        self.controller.send_hid_report(
            buttons=0, lx=128, ly=128, rx=128, ry=128, hat=SwitchHAT.CENTER
        )

    def _move_stick(self, stick: str, direction: str, duration_ms: Optional[int]):
        lx = ly = rx = ry = 128
        if stick == "LS":
            if direction == "UP":
                ly = 0
            elif direction == "DOWN":
                ly = 255
            elif direction == "LEFT":
                lx = 0
            elif direction == "RIGHT":
                lx = 255
            else:
                return
            self.controller.send_hid_report(lx=lx, ly=ly)
        else:
            if direction == "UP":
                ry = 0
            elif direction == "DOWN":
                ry = 255
            elif direction == "LEFT":
                rx = 0
            elif direction == "RIGHT":
                rx = 255
            else:
                return
            self.controller.send_hid_report(rx=rx, ry=ry)

        if duration_ms is not None:
            self._wait(duration_ms)
            self._reset_stick(stick)

    def _reset_stick(self, stick: str):
        if stick == "LS":
            self.controller.send_hid_report(lx=128, ly=128)
        else:
            self.controller.send_hid_report(rx=128, ry=128)

    def _wait(self, ms: int, force: bool = False):
        """等待指定毫秒。若 force=True 则忽略停止标志，必须完整等待。"""
        if ms <= 0:
            return
        step = 50
        for _ in range(ms // step):
            if not force and self._stop_flag:
                return
            time.sleep(step / 1000.0)
        remainder = ms % step
        if remainder > 0:
            if not force and self._stop_flag:
                return
            time.sleep(remainder / 1000.0)
