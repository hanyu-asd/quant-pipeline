#!/usr/bin/env python3
"""
月度准确性汇总报告
"""
import json
import os
from datetime import datetime, timedelta

ACCURACY_LOG_FILE = "shared/accuracy_log.json"


def load_log():
    if not os.path.exists(ACCURACY_LOG_FILE):
        return []
    with open(ACCURACY_LOG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_report():
    logs = load_log()
    if not logs:
        print("无数据")
        return

    # 过滤最近30天
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    recent = [l for l in logs if l['date'] >= cutoff]

    total = len(recent)
    if total == 0:
        print("本月无推荐")
        return

    # 统计各项指标
    hit_buy = sum(1 for l in recent if l.get('next_open') and l['buy_price'] * 0.98 <= l['next_open'] <= l['buy_price'] * 1.02)
    hit_stop = sum(1 for l in recent if l.get('hit_stop_loss'))
    hit_profit = sum(1 for l in recent if l.get('hit_take_profit'))

    print(f"=== 月度准确性报告 ({cutoff} 至今) ===")
    print(f"总推荐: {total}")
    print(f"买入触发率: {hit_buy/total*100:.1f}%")
    print(f"止损触发率: {hit_stop/total*100:.1f}%")
    print(f"止盈触发率: {hit_profit/total*100:.1f}%")


if __name__ == "__main__":
    generate_report()