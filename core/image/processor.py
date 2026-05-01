"""
图像像素化处理模块 v2.2.0
提供将任意图片转换为像素风格并生成颜色索引矩阵的核心算法。
支持预设调色盘（84色 K-Means 聚类）和自定义调色盘（Pyxelate 自动提取）两种模式。
"""

import sys
import os
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

from core.utils.logger import get_logger
from core.image.preset_palette import get_preset_palette

# 允许的颜色数量列表（自定义模式）
ALLOWED_COLOR_COUNTS = [4, 8, 16, 32, 64, 128, 256]


def clamp_color_count(value: int) -> int:
    """将颜色数量钳位到最近的合法值"""
    clamped = min(ALLOWED_COLOR_COUNTS, key=lambda x: abs(x - value))
    logger = get_logger("image_processor")
    logger.info(f"[颜色数钳位] 输入: {value} -> 输出: {clamped}")
    return clamped


def pixelate_image_pyxelate(
    image_path: str,
    pixel_size: int,
    max_colors: int,
    output_color_data_path: str = None,
    use_preset: bool = False,
):
    """
    对图片进行像素化处理。

    Args:
        image_path: 输入图片路径
        pixel_size: 目标像素尺寸（最大边长对应的像素数）
        max_colors: 最大颜色数
        output_color_data_path: 可选，保存色彩数据到 .npz 文件
        use_preset: True 使用预设84色调色板 + K-Means；False 使用 Pyxelate 自动提取

    Returns:
        (canvas, color_palette, color_index_matrix)
        - canvas: PIL.Image，256x256 RGBA 像素图
        - color_palette: list of [r,g,b]，调色板
        - color_index_matrix: np.ndarray (256, 256)，颜色索引（-1 = 透明）
    """
    # 动态导入 Pyxelate（仅在自定义模式时需要）
    if not use_preset:
        libs_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libs"
        )
        if libs_path not in sys.path:
            sys.path.insert(0, libs_path)
        from libs.pyxelate import Pyx

    logger = get_logger("image_processor")
    logger.info("=" * 70)
    logger.info(f"[开始像素化] 文件: {os.path.basename(image_path)}")
    logger.info(
        f"[参数] pixel_size = {pixel_size}, max_colors = {max_colors}, "
        f"use_preset = {use_preset}"
    )

    # 1. 加载图片，保留 RGBA
    img = Image.open(image_path).convert("RGBA")
    orig_w, orig_h = img.size
    logger.info(f"[原图尺寸] {orig_w} x {orig_h}")

    # 2. 分离通道
    r, g, b, a = img.split()
    rgb_img = Image.merge("RGB", (r, g, b))

    # 3. 计算降采样倍数
    max_dim = max(orig_w, orig_h)
    factor = max_dim / pixel_size if pixel_size > 0 else 1.0
    down_w = int(orig_w / factor)
    down_h = int(orig_h / factor)
    logger.info(f"[降采样] 预设模式目标尺寸: {down_w} x {down_h}")

    if use_preset:
        # ========== 预设模式：手动降采样 + 84色调色板 ==========
        small_rgb = rgb_img.resize((down_w, down_h), Image.NEAREST)
        small_a = a.resize((down_w, down_h), Image.NEAREST)

        preset_full = get_preset_palette(normalized=False)  # (84, 3) 0-255
        logger.info(f"[预设模式] 完整调色板颜色数: {len(preset_full)}")
        target_colors = min(max_colors, len(preset_full))

        if target_colors >= len(preset_full):
            selected_colors = preset_full
            logger.info("[预设模式] 直接使用完整84色")
        else:
            # K-Means 聚类 + 最近邻映射到原始84色
            preset_norm = np.array(preset_full) / 255.0
            kmeans = KMeans(n_clusters=target_colors, random_state=42, n_init="auto")
            kmeans.fit(preset_norm)
            centers = kmeans.cluster_centers_
            selected_colors = []
            for c in centers:
                dist = np.linalg.norm(preset_norm - c, axis=1)
                idx = np.argmin(dist)
                selected_colors.append(preset_full[idx])
            logger.info(
                f"[预设模式] K-Means 聚类完成，缩减至 {len(selected_colors)} 色"
            )

        palette = np.array(selected_colors)  # (M, 3) 0-255

        # 颜色映射
        small_rgb_arr = np.array(small_rgb)
        h, w, _ = small_rgb_arr.shape
        flat_rgb = small_rgb_arr.reshape(-1, 3)
        distances = np.linalg.norm(
            flat_rgb[:, np.newaxis, :] - palette[np.newaxis, :, :], axis=2
        )
        indices = np.argmin(distances, axis=1)
        quantized_flat = palette[indices]
        quantized_rgb = quantized_flat.reshape(h, w, 3).astype(np.uint8)

        pixel_rgb_img = Image.fromarray(quantized_rgb)
        color_palette = palette.tolist()
        pixel_img = Image.merge("RGBA", (*pixel_rgb_img.split(), small_a))

    else:
        # ========== 自定义模式：使用 Pyxelate ==========
        max_colors = clamp_color_count(max_colors)
        rgb_array = np.array(rgb_img)
        pyx = Pyx(
            factor=int(round(factor)),
            palette=max_colors,
            dither="none",
            depth=1,
            alpha=0,
        )
        logger.info("[Pyxelate] 开始 fit...")
        pyx.fit(rgb_array)
        logger.info("[Pyxelate] 开始 transform...")
        pixel_rgb_array = pyx.transform(rgb_array)
        pixel_rgb_img = Image.fromarray(pixel_rgb_array.astype(np.uint8))
        color_palette = pyx.colors.reshape(-1, 3).tolist()

        # 以 Pyxelate 输出尺寸为准，调整 Alpha 通道
        out_w, out_h = pixel_rgb_img.size
        logger.info(f"[Pyxelate 输出尺寸] {out_w} x {out_h}")
        small_a = a.resize((out_w, out_h), Image.NEAREST)
        pixel_img = Image.merge("RGBA", (*pixel_rgb_img.split(), small_a))

    logger.info(f"[RGBA 像素图尺寸] {pixel_img.width} x {pixel_img.height}")

    # 6. 居中放置到 256x256 画布
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    paste_x = (256 - pixel_img.width) // 2
    paste_y = (256 - pixel_img.height) // 2
    canvas.paste(pixel_img, (paste_x, paste_y), pixel_img)
    logger.info(f"[居中放置] 粘贴位置: ({paste_x}, {paste_y})")

    # 7. 生成颜色索引矩阵 (256x256)
    color_index_matrix = np.full((256, 256), -1, dtype=np.int16)
    palette_array = np.array(color_palette)
    canvas_arr = np.array(canvas)
    alpha_ch = canvas_arr[:, :, 3]
    rgb_ch = canvas_arr[:, :, :3]
    mask = alpha_ch > 0
    if mask.any():
        flat_rgb = rgb_ch[mask].reshape(-1, 3)
        dist = np.linalg.norm(
            flat_rgb[:, np.newaxis, :] - palette_array[np.newaxis, :, :], axis=2
        )
        inds = np.argmin(dist, axis=1)
        y_coords, x_coords = np.where(mask)
        color_index_matrix[y_coords, x_coords] = inds
    logger.info(f"[颜色索引矩阵] 非透明像素数: {np.sum(mask)}")

    # 8. 可选保存
    if output_color_data_path:
        np.savez_compressed(
            output_color_data_path,
            pixel_data=canvas_arr,
            color_palette=palette_array,
            color_index_matrix=color_index_matrix,
            pixel_size=pixel_size,
            max_colors=max_colors,
            use_preset=use_preset,
        )
        logger.info(f"[色彩数据已保存] {output_color_data_path}")

    logger.info("=" * 70)
    return canvas, color_palette, color_index_matrix


def pixelate_image_simple(
    image_path: str, pixel_size: int, max_colors: int, use_preset: bool = False
):
    """pixelate_image_pyxelate 的简易包装"""
    return pixelate_image_pyxelate(
        image_path, pixel_size, max_colors, use_preset=use_preset
    )
