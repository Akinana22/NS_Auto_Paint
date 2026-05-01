"""
EasyCon 协议常量定义 v2.2.0
包含命令码、回复码、按键掩码等
"""

# 命令码（来自 EasyCon.h）
CMD_READY = 0xA5
CMD_DEBUG = 0x80
CMD_HELLO = 0x81
CMD_FLASH = 0x82
CMD_SCRIPTSTART = 0x83
CMD_SCRIPTSTOP = 0x84
CMD_VERSION = 0x85
CMD_LED = 0x86

# 回复码
REPLY_ERROR = 0x00
REPLY_ACK = 0xFF
REPLY_BUSY = 0xFE
REPLY_HELLO = 0x80
REPLY_FLASHSTART = 0x81
REPLY_FLASHEND = 0x82
REPLY_SCRIPTACK = 0x83

# 设备识别
TARGET_VID = 0x1A86
TARGET_PIDS = [0xFE0C, 0x5740, 0x8001, 0x55D3, 0x7523]

# 串口参数
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0


class SwitchButtons:
    """标准 Switch 手柄按钮掩码（与官方 EasyCon 固件完全一致）"""

    Y = 0x0001
    B = 0x0002
    A = 0x0004
    X = 0x0008
    L = 0x0010
    R = 0x0020
    ZL = 0x0040
    ZR = 0x0080
    MINUS = 0x0100
    PLUS = 0x0200
    LCLICK = 0x0400  # L3 / Lstick
    RCLICK = 0x0800  # R3 / Rstick
    HOME = 0x1000
    CAPTURE = 0x2000


class SwitchHAT:
    """十字键常量（与官方 EasyCon 固件完全一致）"""

    TOP = 0
    TOP_RIGHT = 1
    RIGHT = 2
    BOTTOM_RIGHT = 3
    BOTTOM = 4
    BOTTOM_LEFT = 5
    LEFT = 6
    TOP_LEFT = 7
    CENTER = 8


class SwitchStick:
    """摇杆常量"""

    MIN = 0
    CENTER = 128
    MAX = 255
