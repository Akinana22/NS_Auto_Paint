"""
预设调色板模块 v2.2.0
包含《朋友收集 梦想生活》游戏内基础84色调色板数据。
数据以十六进制字符串存储，行列排布与游戏一致。
提供获取 HEX 列表、RGB 列表、归一化 RGB 数组的接口。
"""

import numpy as np

# ============================================================
# 游戏内基础84色 HEX 值（按游戏内顺序）
# ============================================================
PRESET_PALETTE_HEX = [
    # 第1行 (R1)
    "#FFFFFF",
    "#F1EFF8",
    "#F0F0F8",
    "#F0F7FF",
    "#F0FBF4",
    "#F0F4EE",
    "#F5FAF0",
    "#FDFDEE",
    "#FEF3EF",
    "#FAF0F0",
    "#FDEDDC",
    # 第2行 (R2)
    "#EBEBEB",
    "#CFC8E9",
    "#C7CDE7",
    "#C8E9FD",
    "#C8F1D7",
    "#C7DBC8",
    "#DAEEC8",
    "#FBF9C8",
    "#FCD6C9",
    "#EFC9C8",
    "#E4CFB0",
    # 第3行 (R3)
    "#D5D5D3",
    "#A592D7",
    "#919FD5",
    "#92D6FD",
    "#92E6BA",
    "#92BD94",
    "#BBE294",
    "#FAF592",
    "#FBB491",
    "#E29691",
    "#CAA976",
    # 第4行 (R4)
    "#BCBCBC",
    "#6527C2",
    "#004AC0",
    "#06C2FE",
    "#00DA90",
    "#019616",
    "#92D314",
    "#F9F000",
    "#F78400",
    "#D42700",
    "#91610D",
    # 第5行 (R5)
    "#9C9D9A",
    "#5620AA",
    "#003FA4",
    "#02A5D8",
    "#03BC7B",
    "#03800E",
    "#7DB50C",
    "#D6CE00",
    "#D57100",
    "#B62100",
    "#774200",
    # 第6行 (R6)
    "#727272",
    "#421785",
    "#003281",
    "#0084AB",
    "#009360",
    "#00650C",
    "#628E0D",
    "#A9A200",
    "#A85801",
    "#901600",
    "#5D380C",
    # 第7行 (R7)
    "#000000",
    "#22094C",
    "#001648",
    "#014963",
    "#025435",
    "#013800",
    "#355100",
    "#605D00",
    "#602E01",
    "#510C00",
    "#34220D",
    # 附加 E 列 (E1~E7)
    "#FE2500",
    "#FFFB00",
    "#07F900",
    "#02FDFF",
    "#0432FE",
    "#8836FF",
    "#FF36C3",
]

assert (
    len(PRESET_PALETTE_HEX) == 84
), f"调色板颜色数应为84，实际为{len(PRESET_PALETTE_HEX)}"


def _hex_to_rgb(hex_color: str):
    """将 #RRGGBB 转换为 (R, G, B) 0-255 元组"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _hex_list_to_rgb():
    """返回 84 色 RGB 列表"""
    return [[*_hex_to_rgb(c)] for c in PRESET_PALETTE_HEX]


def _hex_list_to_normalized():
    """返回归一化 RGB numpy 数组 (84, 3)"""
    rgb_list = _hex_list_to_rgb()
    return np.array(rgb_list, dtype=np.float32) / 255.0


def get_preset_palette_hex() -> list:
    """返回预设调色板的 HEX 字符串列表（84 个）"""
    return PRESET_PALETTE_HEX.copy()


def get_preset_palette(normalized: bool = True):
    """
    获取预设调色板数据。

    Args:
        normalized: True 返回归一化 (0~1) numpy 数组；False 返回 RGB (0~255) 列表。
    """
    if normalized:
        return _hex_list_to_normalized()
    else:
        return _hex_list_to_rgb()


def get_preset_color_count() -> int:
    """返回预设调色板包含的颜色数量 (84)。"""
    return len(PRESET_PALETTE_HEX)
