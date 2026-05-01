"""
绘图脚本生成器 v2.2.0
将像素画转换为符合官方 EasyCon 语法的线性脚本。
使用 HEX 判断预设调色盘位置。
画笔自适应扫描排序由 SchedulingOptimizer 提供。
在关键步骤插入注释，便于日志中显示宏观目标。
"""

import os
import time
from typing import List, Tuple, Optional
import numpy as np

from core.scheduling.brush import generate_brush_switch_commands
from core.scheduling.palette import (
    generate_palette_commands_preset,
    generate_palette_commands_custom,
    get_default_cursor,
    get_default_hsv,
)
from core.scheduling.move import generate_move_commands
from core.scheduling.optimizer import SchedulingOptimizer
from core.models.drawing import Schedule, Palette


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _instruction_to_script(cmd: Tuple[str, int]) -> str:
    btn, total_ms = cmd
    if btn == "WAIT":
        return f"WAIT {total_ms}"
    return f"{btn} {total_ms}"


def generate_drawing_script(
    color_index_matrix: np.ndarray,
    palette: Palette,
    pixel_size: int,
    use_preset: bool,
    brush_type: Optional[str] = None,
    brush_size: Optional[int] = None,
    press_data: Optional[List[dict]] = None,
) -> Tuple[str, Schedule, int, int]:
    # 1. 确定网格矩阵
    if brush_type is not None and brush_size is not None:
        step = brush_size
        grid_h = color_index_matrix.shape[0] // step
        grid_w = color_index_matrix.shape[1] // step
        grid_matrix = color_index_matrix[::step, ::step]
    else:
        step = 1
        grid_h = color_index_matrix.shape[0]
        grid_w = color_index_matrix.shape[1]
        grid_matrix = color_index_matrix

    # 2. 生成最优调度方案
    optimizer = SchedulingOptimizer()
    schedule, best_desc, logs = optimizer.find_best_schedule(
        grid_matrix,
        brush_type,
        brush_size,
        use_preset,
        grid_w,
        grid_h,
        palette=palette,
        press_data=press_data,
    )

    lines: List[str] = []
    emit = lambda s="": lines.append(s)

    emit("# NS Auto Painter 绘图脚本")
    emit(f"# 模式: {'预设调色盘' if use_preset else '自定义调色盘'}")
    if brush_type:
        emit(f"# 画笔: {brush_type} {brush_size}px")
    emit(f"# 计划: {best_desc}")
    emit()

    # 3. 画笔切换指令
    brush_cmds = (
        generate_brush_switch_commands(brush_type, brush_size) if brush_type else []
    )
    if brush_cmds:
        emit("# === 画笔切换 ===")
        if brush_type:
            emit(f"# 目标画笔: {brush_type} {brush_size}px")
        for cmd in brush_cmds:
            emit(_instruction_to_script(cmd))
        emit()

    # 4. 调色盘初始光标
    if use_preset:
        cur_row, cur_col = get_default_cursor()
    else:
        cur_hsv = get_default_hsv()

    cur_gx, cur_gy = grid_w // 2, grid_h // 2
    emit("# === 开始绘制 ===")

    # 5. 逐区块绘制
    for block, color_order in schedule:
        if not color_order:
            continue
        emit(f"# 区块 ({block.x},{block.y}) {block.w}x{block.h}")

        # 第一个颜色使用简单蛇形排序
        first_color = color_order[0]
        rgb = palette[first_color]
        hex_color = _rgb_to_hex(*rgb)
        points = block.color_points[first_color]
        if points:
            sorted_pts = SchedulingOptimizer._snake_sort_points(points)
        else:
            sorted_pts = []

        # ---- 调色盘切换（第一个颜色）----
        if use_preset:
            palette_cmds, cur_row, cur_col = generate_palette_commands_preset(
                hex_color, cur_row, cur_col
            )
            emit(f"# 切换颜色: HEX {hex_color} (R{cur_row}C{cur_col})")
        else:
            if press_data and first_color < len(press_data):
                target = press_data[first_color]
                target_hsv = (target["h"], target["s"], target["b"])
            else:
                target_hsv = (0, 0, 0)
            palette_cmds = generate_palette_commands_custom(cur_hsv, target_hsv)
            cur_hsv = target_hsv
            emit(
                f"# 切换颜色: 目标 HSB({target_hsv[0]},{target_hsv[1]},{target_hsv[2]})"
            )
        for cmd in palette_cmds:
            emit(_instruction_to_script(cmd))

        # 绘制第一个颜色的点
        emit(f"# 开始绘制颜色 {first_color} (共 {len(sorted_pts)} 个网格)")
        for gx, gy in sorted_pts:
            dx = gx - cur_gx
            dy = gy - cur_gy
            if dx != 0 or dy != 0:
                move_cmds = generate_move_commands(dx, dy, brush_type, brush_size)
                for cmd in move_cmds:
                    emit(_instruction_to_script(cmd))
                cur_gx, cur_gy = gx, gy
            emit("A 100")

        # 后续颜色：使用自适应排序
        for color_idx in color_order[1:]:
            rgb = palette[color_idx]
            hex_color = _rgb_to_hex(*rgb)
            points = block.color_points.get(color_idx, [])
            if not points:
                continue

            sorted_pts = optimizer.sort_points_adaptive(points, cur_gx, cur_gy)

            # ---- 调色盘切换 ----
            if use_preset:
                palette_cmds, cur_row, cur_col = generate_palette_commands_preset(
                    hex_color, cur_row, cur_col
                )
                emit(f"# 切换颜色: HEX {hex_color} (R{cur_row}C{cur_col})")
            else:
                if press_data and color_idx < len(press_data):
                    target = press_data[color_idx]
                    target_hsv = (target["h"], target["s"], target["b"])
                else:
                    target_hsv = (0, 0, 0)
                palette_cmds = generate_palette_commands_custom(cur_hsv, target_hsv)
                cur_hsv = target_hsv
                emit(
                    f"# 切换颜色: 目标 HSB({target_hsv[0]},{target_hsv[1]},{target_hsv[2]})"
                )
            for cmd in palette_cmds:
                emit(_instruction_to_script(cmd))

            # 绘制
            emit(f"# 开始绘制颜色 {color_idx} (共 {len(sorted_pts)} 个网格)")
            for gx, gy in sorted_pts:
                dx = gx - cur_gx
                dy = gy - cur_gy
                if dx != 0 or dy != 0:
                    move_cmds = generate_move_commands(dx, dy, brush_type, brush_size)
                    for cmd in move_cmds:
                        emit(_instruction_to_script(cmd))
                    cur_gx, cur_gy = gx, gy
                emit("A 100")

    emit()
    emit("# === 绘制完成 ===")
    return "\n".join(lines), schedule, grid_w, grid_h
