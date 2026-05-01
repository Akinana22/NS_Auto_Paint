"""
断点管理器 v2.2.0
仅保存脚本行号和修改后的绘图矩阵，不保留任何游戏内 UI 状态。
恢复时根据用户选择：继续执行当前脚本，或用修改后的矩阵重新生成脚本。
"""

import json
import os
from typing import Optional, List, Dict, Any
import numpy as np

from core.utils.logger import get_logger
from core.utils.resource import get_project_root


class CheckpointManager:
    def __init__(self):
        self.logger = get_logger("CheckpointManager")
        self.scripts_dir = os.path.join(get_project_root(), "scripts")
        os.makedirs(self.scripts_dir, exist_ok=True)
        self.checkpoint_path = os.path.join(self.scripts_dir, "checkpoint.json")

    def save(
        self,
        script_path: str,
        current_line: int,
        resume_matrix: np.ndarray,  # 已标记已绘制像素为 -1 的矩阵
        palette_rgb: List[List[int]],
        use_preset: bool,
        pixel_size: int,
        brush_type: str,
        brush_size: int,
        press_data: Optional[List[Dict[str, int]]] = None,
    ) -> bool:
        """
        保存断点：只记录脚本行号、修改后的矩阵和必要的绘图参数，
        不保存画笔位置、调色盘光标等游戏内状态。
        """
        cp = {
            "version": "2.2.0",
            "script_path": script_path,
            "current_line": current_line,
            "resume_matrix": (
                resume_matrix.tolist() if resume_matrix is not None else None
            ),
            "palette_rgb": palette_rgb,
            "use_preset": use_preset,
            "pixel_size": pixel_size,
            "brush_type": brush_type,
            "brush_size": brush_size,
            "press_data": press_data,
        }
        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(cp, f, ensure_ascii=False, indent=2)
            self.logger.info("断点已保存")
            return True
        except Exception as e:
            self.logger.error(f"保存断点失败: {e}")
            return False

    def load(self) -> Optional[dict]:
        """加载断点，返回字典或 None。若包含 resume_matrix 则转为 numpy 数组。"""
        if not os.path.exists(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 将矩阵列表转换回 numpy 数组
            if data.get("resume_matrix") is not None:
                try:
                    data["resume_matrix"] = np.array(
                        data["resume_matrix"], dtype=np.int16
                    )
                except Exception:
                    self.logger.warning("断点中的矩阵数据无效")
                    data["resume_matrix"] = None
            return data
        except Exception as e:
            self.logger.error(f"加载断点失败: {e}")
            return None

    def has_checkpoint(self) -> bool:
        return os.path.exists(self.checkpoint_path)

    def delete(self) -> bool:
        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)
            self.logger.info("断点已删除")
        return True
