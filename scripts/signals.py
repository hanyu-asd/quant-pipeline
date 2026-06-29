#!/usr/bin/env python3
"""
信号采集模块：技术面、资金面、情绪面
v6.1 - 增强异常处理和日志
"""
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from logger import log

# ---- 技术面 ----
def calculate_momentum_signal(closes, lookback=20):
    if len(closes) < lookback:
        return 0
    ret = (closes[-1] / closes[-lookback] - 1) * 100
    return 1 if ret > 5 else (-1 if ret < -5 else 0)

def calculate_breadth_signal(closes, lookback=20):
    if len(closes) < lookback:
        return 50
    ma20 = sum(closes[-lookback:]) / lookback
    above = sum(1 for c in closes[-lookback:] if c > ma20)
    return above / lookback * 100

def calculate_volatility_signal(closes, lookback=20):
    if len(closes) < lookback:
        return 'normal'
    returns = [(closes[i]/closes[i-1]-1)*100 for i in range(1, len(closes))]
    recent = returns[-lookback:]
    vol = np.std(recent) if recent else 0
    if vol > 2.5:
        return 'high'
    elif vol < 0.8:
        return 'low'
    return 'normal'

def aggregate_technical_signals(sh_closes):
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
        details.append("动量中性")
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

# ---- 资金面 ----
def get_north_flow_signal():
    try:
        import akshare as ak
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            flow = latest.get('当日成交净买入', 0)
            if isinstance(flow, str):
                flow = float(flow.replace(',', ''))
            if flow > 50:
                return 1, f"北向净流入 {flow:.0f}亿"
            elif flow < -50:
                return -1, f"北向净流出 {flow:.0f}亿"
            else:
                return 0, f"北向平衡 {flow:.0f}亿"
    except Exception as e:
        log("WARNING", f"[get_north_flow_signal] 异常: {e}")
    return 0, "北向数据获取失败"

def get_margin_balance_signal():
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = ak.stock_margin_sse(start_date=start_date, end_date=end_date)
        if df is not None and len(df) > 1:
            df = df.sort_values('信用交易日期')
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            bal_col = '融资余额' if '融资余额' in df.columns else '融资余额(元)'
            latest_bal = latest.get(bal_col, 0)
            prev_bal = prev.get(bal_col, 0)
            if isinstance(latest_bal, str):
                latest_bal = float(latest_bal.replace(',', ''))
            if isinstance(prev_bal, str):
                prev_bal = float(prev_bal.replace(',', ''))
            change = (latest_bal - prev_bal)/prev_bal*100 if prev_bal > 0 else 0
            if change > 1:
                return 1, f"融资余额增加 {change:.2f}%"
            elif change < -1:
                return -1, f"融资余额减少 {change:.2f}%"
            else:
                return 0, f"融资余额平稳 {change:.2f}%"
    except Exception as e:
        log("WARNING", f"[get_margin_balance_signal] 异常: {e}")
    return 0, "融资数据获取失败"

def get_market_sentiment_signal():
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
                up_ratio = up/total*100 if total>0 else 0
                limit_up = len(df[df[change_col] > 9.8])
                limit_down = len(df[df[change_col] < -9.8])
                if up_ratio > 70 and limit_up > 50:
                    return 1, f"情绪高涨（涨 {up_ratio:.0f}%，涨停 {limit_up}家）"
                elif up_ratio < 30 and limit_down > 50:
                    return -1, f"情绪恐慌（涨 {up_ratio:.0f}%，跌停 {limit_down}家）"
                else:
                    return 0, f"情绪平稳（涨 {up_ratio:.0f}%，涨停 {limit_up}家）"
    except Exception as e:
        log("WARNING", f"[get_market_sentiment_signal] 异常: {e}")
    return 0, "情绪数据获取失败"

def aggregate_all_signals(sh_closes):
    total_score = 0
    details = []
    tech_score, tech_details = aggregate_technical_signals(sh_closes)
    total_score += tech_score
    details.extend(tech_details)
    log("INFO", f"技术面评分: {tech_score}")
    
    north_score, north_desc = get_north_flow_signal()
    total_score += north_score * 20
    details.append(north_desc)
    log("INFO", f"北向: {north_desc}")
    
    margin_score, margin_desc = get_margin_balance_signal()
    total_score += margin_score * 10
    details.append(margin_desc)
    log("INFO", f"融资: {margin_desc}")
    
    sent_score, sent_desc = get_market_sentiment_signal()
    total_score += sent_score * 15
    details.append(sent_desc)
    log("INFO", f"情绪: {sent_desc}")
    
    log("INFO", f"综合评分: {total_score}")
    return total_score, details

if __name__ == "__main__":
    closes = [3000 + i for i in range(100)]
    score, details = aggregate_all_signals(closes)
    print(f"\n综合评分: {score}")
    for d in details:
        print(f"  {d}")