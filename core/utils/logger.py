"""
统一日志管理模块 v2.2.0
提供基于 logging 的日志系统，支持文件轮转与控制台输出。
日志文件统一存放在项目根目录下的 logs/ 文件夹中。

依赖：
    core.utils.resource.get_project_root  # 获取项目根目录
    logging 标准库
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from core.utils.resource import get_project_root


def get_logs_dir() -> str:
    """
    获取日志文件夹路径（项目根目录下的 logs 目录）。
    自动创建目录（如果不存在）。
    """
    logs_dir = os.path.join(get_project_root(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def setup_logger(name: str, file_name: str = None) -> logging.Logger:
    """
    创建并配置一个 logger 实例。

    Args:
        name: logger 名称（通常用模块名，如 "MainWindow"）
        file_name: 日志文件名（不含扩展名），默认为 name

    Returns:
        配置好的 logging.Logger 实例，已添加文件 Handler 和控制台 Handler
    """
    if file_name is None:
        file_name = name

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 文件 handler（带轮转，单文件最大 5 MB，保留 3 个备份）
    log_file = os.path.join(get_logs_dir(), f"{file_name}.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    # 控制台 handler（仅输出 INFO 及以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger，自动调用 setup_logger 完成配置"""
    return setup_logger(name)
