"""
画布模式数据模型 v2.3.0
定义《朋友收集 梦想生活》中五种绘画模式的实际绘画区域与画笔起始位置。
实际绘画区域限制落笔是否生效，不限制笔尖移动范围。
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CanvasMode:
    name: str          # 模式名称
    width: int         # 画布总宽度 (px)
    height: int        # 画布总高度 (px)
    active_x: int      # 有效绘画区域左上角 X
    active_y: int      # 有效绘画区域左上角 Y
    active_w: int      # 有效绘画区域宽度
    active_h: int      # 有效绘画区域高度
    start_x: int       # 画笔初始 X（画布中心）
    start_y: int       # 画笔初始 Y（画布中心）

    @property
    def active_x2(self) -> int:
        return self.active_x + self.active_w

    @property
    def active_y2(self) -> int:
        return self.active_y + self.active_h

    def is_in_active_area(self, x: int, y: int) -> bool:
        return (
            self.active_x <= x < self.active_x2
            and self.active_y <= y < self.active_y2
        )

    def clamp_to_active(self, x: int, y: int) -> Tuple[int, int]:
        return (
            max(self.active_x, min(x, self.active_x2 - 1)),
            max(self.active_y, min(y, self.active_y2 - 1)),
        )


CANVAS_MODES = {
    "standard": CanvasMode(
        name="标准",
        width=256, height=256,
        active_x=0, active_y=0, active_w=256, active_h=256,
        start_x=128, start_y=128,
    ),
    "book": CanvasMode(
        name="书籍",
        width=256, height=256,
        active_x=38, active_y=0, active_w=180, active_h=256,
        start_x=128, start_y=128,
    ),
    "tv": CanvasMode(
        name="电视",
        width=256, height=256,
        active_x=0, active_y=62, active_w=256, active_h=131,
        start_x=128, start_y=128,
    ),
    "game": CanvasMode(
        name="游戏",
        width=256, height=256,
        active_x=0, active_y=56, active_w=256, active_h=144,
        start_x=128, start_y=128,
    ),
    "decoration": CanvasMode(
        name="装修",
        width=256, height=256,
        active_x=42, active_y=0, active_w=172, active_h=256,
        start_x=128, start_y=128,
    ),
}

DEFAULT_CANVAS_MODE = "standard"

# JSON "canvas.preset" 值 → 内部 key 映射
JSON_TO_CANVAS_MODE = {
    "square": "standard",
    "book": "book",
    "tv": "tv",
    "videogame": "game",
    "interior": "decoration",
}

# 内部 key → UI 显示名
CANVAS_MODE_DISPLAY = {
    "standard": "标准",
    "book": "书籍",
    "tv": "电视",
    "game": "游戏",
    "decoration": "装修",
}


def get_canvas_mode(mode: str = None) -> CanvasMode:
    """获取画布模式配置，默认返回 standard"""
    return CANVAS_MODES.get(mode or DEFAULT_CANVAS_MODE, CANVAS_MODES[DEFAULT_CANVAS_MODE])


def json_preset_to_canvas_mode(preset: str) -> str:
    """将 JSON canvas.preset 值映射为内部 key，未匹配返回 standard"""
    return JSON_TO_CANVAS_MODE.get(preset, DEFAULT_CANVAS_MODE)
