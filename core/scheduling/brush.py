"""
画笔切换指令生成模块 v2.2.0
所有按键间隔统一使用 key_interval_ms，特殊等待使用 wait_interval_ms 叠加。
"""

from typing import List, Tuple
from core.scheduling.timing_config import TimingConfig


def generate_brush_switch_commands(
    brush_type: str, brush_size: int
) -> List[Tuple[str, int]]:
    if brush_type is None or brush_size is None:
        return []

    cmds: List[Tuple[str, int]] = []

    # 打开画笔设置界面
    cmds.append(("X", TimingConfig.key_interval_ms))  # 打开工具栏
    cmds.append(
        ("X", TimingConfig.key_interval_ms + TimingConfig.wait_interval_ms)
    )  # 进入画笔设置(等待画笔工具展开)

    # 切换到像素画笔
    if brush_type == "pixel":
        cmds.append(("UP", TimingConfig.key_interval_ms))
        cmds.append(("RIGHT", TimingConfig.key_interval_ms))
        cmds.append(("A", TimingConfig.key_interval_ms))
        cmds.append(("WAIT", TimingConfig.wait_interval_ms))

    # 方向键移动
    move_sequence = _get_size_move_sequence(brush_type, brush_size)
    for direction in move_sequence:
        cmds.append((direction, TimingConfig.key_interval_ms))

    # 确认与退出
    cmds.append(("A", TimingConfig.key_interval_ms))
    cmds.append(("WAIT", TimingConfig.wait_interval_ms))  # 确保选中生效
    cmds.append(("A", TimingConfig.key_interval_ms))
    cmds.append(("WAIT", TimingConfig.wait_interval_ms))  # 退出工具箱后的稳定等待

    return cmds


def _get_size_move_sequence(brush_type: str, brush_size: int) -> List[str]:
    if brush_type == "smooth":
        smooth_map = {
            1: ["DOWN", "LEFT", "LEFT"],
            3: ["DOWN", "LEFT"],
            7: ["DOWN"],
            13: ["DOWN", "RIGHT"],
            19: ["DOWN", "RIGHT", "RIGHT"],
            27: ["DOWN", "RIGHT", "RIGHT", "RIGHT"],
        }
        if brush_size not in smooth_map:
            raise ValueError(f"不支持的顺滑画笔尺寸: {brush_size}")
        return smooth_map[brush_size]
    elif brush_type == "pixel":
        pixel_map = {
            4: ["DOWN", "DOWN", "LEFT", "LEFT", "LEFT"],
            8: ["DOWN", "DOWN", "LEFT", "LEFT"],
            16: ["DOWN", "DOWN", "LEFT"],
            32: ["DOWN", "DOWN"],
        }
        if brush_size not in pixel_map:
            raise ValueError(f"不支持的像素画笔尺寸: {brush_size}")
        return pixel_map[brush_size]
    else:
        raise ValueError(f"未知的画笔类型: {brush_type}")
