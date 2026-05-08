"""
画笔切换指令生成模块 v2.3.0
基于游戏内画笔工具 3 行 × 6 列网格 UI 重构。
提供两种入口函数：
    generate_brush_nav_sequence   — 从初始状态到目标的导航序列（新建/已保存恢复）
    generate_brush_switch_sequence — 笔尖间增量切换序列（暂停恢复）
支持通过 timing 参数传入冻结的快照，未传则回退 TimingConfig 类属性。
"""

from collections import deque
from typing import List, Tuple, Optional

from core.scheduling.timing_config import TimingConfig, TimingSnapshot

# ============================================================
# 数据定义
# ============================================================

# 顺滑画笔尺寸对应 R3 列号 (1-indexed)
SMOOTH_SIZE_TO_COL = {1: 1, 3: 2, 7: 3, 13: 4, 19: 5, 27: 6}

# 像素画笔尺寸对应 R3 列号 (1-indexed)
PIXEL_SIZE_TO_COL = {4: 2, 8: 3, 16: 4, 32: 5}

# R1 按钮所在列（合并单元格，定位列为中心偏左列）
R1_COLS = {1, 3, 5}

# R1 按钮名称
R1_LABEL = {1: "顺滑画笔", 3: "其他画笔", 5: "像素画笔"}

# 画笔类型 → 像素模式的 R1 按钮列
TYPE_TO_R1_COL = {"smooth": 1, "pixel": 5}

# R1 列 → 顺滑模式第一笔尖列 (R2Cx)
R1_TO_SMOOTH_R2 = {1: 1, 3: 3, 5: 5}

# R1 列 → 像素模式第一笔尖列 (R2Cx)
R1_TO_PIXEL_R2 = {1: 2, 3: 3, 5: 5}

# R2 列 → R1 列 (Rule 4: C1/C2→C1, C3/C4→C3, C5/C6→C5)
R2_TO_R1 = {1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 5}

# 初始状态
INITIAL_TYPE = "smooth"
INITIAL_ROW = 2
INITIAL_COL = 3  # 7px圆


def _is_valid_cell(row: int, col: int, brush_mode: str) -> bool:
    """判断 (row, col) 在当前画笔模式网格中是否有效"""
    if row == 1:
        return col in R1_COLS
    if row in (2, 3):
        if brush_mode == "smooth":
            return 1 <= col <= 6
        elif brush_mode == "pixel":
            return 2 <= col <= 5
    return False


def _get_neighbors(row: int, col: int, brush_mode: str) -> List[Tuple[int, int, str]]:
    """获取当前格子可移动的方向列表，返回 [(next_row, next_col, direction), ...]"""
    neighbors = []

    # 左右移动
    if row in (2, 3):
        ncol = col - 1
        if _is_valid_cell(row, ncol, brush_mode):
            neighbors.append((row, ncol, "LEFT"))
        ncol = col + 1
        if _is_valid_cell(row, ncol, brush_mode):
            neighbors.append((row, ncol, "RIGHT"))
    elif row == 1:
        ncol = col - 2  # R1 按钮之间跳一格
        if _is_valid_cell(1, ncol, brush_mode):
            neighbors.append((1, ncol, "LEFT"))
        ncol = col + 2
        if _is_valid_cell(1, ncol, brush_mode):
            neighbors.append((1, ncol, "RIGHT"))

    # 上下移动
    if row == 1:
        # DOWN: R1→R2 (Rule 3)
        if brush_mode == "smooth":
            r2col = R1_TO_SMOOTH_R2[col]
        else:
            r2col = R1_TO_PIXEL_R2[col]
        if _is_valid_cell(2, r2col, brush_mode):
            neighbors.append((2, r2col, "DOWN"))
    elif row == 2:
        # UP: R2→R1 (Rule 4)
        r1col = R2_TO_R1[col]
        neighbors.append((1, r1col, "UP"))
        # DOWN: R2→R3
        if _is_valid_cell(3, col, brush_mode):
            neighbors.append((3, col, "DOWN"))
    elif row == 3:
        # UP: R3→R2
        if _is_valid_cell(2, col, brush_mode):
            neighbors.append((2, col, "UP"))

    return neighbors


def _bfs_brush_path(
    start_row: int, start_col: int,
    target_row: int, target_col: int,
    brush_mode: str,
) -> List[str]:
    """BFS 最短路径，返回方向指令列表"""
    if start_row == target_row and start_col == target_col:
        return []

    queue = deque()
    queue.append((start_row, start_col, []))
    visited = {(start_row, start_col)}

    while queue:
        r, c, path = queue.popleft()
        for nr, nc, direction in _get_neighbors(r, c, brush_mode):
            if (nr, nc) not in visited:
                new_path = path + [direction]
                if nr == target_row and nc == target_col:
                    return new_path
                visited.add((nr, nc))
                queue.append((nr, nc, new_path))
    return []


def _commands_for_path(
    path: List[str],
    timing: Optional[TimingSnapshot],
    include_type_select: bool = False,
    include_tip_confirm: bool = False,
) -> List[Tuple[str, int]]:
    """将方向路径转换为指令列表，可选包含 R1 A（选择类型）和 R3 A+A+WAIT（确认）"""
    cfg = timing or TimingConfig
    cmds: List[Tuple[str, int]] = []

    for direction in path:
        cmds.append((direction, cfg.key_interval_ms))

    if include_type_select:
        cmds.append(("A", cfg.key_interval_ms))
        cmds.append(("WAIT", cfg.wait_interval_ms))

    if include_tip_confirm:
        cmds.append(("A", cfg.key_interval_ms))  # 选择笔尖
        cmds.append(("A", cfg.key_interval_ms))  # 确认
        cmds.append(("WAIT", cfg.wait_interval_ms))

    return cmds


# ============================================================
# 公开接口
# ============================================================

def generate_brush_nav_sequence(
    brush_type: str,
    brush_size: int,
    timing: Optional[TimingSnapshot] = None,
) -> List[Tuple[str, int]]:
    """
    从画布初始状态导航到目标笔尖。
    适用于：全新绘画任务、从保存中恢复的绘画任务。
    假设进入工具栏时状态为初始：顺滑画笔类型，光标在 R2C3(7px圆)。
    """
    if brush_type is None or brush_size is None:
        return []

    cfg = timing or TimingConfig
    cmds: List[Tuple[str, int]] = []

    # 打开工具栏 → 进入画笔工具
    cmds.append(("X", cfg.key_interval_ms))
    cmds.append(("X", cfg.key_interval_ms + cfg.wait_interval_ms))

    # 初始状态：smooth 模式, 光标 R2C3
    cur_row, cur_col = INITIAL_ROW, INITIAL_COL
    cur_type = INITIAL_TYPE

    # 计算目标 R3 列
    if brush_type == "smooth":
        target_col = SMOOTH_SIZE_TO_COL[brush_size]
    elif brush_type == "pixel":
        target_col = PIXEL_SIZE_TO_COL[brush_size]
    else:
        raise ValueError(f"未知的画笔类型: {brush_type}")

    # ---- 导航 ----
    if cur_type != brush_type:
        # 先到 R1
        path = _bfs_brush_path(cur_row, cur_col, 1, R2_TO_R1[cur_col], cur_type)
        cmds.extend(_commands_for_path(path, timing))

        # 在 R1 左右移动到目标类型按钮
        r1_target_col = TYPE_TO_R1_COL[brush_type]
        r1_cur = R2_TO_R1[cur_col]
        if r1_cur != r1_target_col:
            r1_path = _bfs_brush_path(1, r1_cur, 1, r1_target_col, cur_type)
            cmds.extend(_commands_for_path(r1_path, timing))

        # 选择类型
        cmds.append(("A", cfg.key_interval_ms))
        cmds.append(("WAIT", cfg.wait_interval_ms))

        # 切换到新类型网格后，光标仍在 R1 按钮
        cur_type = brush_type
        cur_row, cur_col = 1, r1_target_col

    # 从当前位置导航到 R3 目标笔尖
    # 先到 R2 目标列（如果不在 R1 则需要处理）
    if cur_row == 1:
        # R1 DOWN 到 R2
        if brush_type == "smooth":
            r2col = R1_TO_SMOOTH_R2[cur_col]
        else:
            r2col = R1_TO_PIXEL_R2[cur_col]
        path = _bfs_brush_path(cur_row, cur_col, 2, r2col, brush_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 2, r2col

    # R2 内左右移动到目标列，再 DOWN 到 R3
    if cur_col != target_col:
        path = _bfs_brush_path(cur_row, cur_col, 2, target_col, brush_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 2, target_col

    # DOWN 到 R3
    if cur_row == 2:
        path = _bfs_brush_path(cur_row, cur_col, 3, target_col, brush_type)
        cmds.extend(_commands_for_path(path, timing))

    # 确认笔尖
    cmds.append(("A", cfg.key_interval_ms))  # 选择笔尖
    cmds.append(("A", cfg.key_interval_ms))  # 确认
    cmds.append(("WAIT", cfg.wait_interval_ms))

    return cmds


def generate_brush_switch_sequence(
    current_type: str,
    current_size: int,
    target_type: str,
    target_size: int,
    timing: Optional[TimingSnapshot] = None,
) -> List[Tuple[str, int]]:
    """
    笔尖间增量切换序列。
    适用于：暂停恢复（未退出绘画界面，工具栏状态保持）。
    假设当前状态为上次确认后光标停留在 R3 目标列。
    """
    if current_type is None or current_size is None:
        return []
    if target_type is None or target_size is None:
        return []

    cfg = timing or TimingConfig
    cmds: List[Tuple[str, int]] = []

    # 打开工具栏 → 进入画笔工具
    cmds.append(("X", cfg.key_interval_ms))
    cmds.append(("X", cfg.key_interval_ms + cfg.wait_interval_ms))

    # 当前光标位置：R3, current_col
    if current_type == "smooth":
        cur_col = SMOOTH_SIZE_TO_COL[current_size]
    elif current_type == "pixel":
        cur_col = PIXEL_SIZE_TO_COL[current_size]
    else:
        raise ValueError(f"未知的画笔类型: {current_type}")

    if target_type == "smooth":
        target_col = SMOOTH_SIZE_TO_COL[target_size]
    elif target_type == "pixel":
        target_col = PIXEL_SIZE_TO_COL[target_size]
    else:
        raise ValueError(f"未知的画笔类型: {target_type}")

    cur_row, cur_col = 3, cur_col
    cur_type = current_type

    # ---- 类型切换 ----
    if cur_type != target_type:
        # UP to R2
        path = _bfs_brush_path(cur_row, cur_col, 2, cur_col, cur_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 2, cur_col

        # UP to R1
        r1col = R2_TO_R1[cur_col]
        path = _bfs_brush_path(cur_row, cur_col, 1, r1col, cur_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 1, r1col

        # R1 左右移动到目标类型
        r1_target = TYPE_TO_R1_COL[target_type]
        if cur_col != r1_target:
            r1_path = _bfs_brush_path(1, cur_col, 1, r1_target, cur_type)
            cmds.extend(_commands_for_path(r1_path, timing))
            cur_col = r1_target

        # 选择类型
        cmds.append(("A", cfg.key_interval_ms))
        cmds.append(("WAIT", cfg.wait_interval_ms))

        cur_type = target_type

    # 从当前位置（R1 或 R3）导航到 R3 目标
    if cur_row == 1:
        if target_type == "smooth":
            r2col = R1_TO_SMOOTH_R2[cur_col]
        else:
            r2col = R1_TO_PIXEL_R2[cur_col]
        path = _bfs_brush_path(cur_row, cur_col, 2, r2col, target_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 2, r2col

    # R2→R3 导航
    if cur_col != target_col:
        path = _bfs_brush_path(cur_row, cur_col, 2, target_col, target_type)
        cmds.extend(_commands_for_path(path, timing))
        cur_row, cur_col = 2, target_col

    if cur_row == 2:
        path = _bfs_brush_path(2, cur_col, 3, target_col, target_type)
        cmds.extend(_commands_for_path(path, timing))

    # 确认笔尖
    cmds.append(("A", cfg.key_interval_ms))  # 选择笔尖
    cmds.append(("A", cfg.key_interval_ms))  # 确认
    cmds.append(("WAIT", cfg.wait_interval_ms))

    return cmds
