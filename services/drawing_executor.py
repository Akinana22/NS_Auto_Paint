"""
绘图执行器 v2.2.0
面向 UI 的顶层绘图服务，负责将像素画转换为脚本并执行。
整合脚本生成、脚本执行、断点管理三大模块，通过信号与 UI 交互。

断点仅记录脚本行号和已标记绘制点的矩阵，不保存任何游戏内 UI 状态。
恢复方式由用户选择：继续当前脚本，或用修改后的矩阵重新生成脚本。

使用方式：
    from services.drawing_executor import DrawingExecutor
    executor = DrawingExecutor(controller)
    executor.log_signal.connect(ui_log_handler)
    executor.progress_signal.connect(ui_progress_handler)
    executor.start_drawing(matrix, palette, ...)
"""

import os
import time
from typing import Optional, List, Tuple

import numpy as np
from PySide6.QtCore import QObject, Signal

from core.hal.controller import EasyConController
from core.utils.logger import get_logger
from core.utils.resource import get_project_root
from core.models.drawing import Palette, Schedule
from core.scripting.drawing_script_generator import generate_drawing_script
from core.scripting.checkpoint_manager import CheckpointManager
from core.scheduling.optimizer import SchedulingOptimizer
from services.script_executor import ScriptExecutor


class DrawingExecutor(QObject):
    """绘图执行器，连接脚本生成与执行，并管理断点"""

    log_signal = Signal(str)  # 日志消息
    progress_signal = Signal(int)  # 当前执行进度（0-100 百分比）
    finished_signal = Signal()  # 绘图正常结束
    error_signal = Signal(str)  # 绘图错误
    state_changed = Signal(str)  # 状态变更（"idle", "running", "stopped", "error"）

    def __init__(self, controller: EasyConController):
        super().__init__()
        self.controller = controller
        self.logger = get_logger("DrawingExecutor")
        self._checkpoint_mgr = CheckpointManager()
        self._executor = ScriptExecutor(controller)
        self._stop_flag = False
        self._state = "idle"  # idle, running, stopped, error

        # 当前绘图上下文（用于脚本生成和断点保存）
        self._current_script_path: Optional[str] = None
        self._current_script: str = ""
        self._current_schedule: Optional[Schedule] = None
        self._current_grid_w = 0
        self._current_grid_h = 0
        self._brush_type: Optional[str] = None
        self._brush_size: Optional[int] = None
        self._use_preset = True
        self._palette: Palette = []
        self._press_data: Optional[List[dict]] = None

        # 保存原始矩阵和参数，用于停止时标记已绘制像素
        self._saved_matrix: Optional[np.ndarray] = None
        self._saved_pixel_size: int = 0

        # 连接底层执行器信号
        self._executor.log_signal.connect(self.log_signal)
        self._executor.progress_signal.connect(self._on_executor_progress)
        self._executor.finished_signal.connect(self._on_executor_finished)
        self._executor.error_signal.connect(self._on_executor_error)

    # ========== 公开接口 ==========
    def start_drawing(
        self,
        color_index_matrix,
        palette: Palette,
        pixel_size: int,
        use_preset: bool,
        brush_type: Optional[str] = None,
        brush_size: Optional[int] = None,
        press_data: Optional[List[dict]] = None,
    ):
        """
        开始新的绘图任务。
        调用后立即返回，绘图在后台线程中执行。
        """
        if self._state == "running":
            self.log_signal.emit("[警告] 已有绘图任务正在执行")
            return

        self._stop_flag = False
        self._set_state("running")

        # 保存参数，以便停止时使用
        self._brush_type = brush_type
        self._brush_size = brush_size
        self._use_preset = use_preset
        self._palette = palette
        self._press_data = press_data
        self._saved_matrix = np.asarray(color_index_matrix, dtype=np.int16)  # 原始矩阵
        self._saved_pixel_size = pixel_size

        # 生成脚本
        try:
            self.log_signal.emit("[脚本] 正在生成绘图脚本...")
            script, schedule, grid_w, grid_h = generate_drawing_script(
                color_index_matrix,
                palette,
                pixel_size,
                use_preset,
                brush_type,
                brush_size,
                press_data,
            )
            self._current_script = script
            self._current_schedule = schedule
            self._current_grid_w = grid_w
            self._current_grid_h = grid_h
        except Exception as e:
            self.logger.error(f"脚本生成失败: {e}")
            self._set_state("error")
            self.error_signal.emit(f"脚本生成失败: {e}")
            return

        # 保存脚本文件
        scripts_dir = os.path.join(get_project_root(), "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        script_filename = f"drawing_{timestamp}.txt"
        self._current_script_path = os.path.join(scripts_dir, script_filename)
        try:
            with open(self._current_script_path, "w", encoding="utf-8") as f:
                f.write(script)
            self.log_signal.emit(f"[脚本] 已保存至 {script_filename}")
        except Exception as e:
            self.logger.error(f"保存脚本文件失败: {e}")
            self.log_signal.emit(f"[警告] 无法保存脚本文件: {e}")

        # 清除旧断点
        self._checkpoint_mgr.delete()

        # 执行脚本
        self.log_signal.emit("[执行] 开始绘图...")
        self._executor.execute(script, start_line=0)

    def stop_drawing(self):
        """停止绘图（安全等待后保存断点）"""
        if self._state != "running":
            return

        self._stop_flag = True
        self._executor.stop()  # 内部会等待 40ms 安全延迟
        self.log_signal.emit("[用户] 停止绘图请求")

        # 保存断点：记录行号和修改后的矩阵
        self._save_checkpoint_and_matrix()
        self._set_state("stopped")

    def resume_continue(self) -> bool:
        """
        从暂停恢复：直接从脚本的断点行继续执行。
        假设游戏内工具/画笔/调色盘状态与暂停时一致。
        """
        cp = self._checkpoint_mgr.load()
        if not cp:
            self.log_signal.emit("[断点] 未找到可恢复的断点")
            return False

        script_path = cp.get("script_path")
        if not script_path or not os.path.exists(script_path):
            self.log_signal.emit("[断点] 脚本文件丢失，无法恢复")
            return False

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = f.read()
        except Exception as e:
            self.log_signal.emit(f"[断点] 读取脚本文件失败: {e}")
            return False

        # 恢复上下文
        self._current_script_path = script_path
        self._current_script = script
        self._brush_type = cp.get("brush_type")
        self._brush_size = cp.get("brush_size")
        self._use_preset = cp.get("use_preset", True)

        start_line = cp["current_line"]
        self.log_signal.emit(f"[恢复] 从第 {start_line+1} 行继续执行...")
        self._stop_flag = False
        self._set_state("running")
        self._executor.execute(script, start_line=start_line)
        return True

    def resume_new_drawing(self) -> bool:
        """
        游戏内重新开始绘画：使用修改后的矩阵（已绘制点标记为空）重新生成脚本并执行。
        适用于用户已退出绘画并保存画布，重新进入绘画模式的情景。
        """
        cp = self._checkpoint_mgr.load()
        if not cp:
            self.log_signal.emit("[断点] 未找到可恢复的断点")
            return False

        resume_matrix = cp.get("resume_matrix")
        palette = cp.get("palette_rgb")
        if resume_matrix is None or palette is None:
            self.log_signal.emit("[断点] 缺少恢复所需的矩阵或调色板数据")
            return False

        # 获取其他参数，若不存在则使用默认
        use_preset = cp.get("use_preset", True)
        pixel_size = cp.get("pixel_size", 64)
        brush_type = cp.get("brush_type")
        brush_size = cp.get("brush_size")
        press_data = cp.get("press_data")

        self.log_signal.emit("[恢复] 使用修改后的矩阵重新生成脚本...")
        # 保留断点文件，因为 start_drawing 内部会调用 delete 吗？不会，但为了安全，我们先删除旧断点再开始新任务
        self._checkpoint_mgr.delete()
        self.start_drawing(
            resume_matrix,
            palette,
            pixel_size,
            use_preset,
            brush_type,
            brush_size,
            press_data,
        )
        return True

    def is_running(self) -> bool:
        return self._state == "running"

    # ========== 内部方法 ==========
    def _count_completed_pixels(self, script: str, stop_line: int) -> int:
        """统计脚本前 stop_line 行中 'A 100' 指令的数量，代表已绘制的像素数"""
        lines = script.splitlines()
        count = 0
        for i in range(min(stop_line + 1, len(lines))):
            line = lines[i].strip().upper()
            # 检测绘制指令：A 100（顺滑画笔或像素画笔都是 A 100）
            if line.startswith("A") and "100" in line:
                count += 1
        return count

    def _mark_matrix_pixels(
        self,
        schedule: Schedule,
        grid_w: int,
        grid_h: int,
        brush_type: Optional[str],
        brush_size: Optional[int],
        matrix: np.ndarray,
        pixel_count: int,
    ) -> np.ndarray:
        """
        按照与脚本生成完全一致的蛇形扫描顺序，将前 pixel_count 个像素在矩阵中标记为 -1。
        返回修改后的矩阵副本。
        """
        marked = np.copy(matrix)
        grid_matrix = (
            marked  # 对于蛇形扫描，我们需要的是网格矩阵，但这里 matrix 已经是网格矩阵
        )
        # 确定网格矩阵
        if brush_type is not None and brush_size is not None:
            step = brush_size
            gh = matrix.shape[0] // step
            gw = matrix.shape[1] // step
            grid = matrix[::step, ::step]
        else:
            step = 1
            gh = matrix.shape[0]
            gw = matrix.shape[1]
            grid = matrix

        opt = SchedulingOptimizer()
        # 假设画笔起始位置为网格中心
        cur_x, cur_y = gw // 2, gh // 2
        target_count = pixel_count
        counted = 0

        for block, color_order in schedule:
            if counted >= target_count:
                break
            # 第一个颜色简单蛇形
            first_color = color_order[0]
            pts = block.color_points.get(first_color, [])
            if pts:
                sorted_pts = opt._snake_sort_points(pts)
                for px, py in sorted_pts:
                    if counted >= target_count:
                        break
                    # 标记为 -1：需要反向映射到原始矩阵坐标
                    actual_x = px * step if step else px
                    actual_y = py * step if step else py
                    # 对于网格坐标，我们直接标记网格点即可
                    marked[py, px] = -1
                    counted += 1

            # 后续颜色自适应蛇形
            for ci in range(1, len(color_order)):
                if counted >= target_count:
                    break
                c = color_order[ci]
                pts = block.color_points.get(c, [])
                if not pts:
                    continue
                sorted_pts = opt.sort_points_adaptive(pts, px, py)
                for px, py in sorted_pts:
                    if counted >= target_count:
                        break
                    marked[py, px] = -1
                    counted += 1
        return marked

    def _save_checkpoint_and_matrix(self):
        """停止时计算已绘制像素，生成修改后的矩阵，并保存断点"""
        if not self._current_script_path or not self._current_script:
            return
        if self._saved_matrix is None:
            self.logger.warning("没有保存的矩阵，无法生成断点")
            return

        current_line = self._executor._current_line
        completed_pixels = self._count_completed_pixels(
            self._current_script, current_line
        )
        self.logger.info(f"已绘制像素数: {completed_pixels}")

        # 标记已绘制像素为 -1
        resume_matrix = self._mark_matrix_pixels(
            self._current_schedule,
            self._current_grid_w,
            self._current_grid_h,
            self._brush_type,
            self._brush_size,
            self._saved_matrix,
            completed_pixels,
        )

        # 保存断点（只保存行号、修改后的矩阵、调色板等必要参数）
        self._checkpoint_mgr.save(
            script_path=self._current_script_path,
            current_line=current_line,
            resume_matrix=resume_matrix,
            palette_rgb=self._palette,
            use_preset=self._use_preset,
            pixel_size=self._saved_pixel_size,
            brush_type=self._brush_type or "",
            brush_size=self._brush_size or 0,
            press_data=self._press_data,
        )

    def _set_state(self, state: str):
        self._state = state
        self.state_changed.emit(state)

    # ========== 信号转发 ==========
    def _on_executor_progress(self, line_num: int):
        if self._current_script:
            total_lines = self._current_script.count("\n") + 1
            if total_lines > 0:
                pct = int((line_num + 1) / total_lines * 100)
                self.progress_signal.emit(pct)

    def _on_executor_finished(self):
        self.log_signal.emit("[绘图] 脚本执行完毕")
        self._set_state("idle")
        self.finished_signal.emit()

    def _on_executor_error(self, msg: str):
        self.log_signal.emit(f"[绘图错误] {msg}")
        self._set_state("error")
        self.error_signal.emit(msg)
