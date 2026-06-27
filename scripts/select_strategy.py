#!/usr/bin/env python3
"""
自动判断市场状态并选择策略
使用 yfinance 获取指数数据（更稳定）
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

def get_index_data(symbol, days=90):
    """使用 yfinance 获取指数数据"""
    try:
        ticker = yf.Ticker(symbol)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ticker.history(start=start_date, end=end_date)
        if df.empty:
            return None
        return df['Close'].values
    except Exception as e:
        print(f"获取 {symbol} 数据失败: {e}")
        return None

def main():
    # 获取指数数据
    sh = get_index_data("000001.SS")   # 上证指数
    cy = get_index_data("399006.SZ")   # 创业板指
    
    # 如果上证数据获取失败，使用默认策略
    if sh is None or len(sh) < 60:
        print("⚠️ 无法获取指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return
    
    # 计算均线
    ma20_sh = np.mean(sh[-20:])
    ma60_sh = np.mean(sh[-60:])
    current_sh = sh[-1]
    
    # 趋势判断
    if current_sh > ma20_sh and ma20_sh > ma60_sh:
        trend = "up"
        trend_desc = "上升趋势"
    elif current_sh < ma20_sh and ma20_sh < ma60_sh:
        trend = "down"
        trend_desc = "下降趋势"
    else:
        trend = "sideways"
        trend_desc = "震荡"
    
    # 科技股相对强弱
    tech_premium = 0
    if cy is not None and len(cy) >= 20 and len(sh) >= 20:
        ret_cy = (cy[-1] / cy[-20] - 1) * 100
        ret_sh = (sh[-1] / sh[-20] - 1) * 100
        tech_premium = ret_cy - ret_sh
    
    # 选择策略
    if trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = "上升趋势 + 科技股强势"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = "上升趋势"
    elif trend == "down":
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（等待超跌反弹）"
    else:
        strategy = "rsi_reversion_v1"
        reason = "震荡（均值回归）"
    
    # 输出结果
    print("=" * 60)
    print(f"📊 市场状态分析")
    print("=" * 60)
    print(f"  上证指数: {current_sh:.2f}")
    print(f"  MA20: {ma20_sh:.2f}")
    print(f"  MA60: {ma60_sh:.2f}")
    print(f"  趋势: {trend_desc}")
    print(f"  科技股溢价（创业板-上证）: {tech_premium:.2f}%")
    print(f"  选择策略: {strategy}")
    print(f"  原因: {reason}")
    print("=" * 60)
    
    # 写入结果文件
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

if __name__ == "__main__":
    main()