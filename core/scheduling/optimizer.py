"""
调度优化器 v2.2.0
负责生成多种候选调度方案（固定网格、四叉树不同阈值），
使用蛇形扫描路径评估各方案的耗时，并选出最优方案。
画笔当前位置会影响同区块内下一个颜色的扫描方向，以减少无效移动。
支持通过 timing 参数传入冻结的快照，未传则回退 TimingConfig 类属性。
"""

from typing import List, Tuple, Optional
import numpy as np

from core.models.drawing import LeafBlock, Schedule
from core.scheduling.quadtree import build_quadtree
from core.scheduling.timing_config import TimingConfig, TimingSnapshot


class SchedulingOptimizer:
    """调度方案生成与成本评估器"""

    @staticmethod
    def _snake_sort_points(points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        简单蛇形排序：按 y 升序，偶数行 x 升序，奇数行 x 降序。
        用于没有上下文时的初始排序（如评估时第一个颜色）。
        """
        if not points:
            return []
        grouped = {}
        for x, y in points:
            grouped.setdefault(y, []).append(x)
        sorted_pts = []
        for y in sorted(grouped.keys()):
            xs = sorted(grouped[y])
            if y % 2 == 0:
                sorted_pts.extend([(x, y) for x in xs])
            else:
                sorted_pts.extend([(x, y) for x in reversed(xs)])
        return sorted_pts

    def sort_points_adaptive(
        self,
        points: List[Tuple[int, int]],
        cur_x: int,
        cur_y: int,
    ) -> List[Tuple[int, int]]:
        """
        根据当前画笔位置 (cur_x, cur_y) 自适应排序点。
        若画笔靠近底部则从下往上扫描；否则从上往下。
        行内来回方向保持蛇形特点。
        返回排序后的点列表。
        """
        if not points:
            return []

        rows = {}
        for x, y in points:
            rows.setdefault(y, []).append(x)
        sorted_y = sorted(rows.keys())
        if not sorted_y:
            return []

        min_y, max_y = sorted_y[0], sorted_y[-1]

        if cur_y >= (min_y + max_y) / 2:  # 靠近底部，从下往上
            y_order = sorted(sorted_y, reverse=True)
        else:  # 从上往下
            y_order = sorted_y

        result = []
        flip_x = False
        for y in y_order:
            xs = sorted(rows[y])
            if flip_x:
                xs.reverse()
            for x in xs:
                result.append((x, y))
            flip_x = not flip_x
        return result

    def generate_candidate_schedules(
        self,
        grid_matrix: np.ndarray,
        brush_type: Optional[str] = None,
        brush_size: Optional[int] = None,
    ) -> List[Tuple[Schedule, str]]:
        schedules = []
        grid_h, grid_w = grid_matrix.shape

        possible_k = [1, 2, 4, 8, 16, 32, 64]
        for k in possible_k:
            if grid_w % k != 0 or grid_h % k != 0:
                continue
            if k > grid_w or k > grid_h:
                continue
            block_w = grid_w // k
            block_h = grid_h // k
            schedule = []
            for by in range(k):
                for bx in range(k):
                    x_start = bx * block_w
                    y_start = by * block_h
                    sub = grid_matrix[
                        y_start : y_start + block_h, x_start : x_start + block_w
                    ]
                    color_points = {}
                    for gy in range(block_h):
                        for gx in range(block_w):
                            idx = int(sub[gy, gx])
                            if idx >= 0:
                                color_points.setdefault(idx, []).append(
                                    (x_start + gx, y_start + gy)
                                )
                    if color_points:
                        block = LeafBlock(
                            x=x_start,
                            y=y_start,
                            w=block_w,
                            h=block_h,
                            color_points=color_points,
                        )
                        sorted_colors = sorted(
                            color_points.keys(),
                            key=lambda c: len(color_points[c]),
                            reverse=True,
                        )
                        schedule.append((block, sorted_colors))
            schedules.append((schedule, f"固定网格 {k}x{k}"))

        for threshold in [2, 3, 5, 8, 12]:
            blocks = build_quadtree(grid_matrix, color_threshold=threshold)
            schedule = []
            for block in blocks:
                if block.color_points:
                    sorted_colors = sorted(
                        block.color_points.keys(),
                        key=lambda c: len(block.color_points[c]),
                        reverse=True,
                    )
                    schedule.append((block, sorted_colors))
            schedules.append((schedule, f"四叉树 阈值{threshold}"))

        return schedules

    def estimate_schedule_cost(
        self,
        schedule: Schedule,
        brush_type: Optional[str],
        brush_size: Optional[int],
        use_preset: bool,
        grid_w: int,
        grid_h: int,
        palette: List[List[int]],  # 调色板 RGB 列表
        press_data: Optional[List[dict]] = None,
        timing: Optional[TimingSnapshot] = None,
    ) -> float:
        """
        精确计算调度方案的总耗时（毫秒）。
        每个颜色切换的耗时基于实际 BFS 路径长度或 HSV 步数。
        """
        if not schedule:
            return float("inf")

        cfg = timing or TimingConfig

        cur_gx, cur_gy = grid_w // 2, grid_h // 2
        total_ms = 0.0

        # 调色盘初始光标
        if use_preset:
            cur_row, cur_col = 7, 1  # R7C1
        else:
            cur_h, cur_s, cur_b = 0, 0, 0  # 初始 HSV

        # 画笔切换耗时（直接使用指令生成器）
        if brush_type is not None and brush_size is not None:
            from core.scheduling.brush import generate_brush_switch_commands

            brush_cmds = generate_brush_switch_commands(
                brush_type, brush_size, timing=timing
            )
            total_ms += sum(cmd[1] for cmd in brush_cmds)

        # 引入调色盘寻路所需函数和映射表
        from core.scheduling.palette import _bfs_path, _PRESET_COORD_MAP

        for block, color_order in schedule:
            if not color_order:
                continue

            # ---------- 第一个颜色 ----------
            first_color = color_order[0]
            pts = block.color_points.get(first_color, [])
            if pts:
                # ---- 颜色切换 ----
                target_rgb = palette[first_color]
                target_hex = (
                    f"#{target_rgb[0]:02X}{target_rgb[1]:02X}{target_rgb[2]:02X}"
                )
                if use_preset:
                    # 基础：Y 长按 + Y 普通
                    total_ms += (
                        cfg.key_interval_ms + cfg.wait_interval_ms + cfg.key_interval_ms
                    )
                    target_row, target_col = _PRESET_COORD_MAP[target_hex]
                    path_len = len(_bfs_path(cur_row, cur_col, target_row, target_col))
                    total_ms += path_len * cfg.key_interval_ms
                    total_ms += cfg.key_interval_ms  # A 确认
                    total_ms += cfg.wait_interval_ms  # 退出等待
                    cur_row, cur_col = target_row, target_col
                else:
                    # 基础：Y 长按 + Y 普通 + R 长按
                    total_ms += (
                        cfg.key_interval_ms
                        + cfg.wait_interval_ms  # Y 长按
                        + cfg.key_interval_ms  # Y 普通
                        + cfg.key_interval_ms
                        + cfg.wait_interval_ms  # R 长按
                    )
                    if press_data and first_color < len(press_data):
                        pd = press_data[first_color]
                        target_h = pd["h"]
                        target_s = pd["s"]
                        target_b = pd["b"]
                    else:
                        target_h, target_s, target_b = 0, 0, 0
                    h_steps = abs(target_h - cur_h)
                    s_steps = abs(target_s - cur_s)
                    b_steps = abs(target_b - cur_b)
                    total_ms += h_steps * cfg.key_interval_ms
                    total_ms += (s_steps + b_steps) * cfg.sv_key_interval_ms
                    total_ms += cfg.key_interval_ms  # A 确认
                    total_ms += cfg.wait_interval_ms  # 退出等待
                    cur_h, cur_s, cur_b = target_h, target_s, target_b

                # ---- 移动到第一个点 ----
                sorted_pts = SchedulingOptimizer._snake_sort_points(pts)
                px, py = sorted_pts[0]
                steps = abs(cur_gx - px) + abs(cur_gy - py)
                total_ms += self._move_to_ms(
                    steps, brush_type, brush_size, timing=timing
                )
                cur_gx, cur_gy = px, py

                # ---- 绘制该颜色所有点 ----
                for gx, gy in sorted_pts[1:]:
                    step = abs(cur_gx - gx) + abs(cur_gy - gy)
                    total_ms += self._move_to_ms(
                        step, brush_type, brush_size, timing=timing
                    )
                    total_ms += cfg.draw_ms
                    cur_gx, cur_gy = gx, gy
                total_ms += cfg.draw_ms  # 第一个点也要绘制

            # ---------- 后续颜色 ----------
            for color_idx in color_order[1:]:
                pts = block.color_points.get(color_idx, [])
                if not pts:
                    continue

                # ---- 颜色切换 ----
                target_rgb = palette[color_idx]
                target_hex = (
                    f"#{target_rgb[0]:02X}{target_rgb[1]:02X}{target_rgb[2]:02X}"
                )
                if use_preset:
                    total_ms += (
                        cfg.key_interval_ms + cfg.wait_interval_ms + cfg.key_interval_ms
                    )
                    target_row, target_col = _PRESET_COORD_MAP[target_hex]
                    path_len = len(_bfs_path(cur_row, cur_col, target_row, target_col))
                    total_ms += path_len * cfg.key_interval_ms
                    total_ms += cfg.key_interval_ms
                    total_ms += cfg.wait_interval_ms
                    cur_row, cur_col = target_row, target_col
                else:
                    total_ms += (
                        cfg.key_interval_ms
                        + cfg.wait_interval_ms
                        + cfg.key_interval_ms
                        + cfg.key_interval_ms
                        + cfg.wait_interval_ms
                    )
                    if press_data and color_idx < len(press_data):
                        pd = press_data[color_idx]
                        target_h = pd["h"]
                        target_s = pd["s"]
                        target_b = pd["b"]
                    else:
                        target_h, target_s, target_b = 0, 0, 0
                    h_steps = abs(target_h - cur_h)
                    s_steps = abs(target_s - cur_s)
                    b_steps = abs(target_b - cur_b)
                    total_ms += h_steps * cfg.key_interval_ms
                    total_ms += (s_steps + b_steps) * cfg.sv_key_interval_ms
                    total_ms += cfg.key_interval_ms
                    total_ms += cfg.wait_interval_ms
                    cur_h, cur_s, cur_b = target_h, target_s, target_b

                # ---- 绘制该颜色所有点 ----
                sorted_pts = self.sort_points_adaptive(pts, cur_gx, cur_gy)
                for gx, gy in sorted_pts:
                    step = abs(cur_gx - gx) + abs(cur_gy - gy)
                    total_ms += self._move_to_ms(
                        step, brush_type, brush_size, timing=timing
                    )
                    total_ms += cfg.draw_ms
                    cur_gx, cur_gy = gx, gy

        return total_ms

    def _move_to_ms(
        self,
        steps: int,
        brush_type: Optional[str],
        brush_size: Optional[int],
        timing: Optional[TimingSnapshot] = None,
    ) -> float:
        """将网格移动步数转换为耗时（毫秒）"""
        cfg = timing or TimingConfig
        if brush_type == "smooth" and brush_size and brush_size > 1:
            actual_move = steps * brush_size
        else:
            actual_move = steps
        return actual_move * cfg.key_interval_ms

    def find_best_schedule(
        self,
        grid_matrix: np.ndarray,
        brush_type: Optional[str],
        brush_size: Optional[int],
        use_preset: bool,
        grid_w: int,
        grid_h: int,
        palette: List[List[int]],
        press_data: Optional[List[dict]] = None,
        timing: Optional[TimingSnapshot] = None,
    ) -> Tuple[Optional[Schedule], str, List[str]]:
        candidates = self.generate_candidate_schedules(
            grid_matrix, brush_type, brush_size
        )
        best_schedule = None
        best_cost = float("inf")
        best_desc = ""
        logs = []

        for schedule, desc in candidates:
            cost = self.estimate_schedule_cost(
                schedule,
                brush_type,
                brush_size,
                use_preset,
                grid_w,
                grid_h,
                palette=palette,
                press_data=press_data,
                timing=timing,
            )
            logs.append(f"{desc}: {cost/1000:.1f} 秒")
            if cost < best_cost:
                best_cost = cost
                best_schedule = schedule
                best_desc = desc

        return best_schedule, best_desc, logs
