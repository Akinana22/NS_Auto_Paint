"""
驱动管理器 v2.2.0
负责检测 Bootloader 模式设备、检查驱动状态、安装 WinUSB 驱动。
仅通过 WMI 完成设备发现与状态判断，不依赖 wchisp.exe。
"""

import sys
import subprocess
import os
import ctypes
from PySide6.QtCore import QObject, Signal, QThread
import wmi

from core.utils.logger import get_logger
from core.utils.resource import resource_path


class BootloaderCheckWorker(QThread):
    """后台检测 Bootloader 设备及驱动状态的线程（纯 WMI 实现）"""

    finished = Signal(
        bool, str
    )  # (成功?, 结果码: "device_found" / "device_not_found" / "unknown_error")
    log_message = Signal(str)

    def __init__(self, target_hardware_id):
        super().__init__()
        self.target_hardware_id = target_hardware_id

    def run(self):
        self.log_message.emit("正在连接 WMI 服务...")
        try:
            c = wmi.WMI()
            self.log_message.emit("正在获取设备列表...")
            # 查询 USB 设备及存在错误代码的设备
            query = (
                "SELECT * FROM Win32_PnPEntity "
                "WHERE DeviceID LIKE '%USB%' OR ConfigManagerErrorCode != 0"
            )
            devices = list(c.query(query))
            self.log_message.emit(f"已获取到 {len(devices)} 个相关设备，开始匹配...")
        except Exception as e:
            self.log_message.emit(f"WMI 连接失败: {e}")
            self.finished.emit(False, f"WMI 连接失败: {e}")
            return

        found_device = None
        error_code = None
        for idx, device in enumerate(devices, 1):
            device_name = device.Name if device.Name else "未知设备"
            self.log_message.emit(f"检查设备 {idx}/{len(devices)}: {device_name}")
            hw_ids = device.HardwareID
            if hw_ids:
                for hw_id in hw_ids:
                    if self.target_hardware_id.upper() in hw_id.upper():
                        found_device = device
                        self.log_message.emit(f"WMI 发现目标设备: {device_name}")
                        break
            if found_device:
                break

        if not found_device:
            self.log_message.emit(
                f"已检查 {len(devices)} 个设备，未找到 Bootloader 设备"
            )
            self.finished.emit(False, "device_not_found")
            return

        # 获取设备状态
        try:
            error_code = found_device.ConfigManagerErrorCode
        except Exception:
            error_code = -1  # 无法获取视为异常

        self.log_message.emit(f"设备状态码 (ConfigManagerErrorCode): {error_code}")

        if error_code == 0:
            # 驱动正常
            self.log_message.emit("驱动状态正常，设备处于 Bootloader 模式")
            self.finished.emit(True, "device_found")  # success=True
        else:
            # 驱动缺失或其他错误（典型值为28）
            self.log_message.emit(f"驱动未安装或异常 (错误代码 {error_code})")
            self.finished.emit(False, "driver_missing")


class DriverManager(QObject):
    driver_ready = Signal()
    driver_missing = Signal(str)
    bootloader_not_found = Signal(str)
    need_admin = Signal()
    status_update = Signal(str)

    CH32_VID = "4348"
    CH32_PID = "55E0"
    TARGET_HARDWARE_ID = f"USB\\VID_{CH32_VID}&PID_{CH32_PID}"

    def __init__(self):
        super().__init__()
        self.logger = get_logger("DriverManager")
        self.logger.info("DriverManager 初始化")
        self.is_admin = self._check_admin_privilege()
        self.logger.info(f"管理员权限: {self.is_admin}")
        self.logger.info(f"目标硬件ID: {self.TARGET_HARDWARE_ID}")
        self.worker = None

    def _check_admin_privilege(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def check_bootloader_and_driver(self):
        """启动后台检测线程（仅使用 WMI）"""
        self.logger.info("开始执行 check_bootloader_and_driver()")
        self.worker = BootloaderCheckWorker(self.TARGET_HARDWARE_ID)
        self.worker.log_message.connect(self._on_worker_log)
        self.worker.finished.connect(self._on_check_finished)
        self.worker.start()

    def _on_worker_log(self, msg):
        self.logger.info(msg)
        self.status_update.emit(msg)

    def install_driver(self) -> bool:
        """使用预置驱动包安装 WinUSB 驱动（需要管理员权限）"""
        if not self.is_admin:
            self.logger.warning("缺少管理员权限，请求提权")
            self.need_admin.emit()
            return False

        self.logger.info("开始安装驱动...")
        driver_dir = resource_path("tools/usb_driver")
        inf_path = os.path.join(driver_dir, "CH32F103C8T6.inf")
        cer_path = os.path.join(driver_dir, "CH32F103C8T6.cer")

        self.logger.info(f"INF 路径: {inf_path}")
        self.logger.info(f"证书路径: {cer_path}")

        if not os.path.exists(inf_path):
            self.logger.error(f"INF 文件不存在: {inf_path}")
            return False
        if not os.path.exists(cer_path):
            self.logger.error(f"证书文件不存在: {cer_path}")
            return False

        # 安装证书
        self.logger.info("正在安装证书...")
        stores = ["Root", "TrustedPublisher"]
        for store in stores:
            cert_cmd = ["certutil", "-addstore", "-f", store, cer_path]
            self.logger.info(f"执行: {' '.join(cert_cmd)}")
            try:
                cert_result = subprocess.run(
                    cert_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                cert_output = (cert_result.stdout + cert_result.stderr).strip()
                self.logger.debug(f"certutil ({store}) 输出:\n{cert_output}")
                if cert_result.returncode != 0:
                    self.logger.error(f"证书安装到 {store} 失败")
                    return False
            except Exception as e:
                self.logger.error(f"安装证书时发生异常: {str(e)}")
                return False

        # 安装驱动
        self.logger.info("正在注册并安装驱动...")
        driver_cmd = ["pnputil", "/add-driver", inf_path, "/install"]
        self.logger.info(f"执行: {' '.join(driver_cmd)}")
        try:
            driver_result = subprocess.run(
                driver_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            driver_output = (driver_result.stdout + driver_result.stderr).strip()
            self.logger.debug(f"pnputil 输出:\n{driver_output}")
            if driver_result.returncode == 0 or "已经安装" in driver_output:
                self.logger.info("驱动安装成功")
                return True
            else:
                self.logger.error(f"驱动安装失败，返回码: {driver_result.returncode}")
                return False
        except Exception as e:
            self.logger.error(f"安装驱动时发生异常: {str(e)}")
            return False

    def request_admin_privilege(self) -> bool:
        """请求以管理员权限重新启动程序"""
        if self.is_admin:
            return True

        self.logger.info("正在请求管理员权限...")
        try:
            params = " ".join([f'"{arg}"' if " " in arg else arg for arg in sys.argv])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, os.getcwd(), 1
            )
            return True
        except Exception as e:
            self.logger.error(f"请求管理员权限失败: {e}")
            return False

    # 信号处理已完全适配新的 worker 返回
    def _on_check_finished(self, success, info):
        """后台检测完成后的处理"""
        if success:
            self.logger.info(f"检测成功，驱动已就绪")
            self.status_update.emit("驱动已就绪，设备处于 Bootloader 模式")
            self.driver_ready.emit()
        else:
            if info == "device_not_found":
                self.logger.info("未检测到 Bootloader 硬件")
                self.status_update.emit("未检测到 Bootloader 硬件")
                self.bootloader_not_found.emit(
                    "未检测到处于 Bootloader 模式的 CH32 设备。\n\n"
                    "请确保：\n"
                    "1. 开发板已通过 USB 连接\n"
                    "2. 跳线帽设置为 BOOT0=1, BOOT1=0\n"
                    "3. 使用 HUSB 接口重新上电"
                )
            elif info == "driver_missing":
                self.logger.warning("设备存在但驱动未安装")
                self.status_update.emit("驱动未安装")
                self.driver_missing.emit(
                    "CH32 设备已处于 Bootloader 模式，但 WinUSB 驱动未安装。\n\n"
                    "请点击下方按钮安装驱动。"
                )
            else:
                self.logger.error(f"检测过程出错: {info}")
                self.status_update.emit(f"检测出错: {info}")
                self.driver_missing.emit(f"检测过程出错: {info}")
