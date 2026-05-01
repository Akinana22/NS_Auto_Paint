"""
统一资源路径管理模块 v2.2.0
负责获取所有静态资源的绝对路径，兼容开发环境与 PyInstaller 打包环境。
"""

import sys
import os


# --------打包用--------
def resource_path(relative_path: str) -> str:
    """
    获取静态资源文件的绝对路径。
    兼容 PyInstaller 打包环境（--onedir 模式下资源位于 sys._MEIPASS）。
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 打包后：资源位于 sys._MEIPASS 下
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # 开发环境：本文件位于 core/utils/ 下，向上三级为项目根目录
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(base_dir, relative_path)


def get_project_root() -> str:
    """
    获取项目根目录的绝对路径。
    供需要拼接运行时输出目录（如 logs/）的模块使用。
    """
    if hasattr(sys, "_MEIPASS"):
        # 打包后：根目录为可执行文件所在目录
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )


# --------开发用--------
# def resource_path(relative_path: str) -> str:
#     if hasattr(sys, "_MEIPASS"):
#         return os.path.join(sys._MEIPASS, relative_path)
#     # 开发环境：core/utils/resource.py -> 上两级为 core，再上一级为项目根目录
#     base_dir = os.path.dirname(
#         os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     )
#     return os.path.join(base_dir, relative_path)


# def get_project_root() -> str:
#     if hasattr(sys, "_MEIPASS"):
#         return os.path.dirname(sys.executable)
#     else:
#         # 同样返回项目根目录
#         return os.path.dirname(
#             os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#         )
