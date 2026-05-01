"""
串口扫描与握手模块 v2.2.0
提供扫描 CH32 串口设备的功能，以及用于正式握手的线程类
"""

import serial
import serial.tools.list_ports
import time
from PySide6.QtCore import QThread, Signal

from core.utils.logger import get_logger


def scan_serial_ports() -> list:
    """
    扫描所有串口，返回匹配 CH32 设备的端口列表。
    :return: 端口号列表，如 ['COM3']
    """
    logger = get_logger("SerialScanner")
    logger.info("开始扫描 CH32 串口设备...")
    target_vid = 0x1A86
    target_pids = [0x55D3, 0x7523, 0x55D4, 0xFE0C, 0x5740, 0x8001]
    ports = serial.tools.list_ports.comports()
    wch_ports = []
    for port in ports:
        if port.vid == target_vid and port.pid in target_pids:
            logger.info(
                f"发现设备: {port.device} (VID=0x{port.vid:04X}, PID=0x{port.pid:04X})"
            )
            wch_ports.append(port.device)
    if not wch_ports:
        logger.info("未找到匹配的 CH32 串口设备")
    return wch_ports


class SerialHandshakeWorker(QThread):
    """
    串口握手线程
    用于在工具选择页点击“自动连接”时，正式与设备握手。
    """

    handshake_success = Signal(str)
    handshake_failed = Signal()

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.logger = get_logger("SerialHandshakeWorker")

    @staticmethod
    def _format_hex(data):
        return " ".join(f"{b:02X}" for b in data) if data else "无"

    def run(self):
        self.logger.info(f"开始握手，端口: {self.port}")
        try:
            ser = serial.Serial(
                port=self.port, baudrate=115200, timeout=1, write_timeout=1
            )
            ser.dtr = True
            ser.rts = True
            time.sleep(0.1)

            # 官方握手序列：A5 A5 81
            handshake = bytes([0xA5, 0xA5, 0x81])
            self.logger.info(f"发送握手: {self._format_hex(handshake)}")
            ser.write(handshake)
            ser.flush()

            resp = ser.read(1)
            self.logger.info(f"收到握手响应: {self._format_hex(resp)}")
            ser.close()

            if len(resp) == 1 and resp[0] == 0x80:
                self.logger.info("握手成功")
                self.handshake_success.emit(self.port)
            else:
                self.logger.warning("握手失败：响应不是 0x80")
                self.handshake_failed.emit()
        except Exception as e:
            self.logger.error(f"握手异常: {e}")
            self.handshake_failed.emit()
