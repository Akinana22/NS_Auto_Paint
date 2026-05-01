"""
EasyCon 串口通信控制器 v2.2.0
基于官方 EasyCon 软件抓包数据逆向实现。
提供设备发现、串口连接/断开、HID 报告发送、配对信号发送等核心通信能力。

使用方式：
    from core.hal.controller import EasyConController

    ctrl = EasyConController()
    ctrl.connect()                              # 自动查找设备并握手
    ctrl.send_hid_report(buttons=SwitchButtons.A)  # 发送单按键按下
    ctrl.disconnect()
"""

import serial
import serial.tools.list_ports
import time
from typing import Optional, List

from core.hal.constants import (
    CMD_READY,
    CMD_HELLO,
    CMD_SCRIPTSTOP,
    REPLY_HELLO,
    REPLY_ACK,
    REPLY_SCRIPTACK,
    TARGET_VID,
    TARGET_PIDS,
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT,
)
from core.hal.hid_encoder import HIDReportBuilder
from core.utils.logger import get_logger


class EasyConController:
    """EasyCon 固件串口通信控制器"""

    def __init__(self, port: Optional[str] = None, baudrate: int = DEFAULT_BAUDRATE):
        self.port = port
        self.baudrate = baudrate
        self.ser: Optional[serial.Serial] = None
        self._connected = False
        self.logger = get_logger("EasyConController")
        self.logger.info("EasyConController 初始化完成")
        self.hid_builder = HIDReportBuilder()

    @staticmethod
    def _format_hex(data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)

    @classmethod
    def find_device(cls) -> Optional[str]:
        """扫描并返回第一个匹配 VID/PID 的串口设备"""
        logger = get_logger("EasyConController")
        logger.info("扫描 EasyCon 串口设备...")
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid == TARGET_VID and port.pid in TARGET_PIDS:
                logger.info(f"找到设备: {port.device}")
                return port.device
        logger.info("未找到匹配设备")
        return None

    @classmethod
    def list_devices(cls) -> List[str]:
        """列出所有匹配的串口设备"""
        ports = serial.tools.list_ports.comports()
        return [
            port.device
            for port in ports
            if port.vid == TARGET_VID and port.pid in TARGET_PIDS
        ]

    def connect(self) -> bool:
        """打开串口并执行握手"""
        self.logger.info("尝试连接设备...")
        if self.port is None:
            self.port = self.find_device()
            if self.port is None:
                self.logger.error("未找到设备，连接失败")
                return False

        self.logger.info(f"目标端口: {self.port}, 波特率: {self.baudrate}")
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=DEFAULT_TIMEOUT,
                write_timeout=DEFAULT_TIMEOUT,
            )
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            self.logger.info(f"串口 {self.port} 打开成功")

            # 官方握手序列：A5 A5 81
            handshake = bytes([CMD_READY, CMD_READY, CMD_HELLO])
            self.logger.debug(f"发送握手: {self._format_hex(handshake)}")
            self.ser.write(handshake)
            self.ser.flush()

            resp = self.ser.read(1)
            self.logger.debug(f"握手响应: {self._format_hex(resp) if resp else '无'}")
            if len(resp) == 1 and resp[0] == REPLY_HELLO:
                self._connected = True
                self.logger.info("握手成功，设备已连接")
                return True
            else:
                self.logger.warning("握手失败")
                self.ser.close()
                self.ser = None
                return False
        except Exception as e:
            self.logger.error(f"连接异常: {e}", exc_info=True)
            return False

    def disconnect(self):
        """关闭串口连接并释放所有资源"""
        self.logger.info("断开设备连接")
        self._connected = False
        if self.ser:
            try:
                if self.ser.is_open:
                    self.ser.flush()
                    self.ser.close()
                    self.logger.info("串口已关闭")
            except Exception as e:
                self.logger.error(f"关闭串口时发生异常: {e}")
            finally:
                self.ser = None
        else:
            self.logger.debug("串口对象已为空，无需断开")

    def is_connected(self) -> bool:
        """返回当前连接状态"""
        return self._connected and self.ser is not None and self.ser.is_open

    def stop_script(self) -> bool:
        """发送停止脚本命令"""
        if not self.is_connected():
            self.logger.warning("发送 CMD_SCRIPTSTOP 失败：设备未连接")
            return False
        try:
            cmd = bytes([CMD_READY, CMD_SCRIPTSTOP])
            self.logger.info(f"发送 CMD_SCRIPTSTOP: {self._format_hex(cmd)}")
            self.ser.write(cmd)
            self.ser.flush()
            resp = self.ser.read(1)
            self.logger.info(
                f"CMD_SCRIPTSTOP 响应: {self._format_hex(resp) if resp else '无'}"
            )
            return len(resp) == 1 and resp[0] == REPLY_SCRIPTACK
        except Exception as e:
            self.logger.error(f"发送异常: {e}")
            return False

    def send_hid_report(
        self,
        buttons: int = 0,
        lx: int = 128,
        ly: int = 128,
        rx: int = 128,
        ry: int = 128,
        hat: int = 8,
    ) -> bool:
        """
        发送 HID 报告
        :param buttons: 按键位掩码
        :param lx: 左摇杆 X (0-255)
        :param ly: 左摇杆 Y (0-255)
        :param rx: 右摇杆 X (0-255)
        :param ry: 右摇杆 Y (0-255)
        :param hat: 十字键
        :return: 是否发送成功
        """
        if not self.is_connected():
            self.logger.warning("发送 HID 报告失败：设备未连接")
            return False

        packet = self.hid_builder.build(buttons, lx, ly, rx, ry, hat)
        self.logger.debug(
            f"构建 HID 包: {self._format_hex(packet)} (buttons=0x{buttons:04X}, "
            f"lx={lx}, ly={ly}, rx={rx}, ry={ry}, hat={hat})"
        )

        try:
            self.ser.write(packet)
            self.ser.flush()
            resp = self.ser.read(1)
            if len(resp) == 1 and resp[0] == REPLY_ACK:
                self.logger.debug(f"HID 报告发送成功，响应: {self._format_hex(resp)}")
                return True
            else:
                self.logger.warning(
                    f"HID 报告发送失败，响应: {resp.hex() if resp else '无'}"
                )
                return False
        except Exception as e:
            self.logger.error(f"发送 HID 报告异常: {e}", exc_info=True)
            return False

    def send_pairing(self) -> bool:
        """发送配对信号：L+R 按下 1 秒"""
        self.logger.info("发送配对信号 (L+R 按下 1 秒)")
        if not self.send_hid_report(buttons=0x30):
            self.logger.error("发送 L+R 按下失败")
            return False
        time.sleep(1.0)
        success = self.send_hid_report(buttons=0x00)
        self.logger.info(f"配对信号发送完成: {success}")
        return success
