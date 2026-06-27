#!/usr/bin/env python3
"""
信号采集模块：技术面、资金面、情绪面
只使用免费、无需注册的数据源：efinance、AkShare
"""

import numpy as np
import pandas as pd


# ============================================================
# 技术面信号（从指数数据计算，无需额外数据源）
# ============================================================

def calculate_momentum_signal(closes, lookback=20):
    """动量信号：近20日涨跌幅"""
    if len(closes) < lookback:
        return 0
    ret = (closes[-1] / closes[-lookback] - 1) * 100
    if ret > 5:
        return 1
    elif ret < -5:
        return -1
    else:
        return 0


def calculate_breadth_signal(closes, lookback=20):
    """市场宽度：价格在MA20上方的比例"""
    if len(closes) < lookback:
        return 50
    ma20 = sum(closes[-lookback:]) / lookback
    above_count = sum(1 for c in closes[-lookback:] if c > ma20)
    return above_count / lookback * 100


def calculate_volatility_signal(closes, lookback=20):
    """波动率信号"""
    if len(closes) < lookback:
        return 'normal'
    returns = [(closes[i] / closes[i-1] - 1) * 100 for i in range(1, len(closes))]
    recent_returns = returns[-lookback:]
    vol = np.std(recent_returns) if len(recent_returns) > 0 else 0
    if vol > 2.5:
        return 'high'
    elif vol < 0.8:
        return 'low'
    else:
        return 'normal'


def aggregate_technical_signals(sh_closes):
    """汇总技术面信号"""
    momentum = calculate_momentum_signal(sh_closes, 20)
    breadth = calculate_breadth_signal(sh_closes, 20)
    volatility = calculate_volatility_signal(sh_closes, 20)
    
    score = 0
    details = []
    if momentum == 1:
        score += 30
        details.append("动量强势 (+30)")
    elif momentum == -1:
        score -= 30
        details.append("动量弱势 (-30)")
    else:
        details.append("动量中性 (0)")
    
    if breadth >= 70:
        score += 20
        details.append(f"宽度强势 ({breadth:.0f}% +20)")
    elif breadth >= 50:
        details.append(f"宽度中性 ({breadth:.0f}%)")
    else:
        score -= 20
        details.append(f"宽度弱势 ({breadth:.0f}% -20)")
    
    details.append(f"波动: {volatility}")
    return score, details


# ============================================================
# 资金面信号（北向资金 + 融资余额）
# ============================================================

def get_north_flow_signal():
    """
    获取北向资金流向信号
    数据源: efinance → AkShare
    返回: (信号值, 描述)
    """
    # 1. 尝试 efinance
    try:
        import efinance as ef
        df = ef.stock.get_north_flow()
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            flow = latest['当日成交净买入'] if '当日成交净买入' in latest else 0
            if flow > 50:
                return 1, f"北向净流入 {flow:.0f}亿"
            elif flow < -50:
                return -1, f"北向净流出 {flow:.0f}亿"
            else:
                return 0, f"北向平衡 {flow:.0f}亿"
    except Exception as e:
        print(f"efinance 获取北向资金失败: {e}")
    
    # 2. 尝试 AkShare
    try:
        import akshare as ak
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            flow = latest['当日成交净买入'] if '当日成交净买入' in latest else 0
            if flow > 50:
                return 1, f"北向净流入 {flow:.0f}亿"
            elif flow < -50:
                return -1, f"北向净流出 {flow:.0f}亿"
            else:
                return 0, f"北向平衡 {flow:.0f}亿"
    except Exception as e:
        print(f"AkShare 获取北向资金失败: {e}")
    
    return 0, "北向资金数据获取失败"


def get_margin_balance_signal():
    """
    获取融资余额变化信号
    数据源: efinance → AkShare
    返回: (信号值, 描述)
    """
    # 1. 尝试 efinance
    try:
        import efinance as ef
        df = ef.stock.get_margin_trading()
        if df is not None and len(df) > 1:
            latest = df.iloc[-1]['融资余额']
            prev = df.iloc[-2]['融资余额']
            change = (latest - prev) / prev * 100 if prev > 0 else 0
            if change > 1:
                return 1, f"融资余额增加 {change:.2f}%"
            elif change < -1:
                return -1, f"融资余额减少 {change:.2f}%"
            else:
                return 0, f"融资余额平稳 {change:.2f}%"
    except Exception as e:
        print(f"efinance 获取融资余额失败: {e}")
    
    # 2. 尝试 AkShare
    try:
        import akshare as ak
        df = ak.stock_margin_sse()
        if df is not None and len(df) > 1:
            latest = df.iloc[-1]['融资余额']
            prev = df.iloc[-2]['融资余额']
            change = (latest - prev) / prev * 100 if prev > 0 else 0
            if change > 1:
                return 1, f"融资余额增加 {change:.2f}%"
            elif change < -1:
                return -1, f"融资余额减少 {change:.2f}%"
            else:
                return 0, f"融资余额平稳 {change:.2f}%"
    except Exception as e:
        print(f"AkShare 获取融资余额失败: {e}")
    
    return 0, "融资余额数据获取失败"


# ============================================================
# 情绪面信号（涨跌家数 + 涨停家数）
# ============================================================

def get_market_sentiment_signal():
    """
    获取市场情绪信号（涨跌家数、涨停家数）
    数据源: efinance → AkShare
    返回: (信号值, 描述)
    """
    # 1. 尝试 efinance
    try:
        import efinance as ef
        df = ef.stock.get_realtime_quotes()
        if df is not None and len(df) > 0:
            up = len(df[df['涨跌幅'] > 0])
            down = len(df[df['涨跌幅'] < 0])
            total = len(df)
            up_ratio = up / total * 100
            limit_up = len(df[df['涨跌幅'] > 9.8])
            limit_down = len(df[df['涨跌幅'] < -9.8])
            
            if up_ratio > 70 and limit_up > 50:
                return 1, f"情绪高涨（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
            elif up_ratio < 30 and limit_down > 50:
                return -1, f"情绪恐慌（涨 {up_ratio:.0f}%，跌停 {limit_down} 家）"
            else:
                return 0, f"情绪平稳（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
    except Exception as e:
        print(f"efinance 获取情绪信号失败: {e}")
    
    # 2. 尝试 AkShare
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()
        if df is not None and len(df) > 0:
            up = len(df[df['涨跌幅'] > 0])
            down = len(df[df['涨跌幅'] < 0])
            total = len(df)
            up_ratio = up / total * 100
            limit_up = len(df[df['涨跌幅'] > 9.8])
            limit_down = len(df[df['涨跌幅'] < -9.8])
            
            if up_ratio > 70 and limit_up > 50:
                return 1, f"情绪高涨（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
            elif up_ratio < 30 and limit_down > 50:
                return -1, f"情绪恐慌（涨 {up_ratio:.0f}%，跌停 {limit_down} 家）"
            else:
                return 0, f"情绪平稳（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
    except Exception as e:
        print(f"AkShare 获取情绪信号失败: {e}")
    
    return 0, "情绪信号获取失败"


# ============================================================
# 综合信号汇总函数
# ============================================================

def aggregate_all_signals(sh_closes):
    """
    汇总所有信号：技术面 + 资金面 + 情绪面
    返回: 综合评分(整数), 详情列表
    """
    all_details = []
    total_score = 0
    
    # 1. 技术面
    tech_score, tech_details = aggregate_technical_signals(sh_closes)
    total_score += tech_score
    all_details.extend(tech_details)
    print(f"  技术面评分: {tech_score}")
    
    # 2. 资金面：北向资金
    north_score, north_desc = get_north_flow_signal()
    total_score += north_score * 20
    all_details.append(f"北向资金: {north_desc}")
    print(f"  北向资金: {north_desc}")
    
    # 3. 资金面：融资余额
    margin_score, margin_desc = get_margin_balance_signal()
    total_score += margin_score * 10
    all_details.append(f"融资余额: {margin_desc}")
    print(f"  融资余额: {margin_desc}")
    
    # 4. 情绪面：涨跌家数
    sent_score, sent_desc = get_market_sentiment_signal()
    total_score += sent_score * 15
    all_details.append(f"市场情绪: {sent_desc}")
    print(f"  市场情绪: {sent_desc}")
    
    return total_score, all_details


if __name__ == "__main__":
    # 测试用
    closes = [3000 + i for i in range(100)]
    score, details = aggregate_all_signals(closes)
    print(f"\n综合评分: {score}")
    print("详情:")
    for d in details:
        print(f"  {d}")