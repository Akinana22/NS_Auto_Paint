"""
JSON 导入器 v2.2.0
解析第三方像素画 JSON 文件（如 living-the-grid 格式），转换为内部格式。
支持顺滑画笔和像素画笔两种模式，处理网格居中与缩放。
适配新版 JSON 中的 press 对象（h/s/b 对应 ZR/方向键右/方向键上按下次数），
并处理 h=201 时需要替换为 0 的特殊规则。
颜色匹配使用 HEX 字符串。
"""

import json
import numpy as np
from typing import List, Tuple, Dict, Any, Optional

from core.utils.logger import get_logger
from core.image.preset_palette import get_preset_palette_hex


class JsonImporter:
    """JSON 像素画导入器"""

    def __init__(self):
        self.logger = get_logger("JsonImporter")

    def load_from_file(
        self,
        file_path: str,
        brush_type: str,
        brush_size: int,
    ) -> Tuple[Optional[np.ndarray], Optional[List[List[int]]], Dict[str, Any]]:
        """
        从 JSON 文件加载像素画数据。

        Args:
            file_path: JSON 文件路径
            brush_type: 画笔类型，"smooth"（顺滑）或 "pixel"（像素）
            brush_size: 画笔尺寸（1,3,7,13,19,27 或 4,8,16,32）

        Returns:
            (color_index_matrix, color_palette, metadata)
            - color_index_matrix: 256×256 颜色索引矩阵（-1 表示透明）
            - color_palette: RGB 调色板列表 [[r,g,b], ...]
            - metadata: 包含 width, height, brush_type, brush_size 等信息的字典
        """
        self.logger.info(f"开始导入 JSON 文件: {file_path}")
        self.logger.info(f"画笔类型: {brush_type}, 尺寸: {brush_size}")

        # 1. 读取并解析 JSON
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.error(f"读取 JSON 文件失败: {e}")
            return None, None, {"error": f"读取文件失败: {e}"}

        # 2. 校验必要字段
        required_fields = ["width", "height", "palette", "pixels"]
        for field in required_fields:
            if field not in data:
                self.logger.error(f"JSON 缺少必要字段: {field}")
                return None, None, {"error": f"JSON 格式错误，缺少字段: {field}"}

        width = data["width"]
        height = data["height"]
        raw_palette = data["palette"]
        raw_pixels = data["pixels"]

        # 3. 验证调色板与像素数组格式
        if not isinstance(raw_palette, list) or not isinstance(raw_pixels, list):
            return None, None, {"error": "调色板或像素数组格式错误"}

        if len(raw_pixels) != height:
            self.logger.warning(
                f"像素行数 ({len(raw_pixels)}) 与高度 ({height}) 不匹配"
            )
            height = min(height, len(raw_pixels))

        # 4. 转换调色板：十六进制 -> RGB 元组列表，同时提取 press 数据
        color_palette = []  # 返回的 RGB 列表
        hex_palette = []  # 内部用于与预设表比较的 HEX 列表
        press_data = None
        has_press = False

        for item in raw_palette:
            if isinstance(item, dict):
                # 新版 JSON 格式：{"hex": "#...", "rgb": [...], "press": {...}}
                hex_str = item.get("hex", "")
                if not hex_str.startswith("#"):
                    return None, None, {"error": f"无效的调色板颜色: {item}"}
                hex_str_clean = hex_str.lstrip("#")
                try:
                    r = int(hex_str_clean[0:2], 16)
                    g = int(hex_str_clean[2:4], 16)
                    b = int(hex_str_clean[4:6], 16)
                    color_palette.append([r, g, b])
                except Exception:
                    return None, None, {"error": f"解析颜色失败: {item}"}

                # 保存原始 HEX（统一大写）
                hex_palette.append(hex_str.upper())
                has_press = "press" in item

            elif isinstance(item, str):
                # 旧版格式：纯十六进制字符串，无 press
                hex_str = item.lstrip("#")
                try:
                    r = int(hex_str[0:2], 16)
                    g = int(hex_str[2:4], 16)
                    b = int(hex_str[4:6], 16)
                    color_palette.append([r, g, b])
                except Exception:
                    return None, None, {"error": f"解析颜色失败: {item}"}
                hex_palette.append(item.upper())
            else:
                return None, None, {"error": f"无效的调色板颜色: {item}"}

        # 统一处理 press 数据（新版字典格式）
        if has_press:
            press_data = []
            for item in raw_palette:
                if isinstance(item, dict) and "press" in item:
                    p = item["press"]
                    h = p.get("h", 0)
                    if h in (200, 201):
                        h = 0
                    s = p.get("s", 0)
                    b = p.get("b", 0)
                    press_data.append({"h": h, "s": s, "b": b})
                else:
                    press_data.append({"h": 0, "s": 0, "b": 0})

        # 5. 验证所有颜色是否在预设84色内（基于 HEX 判断）
        preset_hex_set = set(get_preset_palette_hex())
        missing_hex = [h for h in hex_palette if h not in preset_hex_set]

        if missing_hex:
            self.logger.warning(
                f"调色板中有 {len(missing_hex)} 种颜色不在预设84色内，将使用自定义模式"
            )
        else:
            self.logger.info("所有颜色均在预设84色内，可使用预设模式绘图")

        # 6. 计算网格缩放与居中偏移
        cell_span = brush_size
        pattern_width = width * cell_span
        pattern_height = height * cell_span

        if pattern_width > 256 or pattern_height > 256:
            self.logger.warning(
                f"图案尺寸 ({pattern_width}x{pattern_height}) 超过 256x256，将被裁剪"
            )

        offset_x = (256 - pattern_width) // 2
        offset_y = (256 - pattern_height) // 2

        # 7. 构建 256x256 颜色索引矩阵
        color_index_matrix = np.full((256, 256), -1, dtype=np.int16)

        for row in range(height):
            if row >= len(raw_pixels):
                break
            row_data = raw_pixels[row]
            if not isinstance(row_data, list):
                continue
            for col in range(min(width, len(row_data))):
                idx = row_data[col]
                if idx is None:
                    continue
                if not isinstance(idx, int) or idx < 0 or idx >= len(color_palette):
                    continue

                base_x = offset_x + col * cell_span
                base_y = offset_y + row * cell_span

                for dy in range(cell_span):
                    y = base_y + dy
                    if y < 0 or y >= 256:
                        continue
                    for dx in range(cell_span):
                        x = base_x + dx
                        if x < 0 or x >= 256:
                            continue
                        color_index_matrix[y, x] = idx
        # 8. 解析顶层 brush 字段（如果存在）
        json_brush_type = None
        json_brush_size = None
        brush_data = data.get("brush")
        if isinstance(brush_data, dict):
            mode = brush_data.get("mode")
            px = brush_data.get("px")
            if mode in ("smooth", "pixel"):
                json_brush_type = mode
            else:
                self.logger.warning(f"未知的画笔模式: {mode}，忽略")
            if isinstance(px, int):
                json_brush_size = px
            else:
                if json_brush_type is not None:
                    self.logger.warning(f"无效的画笔尺寸: {px}")
                    json_brush_type = None
        # 9. 构建元数据
        metadata = {
            "width": width,
            "height": height,
            "brush_type": brush_type,  # 用户当前选择的画笔类型（调用方传入）
            "brush_size": brush_size,  # 用户当前选择的笔尖大小
            "palette_size": len(color_palette),
            "total_pixels": np.sum(color_index_matrix >= 0),
            "offset": (offset_x, offset_y),
            "all_preset": len(missing_hex) == 0,
            "json_brush_type": json_brush_type,  # 新增：JSON 原始画笔类型
            "json_brush_size": json_brush_size,  # 新增：JSON 原始笔尖大小
        }
        if press_data is not None:
            metadata["press_data"] = press_data

        self.logger.info(f"导入完成，有效像素数: {metadata['total_pixels']}")
        return color_index_matrix, color_palette, metadata
