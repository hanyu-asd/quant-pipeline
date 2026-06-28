#!/usr/bin/env python3
"""
信号采集模块：技术面、资金面、情绪面
资金面/情绪面数据源：AkShare（唯一，稳定）
技术面从指数数据计算，无需外部数据源
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

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
    """获取北向资金流向信号，返回 (信号值, 描述)"""
    try:
        import akshare as ak
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            flow_col = '当日成交净买入' if '当日成交净买入' in df.columns else 'value'
            flow = latest.get(flow_col, 0)
            if isinstance(flow, str):
                flow = float(flow.replace(',', ''))
            if flow > 50:
                return 1, f"北向净流入 {flow:.0f}亿"
            elif flow < -50:
                return -1, f"北向净流出 {flow:.0f}亿"
            else:
                return 0, f"北向平衡 {flow:.0f}亿"
    except Exception as e:
        pass
    return 0, "北向资金: 数据获取失败"


def get_margin_balance_signal():
    """获取融资余额变化信号，返回 (信号值, 描述)"""
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = ak.stock_margin_sse(start_date=start_date, end_date=end_date)
        if df is not None and len(df) > 1:
            df = df.sort_values('信用交易日期')
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            balance_col = '融资余额' if '融资余额' in df.columns else '融资余额(元)'
            latest_balance = latest.get(balance_col, 0)
            prev_balance = prev.get(balance_col, 0)
            if isinstance(latest_balance, str):
                latest_balance = float(latest_balance.replace(',', ''))
            if isinstance(prev_balance, str):
                prev_balance = float(prev_balance.replace(',', ''))
            change = (latest_balance - prev_balance) / prev_balance * 100 if prev_balance > 0 else 0
            if change > 1:
                return 1, f"融资余额增加 {change:.2f}%"
            elif change < -1:
                return -1, f"融资余额减少 {change:.2f}%"
            else:
                return 0, f"融资余额平稳 {change:.2f}%"
    except Exception as e:
        pass
    return 0, "融资余额: 数据获取失败"


# ============================================================
# 情绪面信号（涨跌家数 + 涨停家数）
# ============================================================

def get_market_sentiment_signal():
    """获取市场情绪信号，返回 (信号值, 描述)"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is not None and len(df) > 0:
            change_col = '涨跌幅'
            if change_col in df.columns:
                df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
                up = len(df[df[change_col] > 0])
                down = len(df[df[change_col] < 0])
                total = len(df)
                up_ratio = up / total * 100
                limit_up = len(df[df[change_col] > 9.8])
                limit_down = len(df[df[change_col] < -9.8])
                
                if up_ratio > 70 and limit_up > 50:
                    return 1, f"情绪高涨（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
                elif up_ratio < 30 and limit_down > 50:
                    return -1, f"情绪恐慌（涨 {up_ratio:.0f}%，跌停 {limit_down} 家）"
                else:
                    return 0, f"情绪平稳（涨 {up_ratio:.0f}%，涨停 {limit_up} 家）"
    except Exception as e:
        pass
    return 0, "市场情绪: 数据获取失败"


# ============================================================
# 综合信号汇总函数
# ============================================================

def aggregate_all_signals(sh_closes):
    """
    汇总所有信号：技术面 + 资金面 + 情绪面
    返回: 综合评分, 详情列表
    """
    all_details = []
    total_score = 0
    
    # 1. 技术面（从指数数据计算）
    tech_score, tech_details = aggregate_technical_signals(sh_closes)
    total_score += tech_score
    all_details.extend(tech_details)
    print(f"  技术面评分: {tech_score}")
    
    # 2. 资金面：北向资金
    north_score, north_desc = get_north_flow_signal()
    total_score += north_score * 20
    all_details.append(north_desc)
    print(f"  北向资金: {north_desc}")
    
    # 3. 资金面：融资余额
    margin_score, margin_desc = get_margin_balance_signal()
    total_score += margin_score * 10
    all_details.append(margin_desc)
    print(f"  融资余额: {margin_desc}")
    
    # 4. 情绪面：涨跌家数
    sent_score, sent_desc = get_market_sentiment_signal()
    total_score += sent_score * 15
    all_details.append(sent_desc)
    print(f"  市场情绪: {sent_desc}")
    
    return total_score, all_details


if __name__ == "__main__":
    closes = [3000 + i for i in range(100)]
    score, details = aggregate_all_signals(closes)
    print(f"\n综合评分: {score}")
    print("详情:")
    for d in details:
        print(f"  {d}")