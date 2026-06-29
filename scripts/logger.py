#!/usr/bin/env python3
"""
统一日志模块
提供 INFO / WARNING / ERROR 级别的日志输出，带时间戳和图标
"""
import sys
from datetime import datetime

LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
CURRENT_LEVEL = "INFO"

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