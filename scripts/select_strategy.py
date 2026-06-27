#!/usr/bin/env python3
"""
自动判断市场状态并选择策略
用于 weekly-evo.yml 中的策略选择
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

def get_index_data(symbol, days=90):
    """
    获取指数历史数据
    symbol: 000001（上证）, 399006（创业板）
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
    
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=""
        )
        if df.empty:
            return None
        df['date'] = pd.to_datetime(df['日期'])
        df = df.sort_values('date')
        return df['收盘'].values
    except Exception as e:
        print(f"获取 {symbol} 数据失败: {e}")
        return None

def main():
    # 1. 获取指数数据
    sh = get_index_data("000001")   # 上证指数
    cy = get_index_data("399006")   # 创业板指
    
    # 如果上证数据获取失败，使用默认策略
    if sh is None or len(sh) < 60:
        print("⚠️ 无法获取指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return
    
    # 2. 计算均线
    ma20_sh = np.mean(sh[-20:])
    ma60_sh = np.mean(sh[-60:])
    current_sh = sh[-1]
    
    # 3. 趋势判断
    if current_sh > ma20_sh and ma20_sh > ma60_sh:
        trend = "up"
        trend_desc = "上升趋势"
    elif current_sh < ma20_sh and ma20_sh < ma60_sh:
        trend = "down"
        trend_desc = "下降趋势"
    else:
        trend = "sideways"
        trend_desc = "震荡"
    
    # 4. 科技股相对强弱（创业板 vs 上证，近20日涨幅差）
    tech_premium = 0
    if cy is not None and len(cy) >= 20 and len(sh) >= 20:
        ret_cy = (cy[-1] / cy[-20] - 1) * 100
        ret_sh = (sh[-1] / sh[-20] - 1) * 100
        tech_premium = ret_cy - ret_sh
    
    # 5. 选择策略
    # 策略映射：
    #   上升趋势 + 科技股强势（创业板跑赢上证 > 3%）→ trend_pullback_rebound
    #   上升趋势（普通）→ ma_crossover
    #   下降趋势或震荡 → rsi_reversion_v1（均值回归/超跌反弹）
    
    if trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = "上升趋势 + 科技股强势"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = "上升趋势"
    elif trend == "down":
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（等待超跌反弹）"
    else:  # sideways
        strategy = "rsi_reversion_v1"
        reason = "震荡（均值回归）"
    
    # 6. 输出结果
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
    
    # 7. 写入结果文件
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

if __name__ == "__main__":
    main()