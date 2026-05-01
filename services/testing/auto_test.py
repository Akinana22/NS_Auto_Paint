"""
自动测试控制器 v2.2.0
管理 KeyTestWorker 的生命周期、进度和状态。
属于 services/testing 层，依赖 QtCore 信号但不依赖 UI 组件。
"""

from PySide6.QtCore import QObject, Signal
from services.testing.test_worker import KeyTestWorker
from core.utils.logger import get_logger


class AutoTestController(QObject):
    status_changed = Signal(str)  # 状态文本（用于状态标签）
    log_message = Signal(str)  # 日志消息（追加到文本框）
    progress_changed = Signal(int)  # 进度百分比
    test_finished = Signal()  # 测试结束（用于按钮恢复）

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.logger = get_logger("AutoTestController")
        self.test_worker = None

    def start_test(self):
        """开始自动测试"""
        if self.test_worker is not None:
            return
        self.logger.info("开始自动测试")
        self.test_worker = KeyTestWorker(self.controller)
        self.test_worker.log_message.connect(self._on_log_message)
        self.test_worker.test_finished.connect(self._on_test_finished)
        self.test_worker.progress_update.connect(self.progress_changed)
        self.test_worker.start()
        self.status_changed.emit("自动测试运行中...")

    def stop_test(self):
        """停止自动测试"""
        if self.test_worker is not None:
            self.logger.info("用户停止自动测试")
            self.test_worker.cancel()
        else:
            self.logger.warning("尝试停止测试但无活动测试")

    def is_running(self) -> bool:
        return self.test_worker is not None

    def _on_log_message(self, message: str):
        self.log_message.emit(message)

    def _on_test_finished(self):
        self.logger.info("自动测试完成")
        self.test_worker = None
        self.test_finished.emit()
        self.status_changed.emit("自动测试完成")
