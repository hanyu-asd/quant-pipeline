#!/usr/bin/env python3
"""
双窗口趋势判断 + 主线识别 + 策略选择
版本：v6.0（集成动态主线识别）
"""

import requests
import json
import re
import os
import sys
from datetime import datetime, timedelta
from identify_mainline import identify_mainline

STATE_FILE = "trend_state.json"


# ============================================================
# 数据源函数（5个数据源）
# ============================================================

def get_index_history_baostock(symbol, days=100):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_history_k_data_plus(
            symbol,
            "date,close",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) < 10:
            return None
        closes = [float(x) for x in data['close'].tolist()]
        return closes
    except:
        return None


def get_index_history_efinance(symbol, days=100):
    try:
        import efinance as ef
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ef.stock.get_quote_history(symbol, beg=start_date, end=end_date)
        if df is None or len(df) < 10:
            return None
        closes = df.iloc[:, 2].tolist()
        return closes
    except:
        return None


def get_index_history_sina(symbol, days=100):
    try:
        url = f"https://quotes.sina.com.cn/stock/api/json_v2.php/var/stock_day?symbol={symbol}&page=1&num={days}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or len(data) < 10:
            return None
        closes = [float(item['close']) for item in data]
        return closes
    except:
        return None


def get_index_history_tencent(symbol, days=100):
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data_str = resp.text
        match = re.search(r'kline_day=({.*})', data_str)
        if not match:
            return None
        data_json = json.loads(match.group(1))
        if 'data' not in data_json or symbol not in data_json['data']:
            return None
        kline_data = data_json['data'][symbol].get('day', [])
        if not kline_data:
            return None
        closes = [float(item[2]) for item in kline_data if len(item) > 2]
        return closes
    except:
        return None


def get_index_history_akshare(symbol, days=100):
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="")
        if df.empty or len(df) < 10:
            return None
        closes = df['收盘'].values.tolist()
        return closes
    except:
        return None


def get_index_data(symbol, days=100):
    if symbol in ["sh000001", "000001"]:
        code_map = {"baostock": "sh.000001", "efinance": "000001", "sina": "sh000001", "tencent": "sh000001", "akshare": "000001"}
        name = "上证指数"
    elif symbol in ["sz399006", "399006"]:
        code_map = {"baostock": "sz.399006", "efinance": "399006", "sina": "sz399006", "tencent": "sz399006", "akshare": "399006"}
        name = "创业板指"
    else:
        return None
    print(f"  正在获取 {name} 数据...")
    closes = get_index_history_baostock(code_map["baostock"], days)
    if closes:
        print(f"   ✅ Baostock成功: {len(closes)} 个交易日")
        return closes
    closes = get_index_history_efinance(code_map["efinance"], days)
    if closes:
        print(f"   ✅ efinance成功: {len(closes)} 个交易日")
        return closes
    closes = get_index_history_sina(code_map["sina"], days)
    if closes:
        print(f"   ✅ 新浪财经成功: {len(closes)} 个交易日")
        return closes
    closes = get_index_history_tencent(code_map["tencent"], days)
    if closes:
        print(f"   ✅ 腾讯财经成功: {len(closes)} 个交易日")
        return closes
    closes = get_index_history_akshare(code_map["akshare"], days)
    if closes:
        print(f"   ✅ AkShare成功: {len(closes)} 个交易日")
        return closes
    print(f"   ❌ 所有5个数据源均失败")
    return None


def calculate_ma(closes, period):
    if len(closes) < period:
        return closes[-1]
    return sum(closes[-period:]) / period


def detect_trend(sh_closes, cy_closes):
    if not sh_closes or len(sh_closes) < 60:
        return "sideways", "rsi_reversion_v1", "数据不足", "数据不足", 0, 0, 3

    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60)
    current = sh_closes[-1]
    momentum_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100

    if ma20 > ma60:
        long_trend = "up"
    elif ma20 < ma60:
        long_trend = "down"
    else:
        long_trend = "sideways"

    if long_trend == "up" and momentum_20 < -3:
        base_trend = "sideways"
    elif long_trend == "down" and momentum_20 > 3:
        base_trend = "sideways"
    elif long_trend == "up":
        base_trend = "up"
    elif long_trend == "down":
        base_trend = "down"
    else:
        base_trend = "sideways"

    tech_premium = 0
    if cy_closes and len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)

    return base_trend, tech_premium, ma20, ma60, momentum_20, current


def get_position_advice(trend, market_state, confidence):
    """根据市场状态分配仓位"""
    if market_state == "extreme":
        return 0, 0, 100, "极端模式，建议空仓观望"
    if market_state == "high_risk":
        return 30, 30, 40, "高风险模式，建议轻仓防守"
    if trend == "up" and confidence > 70:
        return 70, 20, 10, "上升趋势+主线明确，积极配置"
    if trend == "up" and confidence > 50:
        return 50, 30, 20, "上升趋势+主线模糊，适度配置"
    if trend == "up":
        return 40, 35, 25, "上升趋势无主线，均衡配置"
    if trend == "sideways":
        return 40, 35, 25, "震荡+无主线，均衡配置"
    return 30, 30, 40, "下跌趋势，防守为主"


def main():
    print("=" * 70)
    print("📊 双窗口趋势判断 + 动态主线识别（v6.0）")
    print("=" * 70)

    # 1. 获取指数数据
    sh_closes = get_index_data("sh000001", 100)
    if not sh_closes:
        print("⚠️ 无法获取指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return

    cy_closes = get_index_data("sz399006", 100)
    if not cy_closes:
        cy_closes = sh_closes

    # 2. 趋势判断
    trend, tech_premium, ma20, ma60, momentum_20, current = detect_trend(sh_closes, cy_closes)
    trend_desc = {"up": "上升趋势", "down": "下降趋势", "sideways": "震荡"}.get(trend, "未知")

    # 3. 大盘状态检测
    if len(sh_closes) >= 20:
        ret_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        if ret_20 < -7:
            market_state = "extreme"
        elif ret_20 < -4:
            market_state = "high_risk"
        else:
            market_state = "normal"
    else:
        market_state = "normal"

    # 4. 主线识别
    print("\n📊 正在识别市场主线...")
    main_group, main_strategy, confidence, confirm_days = identify_mainline()

    # 5. 策略选择
    if market_state == "extreme" or market_state == "high_risk":
        strategy = "rsi_reversion_v1"
        reason = f"{market_state}，使用防守策略"
    elif main_group and confidence > 50:
        strategy = main_strategy
        reason = f"主线识别: {main_group}（置信度 {confidence:.0f}%）"
    elif trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技溢价 {tech_premium:.2f}%"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = f"上升趋势（动量 {momentum_20:.2f}%）"
    else:
        strategy = "rsi_reversion_v1"
        reason = f"{trend_desc}（均值回归）"

    # 6. 仓位分配
    main_pct, alt_pct, def_pct, pos_reason = get_position_advice(trend, market_state, confidence)

    # 7. 输出
    print("")
    print("📊 分析结果:")
    print(f"  上证指数: {current:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    print(f"  近20日动量: {momentum_20:.2f}%")
    print(f"  科技溢价: {tech_premium:.2f}%")
    print(f"  趋势: {trend_desc}")
    print(f"  市场状态: {market_state}")
    print("")
    print(f"🎯 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("")
    print(f"💰 仓位建议:")
    print(f"  主策略: {main_pct}%")
    print(f"  备选: {alt_pct}%")
    print(f"  防御: {def_pct}%")
    print(f"  📌 {pos_reason}")
    print("=" * 70)

    # 8. 保存结果
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trend": trend,
        "trend_desc": trend_desc,
        "strategy": strategy,
        "reason": reason,
        "market_state": market_state,
        "main_group": main_group,
        "confidence": confidence,
        "confirm_days": confirm_days,
        "main_strategy": main_strategy,
        "position_main": main_pct,
        "position_alt": alt_pct,
        "position_def": def_pct,
        "position_reason": pos_reason,
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "momentum_20": momentum_20,
        "tech_premium": tech_premium
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print("✅ 结果已保存")


if __name__ == "__main__":
    main()