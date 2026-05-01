"""
自适应四叉树分割模块 v2.2.0
根据图像颜色分布自动划分不同大小的矩形区块，
用于替代固定 K 值网格分块，优化多色彩像素画的绘制调度。

算法：
- 从覆盖整个画布的根节点开始递归。
- 统计节点内非透明像素的颜色种类数。
- 若种类数 > 阈值且节点尺寸大于 1×1，则四等分并递归处理。
- 否则该节点成为叶子区块（若包含有效像素）。
- 透明区域（颜色索引为 -1）会被忽略，空区块直接丢弃。
"""

from __future__ import annotations

import numpy as np
from typing import List

from core.models.drawing import LeafBlock


def build_quadtree(
    matrix: np.ndarray,
    color_threshold: int = 3,
    x: int = 0,
    y: int = 0,
    w: int = 256,
    h: int = 256,
) -> List[LeafBlock]:
    """
    根据输入的颜色索引矩阵构建四叉树分割，返回叶子区块列表。

    Args:
        matrix: 颜色索引矩阵（0-255 为有效索引，-1 为透明）
        color_threshold: 允许的最大颜色种类数，超过此值则继续分割
        x, y: 当前子区域左上角坐标（用于递归）
        w, h: 当前子区域宽度和高度

    Returns:
        LeafBlock 对象列表，代表所有非空的叶子区块
    """
    # 裁剪区域，避免越界
    max_h, max_w = matrix.shape
    x = max(0, min(x, max_w - 1))
    y = max(0, min(y, max_h - 1))
    w = min(w, max_w - x)
    h = min(h, max_h - y)
    if w <= 0 or h <= 0:
        return []

    sub = matrix[y : y + h, x : x + w]
    actual_h, actual_w = sub.shape

    # 统计当前区域内的颜色种类（非透明像素）
    colors = set()
    for row in range(actual_h):
        for col in range(actual_w):
            idx = sub[row, col]
            if idx >= 0:
                colors.add(int(idx))

    if not colors:
        return []

    # 停止条件：颜色种类不超过阈值，或区域已最小
    if len(colors) <= color_threshold or (actual_w == 1 and actual_h == 1):
        color_points = {}
        for row in range(actual_h):
            for col in range(actual_w):
                idx = int(sub[row, col])
                if idx >= 0:
                    color_points.setdefault(idx, []).append((x + col, y + row))
        block = LeafBlock(x=x, y=y, w=actual_w, h=actual_h, color_points=color_points)
        return [block]

    # 分割当前区域
    left_w = actual_w // 2
    right_w = actual_w - left_w
    top_h = actual_h // 2
    bottom_h = actual_h - top_h

    blocks = []
    blocks.extend(build_quadtree(matrix, color_threshold, x, y, left_w, top_h))
    blocks.extend(
        build_quadtree(matrix, color_threshold, x + left_w, y, right_w, top_h)
    )
    blocks.extend(
        build_quadtree(matrix, color_threshold, x, y + top_h, left_w, bottom_h)
    )
    blocks.extend(
        build_quadtree(
            matrix, color_threshold, x + left_w, y + top_h, right_w, bottom_h
        )
    )
    return blocks
