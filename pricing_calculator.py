#!/usr/bin/env python3
import yaml
import json
import os
import sys
from datetime import datetime

def load_candidates():
    """从 shared/candidates.json 读取候选股列表"""
    candidates_file = "shared/candidates.json"
    if not os.path.exists(candidates_file):
        print("候选股文件不存在，跳过定价计算")
        return []
    with open(candidates_file, 'r') as f:
        data = json.load(f)
    picks = data.get('picks', [])
    return [item['code'] for item in picks if 'code' in item]

def load_strategy():
    """加载 rsi_reversion 策略"""
    strategy_file = "alphaevo/strategies/builtin/rsi_reversion.yaml"
    if not os.path.exists(strategy_file):
        print("策略文件不存在，跳过定价计算")
        return None
    with open(strategy_file, 'r') as f:
        return yaml.safe_load(f)

def get_stock_price(stock_code):
    """获取股票当前价格（这里使用模拟，实际应调用数据源）"""
    # 实际应调用 daily_stock_analysis 的数据获取模块，或使用腾讯财经 API
    # 这里为演示，返回一个示例价格
    return 10.0

def calculate_pricing(strategy, stock_code):
    """根据策略计算买卖价格"""
    # 这里简化逻辑，实际应完整实现策略的 entry/exit 条件
    # 例如：根据 RSI、MA20、成交量比等计算
    # 这里只是返回示例数据
    return {
        "buy_price": 9.50,
        "stop_loss": 9.00,
        "take_profit": 10.50
    }

def main():
    candidates = load_candidates()
    if not candidates:
        print("没有候选股，定价计算跳过")
        sys.exit(0)
    
    strategy = load_strategy()
    if not strategy:
        sys.exit(1)
    
    # 生成定价报告
    report_lines = ["📊 买卖价格参考（基于 rsi_reversion 策略）", ""]
    for code in candidates:
        pricing = calculate_pricing(strategy, code)
        report_lines.append(f"股票代码: {code}")
        report_lines.append(f"  买入触发价: {pricing['buy_price']:.2f}")
        report_lines.append(f"  止损价: {pricing['stop_loss']:.2f}")
        report_lines.append(f"  止盈价: {pricing['take_profit']:.2f}")
        report_lines.append("")
    
    # 写入文件
    with open("pricing.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("定价报告已生成: pricing.txt")

if __name__ == "__main__":
    main()