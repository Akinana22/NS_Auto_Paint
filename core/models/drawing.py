"""
绘图领域数据模型 v2.2.0
定义绘图过程中涉及的核心数据结构，与算法实现和 UI 逻辑解耦。
包含：
    - LeafBlock：自适应分块结果
    - Schedule / ColorOrder：类型别名，用于提高可读性
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


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
