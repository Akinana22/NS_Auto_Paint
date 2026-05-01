"""
调色盘切换指令生成模块 v2.2.0
按键间隔统一为 key_interval_ms，长按效果使用 key_interval_ms + wait_interval_ms，退出等待使用 wait_interval_ms。
"""

from collections import deque
from typing import List, Tuple, Dict, Optional

from core.image.preset_palette import get_preset_palette_hex
from core.scheduling.timing_config import TimingConfig


def _build_coord_map() -> Dict[str, Tuple[int, int]]:
    hex_list = get_preset_palette_hex()
    coord_map = {}
    idx = 0
    for row in range(1, 8):
        for col in range(1, 12):
            coord_map[hex_list[idx]] = (row, col)
            idx += 1
    for row in range(1, 8):
        coord_map[hex_list[idx]] = (row, 12)
        idx += 1
    return coord_map


_PRESET_COORD_MAP = _build_coord_map()


def _can_wrap_column(row: int) -> bool:
    return 1 <= row <= 3


def _bfs_path(start_r: int, start_c: int, end_r: int, end_c: int) -> List[str]:
    def get_neighbors(r, c):
        neighbors = []
        nr = 7 if r == 1 else r - 1
        neighbors.append(("UP", nr, c))
        nr = 1 if r == 7 else r + 1
        neighbors.append(("DOWN", nr, c))
        if c == 1:
            nc = 12 if _can_wrap_column(r) else None
        else:
            nc = c - 1
        if nc is not None:
            neighbors.append(("LEFT", r, nc))
        if c == 12:
            nc = 1 if _can_wrap_column(r) else None
        else:
            nc = c + 1
        if nc is not None:
            neighbors.append(("RIGHT", r, nc))
        return neighbors

    queue = deque()
    queue.append((start_r, start_c, []))
    visited = {(start_r, start_c)}
    while queue:
        r, c, path = queue.popleft()
        if r == end_r and c == end_c:
            return path
        for action, nr, nc in get_neighbors(r, c):
            if (nr, nc) not in visited:
                visited.add((nr, nc))
                queue.append((nr, nc, path + [action]))
    return []


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def generate_palette_commands_preset(
    target_hex: str,
    cur_row: int,
    cur_col: int,
) -> Tuple[List[Tuple[str, int]], int, int]:
    key = target_hex.upper()
    if key not in _PRESET_COORD_MAP:
        target_rgb = _hex_to_rgb(target_hex)
        min_dist = float("inf")
        nearest_key = None
        for hex_key in _PRESET_COORD_MAP:
            rgb = _hex_to_rgb(hex_key)
            dist = sum((a - b) ** 2 for a, b in zip(target_rgb, rgb))
            if dist < min_dist:
                min_dist = dist
                nearest_key = hex_key
        key = nearest_key

    target_row, target_col = _PRESET_COORD_MAP[key]

    cmds: List[Tuple[str, int]] = [
        (
            "Y",
            TimingConfig.key_interval_ms,
        ),  # 打开快捷栏
        (
            "Y",
            TimingConfig.key_interval_ms + TimingConfig.wait_interval_ms,
        ),  # 打开调色盘
    ]

    path = _bfs_path(cur_row, cur_col, target_row, target_col)
    for action in path:
        cmds.append((action, TimingConfig.key_interval_ms))
    cmds.append(("A", TimingConfig.key_interval_ms))  # 确认
    cmds.append(("WAIT", 2 * TimingConfig.wait_interval_ms))  # 退出等待

    return cmds, target_row, target_col


def generate_palette_commands_custom(
    current_hsv: Tuple[int, int, int],
    target_hsv: Tuple[int, int, int],
) -> List[Tuple[str, int]]:
    h1, s1, b1 = current_hsv
    h2, s2, b2 = target_hsv
    dh = h2 - h1
    sv_interval = TimingConfig.sv_key_interval_ms

    if dh > 0:
        hue_cmds = [("ZR", TimingConfig.key_interval_ms)] * dh
    else:
        hue_cmds = [("ZL", TimingConfig.key_interval_ms)] * (-dh)

    ds = s2 - s1
    if ds > 0:
        sat_cmds = [("RIGHT", sv_interval)] * ds
    else:
        sat_cmds = [("LEFT", sv_interval)] * (-ds)

    db = b2 - b1
    if db > 0:
        val_cmds = [("UP", sv_interval)] * db
    else:
        val_cmds = [("DOWN", sv_interval)] * (-db)

    cmds: List[Tuple[str, int]] = [
        (
            "Y",
            TimingConfig.key_interval_ms,
        ),  # 打开快捷栏
        (
            "Y",
            TimingConfig.key_interval_ms + 2 * TimingConfig.wait_interval_ms,
        ),  # 打开调色盘
        (
            "R",
            TimingConfig.key_interval_ms + 2 * TimingConfig.wait_interval_ms,
        ),  # 切换到自定义模式
    ]
    cmds.extend(hue_cmds)
    cmds.extend(sat_cmds)
    cmds.extend(val_cmds)
    cmds.append(("A", TimingConfig.key_interval_ms))
    cmds.append(("WAIT", 2 * TimingConfig.wait_interval_ms))

    return cmds


def get_default_cursor() -> Tuple[int, int]:
    return 7, 1


def get_default_hsv() -> Tuple[int, int, int]:
    return 0, 0, 0
