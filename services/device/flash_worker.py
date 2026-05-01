"""
烧录工作线程 v2.2.0
用于异步执行 wchisp 命令（info / flash）。
wchisp.exe 的路径由调用方通过 resource_path("tools/wchisp.exe") 获取并传入。
"""

from PySide6.QtCore import QThread, Signal, QProcess
from core.utils.logger import get_logger


class FlashWorker(QThread):
    output_log = Signal(str)
    probe_finished = Signal(bool, str)
    flash_progress = Signal(int, str)
    flash_finished = Signal(bool, str)

    def __init__(self, wchisp_path, command, arguments=None):
        super().__init__()
        self.logger = get_logger("FlashWorker")
        self.wchisp_path = wchisp_path
        self.command = command
        self.arguments = arguments or []
        self.process = None
        self.logger.info(f"FlashWorker 初始化: command={command}, args={arguments}")

    def run(self):
        self.logger.info(
            f"启动进程: {self.wchisp_path} {self.command} {' '.join(self.arguments)}"
        )
        self.process = QProcess()
        self.process.setProgram(self.wchisp_path)
        args = [self.command] + self.arguments
        self.process.setArguments(args)

        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)

        self.process.start()
        self.exec()

    def on_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors="replace")
        self.output_log.emit(data.strip())
        self.logger.debug(f"stdout: {data.strip()}")

        if self.command == "info":
            for line in data.splitlines():
                if "Chip:" in line:
                    self.logger.info(f"探测到芯片: {line.strip()}")
                    self.probe_finished.emit(True, line.strip())
                    return
        elif self.command == "flash":
            for line in data.splitlines():
                line_lower = line.lower()
                if "erasing" in line_lower:
                    self.logger.debug("烧录阶段: 擦除中")
                    self.flash_progress.emit(20, "正在擦除旧固件...")
                elif "writing to code flash" in line_lower:
                    self.logger.debug("烧录阶段: 写入中")
                    self.flash_progress.emit(50, "正在写入固件...")
                elif "verifying" in line_lower:
                    self.logger.debug("烧录阶段: 校验中")
                    self.flash_progress.emit(80, "正在校验固件...")
                elif "verify ok" in line_lower:
                    self.logger.debug("烧录阶段: 校验通过")
                    self.flash_progress.emit(100, "校验完成")
                elif "writing" in line_lower and "%" in line:
                    try:
                        percent_str = line.split("%")[0].split()[-1]
                        percent = int(percent_str)
                        self.logger.debug(f"烧录进度: {percent}%")
                        self.flash_progress.emit(percent, f"烧录中... {percent}%")
                    except:
                        pass

    def on_stderr(self):
        data = self.process.readAllStandardError().data().decode(errors="replace")
        self.output_log.emit(f"[stderr] {data.strip()}")
        self.logger.warning(f"stderr: {data.strip()}")

    def on_finished(self, exit_code, exit_status):
        self.logger.info(f"进程结束，退出码: {exit_code}")
        if self.command == "info":
            if exit_code != 0:
                self.logger.warning("探测失败")
                self.probe_finished.emit(False, "")
        elif self.command == "flash":
            success = exit_code == 0
            msg = "烧录成功！" if success else f"烧录失败，错误码: {exit_code}"
            self.logger.info(msg)
            if success:
                self.flash_progress.emit(100, "烧录完成")
            self.flash_finished.emit(success, msg)
        self.quit()
