"""
调色盘切换指令生成模块 v2.3.0
按键间隔统一为 key_interval_ms，长按效果使用 key_interval_ms + wait_interval_ms，退出等待使用 wait_interval_ms。
支持通过 timing 参数传入冻结的快照，未传则回退 TimingConfig 类属性。
自定义调色盘支持长按/长推优化（3000ms 到达极值再微调）。
"""

from collections import deque
from typing import List, Tuple, Dict, Optional

from core.image.preset_palette import get_preset_palette_hex
from core.scheduling.timing_config import TimingConfig, TimingSnapshot

# 长按/长推固定时长 (ms)
LONG_PRESS_MS = 3000

# 自定义调色盘范围
HUE_MAX = 200
SAT_MAX = 212
VAL_MAX = 111


def _optimize_axis_cmds(
    current: int,
    target: int,
    dec_key: str,
    inc_key: str,
    axis_max: int,
    step_ms: int,
    use_stick: bool = False,
) -> List[Tuple[str, int]]:
    """
    单维度最优指令生成。
    - use_stick=True: 使用左摇杆长推 (极值 3000ms)
    - use_stick=False: 使用 ZL/ZR 长按 (极值 3000ms)
    返回 (cmd_str, ms) 元组列表。
    特殊约定：cmd_str 以 "__DOWN__" 或 "__UP__" 前缀表示持续按下/释放。
    摇杆长推发送 LS DIR 3000 格式（脚本执行器原生支持）。
    """
    if target == current:
        return []

    delta = target - current
    direct_steps = abs(delta)

    # 方案1：纯按键
    if delta > 0:
        direct_cmds = [(inc_key, step_ms)] * direct_steps
        direct_cost = direct_steps * step_ms
    else:
        direct_cmds = [(dec_key, step_ms)] * direct_steps
        direct_cost = direct_steps * step_ms

    if direct_steps <= 1:
        return direct_cmds

    # 方案2：长按/长推到极值 + 微调
    best_extreme = None
    best_cost = direct_cost

    for extreme in (0, axis_max):
        from_extreme_steps = abs(target - extreme)
        via_cost = LONG_PRESS_MS + from_extreme_steps * step_ms
        if via_cost < best_cost:
            best_cost = via_cost
            best_extreme = extreme

    if best_extreme is None:
        return direct_cmds

    cmds: List[Tuple[str, int]] = []

    if use_stick:
        # 左摇杆长推到极值
        if inc_key == "RIGHT":  # S轴
            stick_dir = "LEFT" if best_extreme == 0 else "RIGHT"
        else:  # B轴 (inc_key == "UP")
            stick_dir = "DOWN" if best_extreme == 0 else "UP"
        cmds.append((f"LS {stick_dir}", LONG_PRESS_MS))  # executor 原生支持 "LS LEFT 3000"
    else:
        # ZL/ZR 长按：DOWN → WAIT → UP
        hkey = "ZL" if best_extreme == 0 else "ZR"
        cmds.append((f"__DOWN__{hkey}", 0))
        cmds.append(("WAIT", LONG_PRESS_MS))
        cmds.append((f"__UP__{hkey}", 0))

    # 从极值微调（如果极值与目标相同则跳过）
    adj = target - best_extreme
    if adj > 0:
        cmds.extend([(inc_key, step_ms)] * adj)
    elif adj < 0:
        cmds.extend([(dec_key, step_ms)] * (-adj))

    return cmds


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
    timing: Optional[TimingSnapshot] = None,
) -> Tuple[List[Tuple[str, int]], int, int]:
    cfg = timing or TimingConfig
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
            cfg.key_interval_ms,
        ),  # 打开快捷栏
        (
            "Y",
            cfg.key_interval_ms + cfg.wait_interval_ms,
        ),  # 打开调色盘
    ]

    path = _bfs_path(cur_row, cur_col, target_row, target_col)
    for action in path:
        cmds.append((action, cfg.key_interval_ms))
    cmds.append(("A", cfg.key_interval_ms))  # 确认
    cmds.append(("WAIT", 2 * cfg.wait_interval_ms))  # 退出等待

    return cmds, target_row, target_col


def generate_palette_commands_custom(
    current_hsv: Tuple[int, int, int],
    target_hsv: Tuple[int, int, int],
    timing: Optional[TimingSnapshot] = None,
) -> List[Tuple[str, int]]:
    cfg = timing or TimingConfig
    h1, s1, b1 = current_hsv
    h2, s2, b2 = target_hsv

    # 使用长按/长推优化计算每个维度的最优指令
    hue_cmds = _optimize_axis_cmds(
        h1, h2, "ZL", "ZR", HUE_MAX, cfg.key_interval_ms, use_stick=False
    )
    sat_cmds = _optimize_axis_cmds(
        s1, s2, "LEFT", "RIGHT", SAT_MAX, cfg.sv_key_interval_ms, use_stick=True
    )
    val_cmds = _optimize_axis_cmds(
        b1, b2, "DOWN", "UP", VAL_MAX, cfg.sv_key_interval_ms, use_stick=True
    )

    cmds: List[Tuple[str, int]] = [
        (
            "Y",
            cfg.key_interval_ms,
        ),  # 打开快捷栏
        (
            "Y",
            cfg.key_interval_ms + 2 * cfg.wait_interval_ms,
        ),  # 打开调色盘
        (
            "R",
            cfg.key_interval_ms + 2 * cfg.wait_interval_ms,
        ),  # 切换到自定义模式
    ]
    cmds.extend(hue_cmds)
    cmds.extend(sat_cmds)
    cmds.extend(val_cmds)
    cmds.append(("A", cfg.key_interval_ms))
    cmds.append(("WAIT", 2 * cfg.wait_interval_ms))

    return cmds


def get_default_cursor() -> Tuple[int, int]:
    return 7, 1


def get_default_hsv() -> Tuple[int, int, int]:
    return 0, 0, 0
