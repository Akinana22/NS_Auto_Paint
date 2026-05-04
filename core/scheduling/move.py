"""
画布移动指令生成模块 v2.2.0
画布移动统一使用 key_interval_ms。
支持通过 timing 参数传入冻结的快照，未传则回退 TimingConfig 类属性。
"""

from typing import List, Tuple, Optional
from core.scheduling.timing_config import TimingConfig, TimingSnapshot


def generate_grid_move_commands(
    dx: int, dy: int, move_ms: int = None, timing: Optional[TimingSnapshot] = None
) -> List[Tuple[str, int]]:
    cfg = timing or TimingConfig
    if move_ms is None:
        move_ms = cfg.key_interval_ms
    cmds = []
    while dx != 0 and dy != 0:
        if abs(dx) >= abs(dy):
            direction = "RIGHT" if dx > 0 else "LEFT"
            cmds.append((direction, move_ms))
            dx -= 1 if dx > 0 else -1
        else:
            direction = "DOWN" if dy > 0 else "UP"
            cmds.append((direction, move_ms))
            dy -= 1 if dy > 0 else -1
    while dx != 0:
        direction = "RIGHT" if dx > 0 else "LEFT"
        cmds.append((direction, move_ms))
        dx -= 1 if dx > 0 else -1
    while dy != 0:
        direction = "DOWN" if dy > 0 else "UP"
        cmds.append((direction, move_ms))
        dy -= 1 if dy > 0 else -1
    return cmds


def generate_smooth_move_commands(
    dx: int,
    dy: int,
    repeat: int,
    move_ms: int = None,
    timing: Optional[TimingSnapshot] = None,
) -> List[Tuple[str, int]]:
    base_cmds = generate_grid_move_commands(dx, dy, move_ms, timing=timing)
    expanded = []
    for btn, total_ms in base_cmds:
        for _ in range(repeat):
            expanded.append((btn, total_ms))
    return expanded


def generate_move_commands(
    dx: int,
    dy: int,
    brush_type: str = None,
    brush_size: int = 1,
    move_ms: int = None,
    timing: Optional[TimingSnapshot] = None,
) -> List[Tuple[str, int]]:
    cfg = timing or TimingConfig
    if move_ms is None:
        move_ms = cfg.key_interval_ms
    if brush_type == "smooth" and brush_size > 1:
        return generate_smooth_move_commands(dx, dy, brush_size, move_ms, timing=timing)
    else:
        return generate_grid_move_commands(dx, dy, move_ms, timing=timing)
