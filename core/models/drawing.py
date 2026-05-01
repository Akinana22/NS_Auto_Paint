"""
绘图领域数据模型 v2.2.0
定义绘图过程中涉及的核心数据结构，与算法实现和 UI 逻辑解耦。
包含：
    - LeafBlock：自适应分块结果
    - Checkpoint：断点恢复上下文
    - Schedule / ColorOrder：类型别名，用于提高可读性
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


@dataclass
class LeafBlock:
    """四叉树或固定网格分块得到的叶子节点，代表一个待绘制的矩形区域"""

    x: int  # 左上角 X 坐标（网格坐标）
    y: int  # 左上角 Y 坐标（网格坐标）
    w: int  # 宽度（网格单位）
    h: int  # 高度（网格单位）
    # 键为颜色索引（int），值为该颜色在此区块内的网格坐标列表 [(x, y), ...]
    color_points: Dict[int, List[Tuple[int, int]]] = field(default_factory=dict)

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)


# 调度计划：每个元素为 (区块, 颜色索引顺序列表)
Schedule = List[Tuple[LeafBlock, List[int]]]

# 调色板：一个颜色的 RGB 值（0~255）
ColorRGB = Tuple[int, int, int]
Palette = List[ColorRGB]


@dataclass
class Checkpoint:
    """
    绘图断点数据模型
    存储在一次绘图任务中任意时刻的完整上下文，可序列化为字典或从字典恢复。
    """

    # 调度计划快照（与设置断点时完全一致）
    schedule: Schedule
    # 当前执行进度
    block_index: int  # 当前区块在 schedule 中的索引
    color_index: int  # 当前颜色在区块 color_order 中的索引
    pixel_index: int  # 当前像素在当前颜色点列表中的索引（已绘制完成的最后一个点）
    cur_x: int  # 当前画笔的网格 X 坐标
    cur_y: int  # 当前画笔的网格 Y 坐标
    # 预设调色盘模式下的光标位置（行/列，1‑based）
    cur_row: int = 7
    cur_col: int = 1
    # 自定义调色盘模式下的当前 HSV 值
    current_hsv: Optional[Tuple[float, float, float]] = None
    original_matrix: Optional[List[List[int]]] = None

    # 绘图参数（用于恢复时重建执行器状态）
    drawing_mode: str = "image"  # "image" 或 "json"
    brush_type: Optional[str] = None  # "smooth" / "pixel" / None
    brush_size: Optional[int] = None
    use_preset_palette: bool = False
    version: str = "2.2.0"  # 断点数据版本号

    def to_dict(self) -> dict:
        """将断点数据序列化为字典（便于 JSON 持久化）"""
        return {
            "version": self.version,
            "drawing_mode": self.drawing_mode,
            "brush_type": self.brush_type,
            "brush_size": self.brush_size,
            "use_preset_palette": self.use_preset_palette,
            "schedule": self._schedule_to_dict(),
            "checkpoint": {
                "block_index": self.block_index,
                "color_index": self.color_index,
                "pixel_index": self.pixel_index,
                "cur_x": self.cur_x,
                "cur_y": self.cur_y,
                "cur_row": self.cur_row,
                "cur_col": self.cur_col,
                "current_hsv": list(self.current_hsv) if self.current_hsv else None,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        """从字典反序列化为 Checkpoint 实例"""
        schedule = cls._schedule_from_dict(data["schedule"])
        cp = data["checkpoint"]
        return cls(
            schedule=schedule,
            block_index=cp["block_index"],
            color_index=cp["color_index"],
            pixel_index=cp["pixel_index"],
            cur_x=cp["cur_x"],
            cur_y=cp["cur_y"],
            cur_row=cp.get("cur_row", 7),
            cur_col=cp.get("cur_col", 1),
            current_hsv=tuple(cp["current_hsv"]) if cp.get("current_hsv") else None,
            drawing_mode=data.get("drawing_mode", "image"),
            brush_type=data.get("brush_type"),
            brush_size=data.get("brush_size"),
            use_preset_palette=data.get("use_preset_palette", False),
            version=data.get("version", "2.2.0"),
        )

    @staticmethod
    def _schedule_to_dict(schedule: Schedule) -> List[dict]:
        """辅助：将 Schedule 转换为可序列化的字典列表"""
        return [
            {
                "x": block.x,
                "y": block.y,
                "w": block.w,
                "h": block.h,
                "colors": [
                    {"index": c, "pixels": block.color_points[c]} for c in color_order
                ],
            }
            for block, color_order in schedule
        ]

    @staticmethod
    def _schedule_from_dict(data: List[dict]) -> Schedule:
        """辅助：从字典列表恢复 Schedule（重建 LeafBlock 对象）"""
        schedule = []
        for blk in data:
            block = LeafBlock(x=blk["x"], y=blk["y"], w=blk["w"], h=blk["h"])
            color_order = []
            for cdata in blk["colors"]:
                idx = cdata["index"]
                block.color_points[idx] = [tuple(p) for p in cdata["pixels"]]
                color_order.append(idx)
            schedule.append((block, color_order))
        return schedule
