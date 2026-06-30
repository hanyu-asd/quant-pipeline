#!/usr/bin/env python3
"""
统一日志模块
支持日志级别控制: DEBUG / INFO / WARNING / ERROR
"""
import sys
from datetime import datetime

# 全局日志级别（可通过 set_log_level 修改）
LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
CURRENT_LEVEL = "INFO"   # 默认 INFO


def set_log_level(level):
    """设置日志级别（INFO / DEBUG / WARNING / ERROR）"""
    global CURRENT_LEVEL
    if level in LOG_LEVELS:
        CURRENT_LEVEL = level
        log("INFO", f"日志级别已设置为: {level}")


def log(level, message):
    if LOG_LEVELS.get(level, 1) < LOG_LEVELS.get(CURRENT_LEVEL, 1):
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix_map = {
        "DEBUG": "🔍",
        "INFO": "📊",
        "WARNING": "⚠️",
        "ERROR": "❌"
    }
    prefix = prefix_map.get(level, "📊")
    output = f"{prefix} [{timestamp}] {message}"
    if level in ("ERROR", "WARNING"):
        print(output, file=sys.stderr)
    else:
        print(output)