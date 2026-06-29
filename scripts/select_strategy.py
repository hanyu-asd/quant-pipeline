#!/usr/bin/env python3
"""
双窗口趋势判断 + 主线识别 + 策略选择
v6.1 - 增强异常处理、告警、日志统一
"""
import requests
import json
import re
import os
import sys
from datetime import datetime, timedelta
from identify_mainline import identify_mainline
from logger import log

STATE_FILE = "trend_state.json"

# ---- 数据源获取（4层） ----
def get_index_history_baostock(symbol, days=100):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_history_k_data_plus(
            symbol, "date,close",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) < 10:
            return None
        return [float(x) for x in data['close'].tolist()]
    except Exception as e:
        log("WARNING", f"[get_index_history_baostock] 失败: {e}")
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
        return [float(item['close']) for item in data]
    except Exception as e:
        log("WARNING", f"[get_index_history_sina] 失败: {e}")
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
        return [float(item[2]) for item in kline_data if len(item)>2]
    except Exception as e:
        log("WARNING", f"[get_index_history_tencent] 失败: {e}")
        return None

def get_index_history_akshare(symbol, days=100):
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="")
        if df.empty or len(df) < 10:
            return None
        return df['收盘'].values.tolist()
    except Exception as e:
        log("WARNING", f"[get_index_history_akshare] 失败: {e}")
        return None

def get_index_data(symbol, days=100):
    if symbol in ["sh000001", "000001"]:
        code_map = {"baostock": "sh.000001", "sina": "sh000001", "tencent": "sh000001", "akshare": "000001"}
        name = "上证指数"
    elif symbol in ["sz399006", "399006"]:
        code_map = {"baostock": "sz.399006", "sina": "sz399006", "tencent": "sz399006", "akshare": "399006"}
        name = "创业板指"
    else:
        return None
    log("INFO", f"正在获取 {name} 数据...")
    closes = get_index_history_baostock(code_map["baostock"], days)
    if closes:
        log("INFO", f"  ✅ Baostock成功: {len(closes)}个交易日")
        return closes
    log("WARNING", f"  Baostock失败，切换新浪财经")
    closes = get_index_history_sina(code_map["sina"], days)
    if closes:
        log("INFO", f"  ✅ 新浪财经成功: {len(closes)}个交易日")
        return closes
    log("WARNING", f"  新浪失败，切换腾讯财经")
    closes = get_index_history_tencent(code_map["tencent"], days)
    if closes:
        log("INFO", f"  ✅ 腾讯财经成功: {len(closes)}个交易日")
        return closes
    log("WARNING", f"  腾讯失败，切换AkShare")
    closes = get_index_history_akshare(code_map["akshare"], days)
    if closes:
        log("INFO", f"  ✅ AkShare成功: {len(closes)}个交易日")
        return closes
    log("ERROR", f"  所有数据源均失败")
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
    momentum_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100 if len(sh_closes)>=20 else 0
    long_trend = "up" if ma20 > ma60 else ("down" if ma20 < ma60 else "sideways")
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
    if cy_closes and len(cy_closes)>=20 and len(sh_closes)>=20:
        ret_cy = (cy_closes[-1]/cy_closes[-20]-1)*100
        ret_sh = (sh_closes[-1]/sh_closes[-20]-1)*100
        tech_premium = round(ret_cy - ret_sh, 2)
    return base_trend, tech_premium, ma20, ma60, momentum_20, current

def get_position_advice(trend, market_state, confidence):
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
    log("INFO", "="*70)
    log("INFO", "📊 双窗口趋势判断 + 动态主线识别（v6.1）")
    log("INFO", "="*70)
    
    sh_closes = get_index_data("sh000001", 100)
    if not sh_closes:
        log("ERROR", "无法获取指数数据，使用默认策略 rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return
    cy_closes = get_index_data("sz399006", 100)
    if not cy_closes:
        cy_closes = sh_closes
    
    trend, tech_premium, ma20, ma60, momentum_20, current = detect_trend(sh_closes, cy_closes)
    trend_desc = {"up":"上升趋势", "down":"下降趋势", "sideways":"震荡"}.get(trend, "未知")
    
    if len(sh_closes) >= 20:
        ret_20 = (sh_closes[-1]/sh_closes[-20]-1)*100
        if ret_20 < -7:
            market_state = "extreme"
        elif ret_20 < -4:
            market_state = "high_risk"
        else:
            market_state = "normal"
    else:
        market_state = "normal"
    
    log("INFO", "正在识别市场主线...")
    main_group, main_strategy, confidence, confirm_days = identify_mainline()
    
    # 策略决策（优先级）
    if market_state in ("extreme", "high_risk"):
        strategy = "rsi_reversion_v1"
        reason = f"{market_state}，使用防守策略"
    elif main_group and confidence > 50:
        strategy = main_strategy
        reason = f"主线识别: {main_group}（置信度 {confidence:.0f}%）"
    elif trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技溢价 {tech_premium:.2f}%"
    elif trend == "up":
        # 上升趋势无主线：使用 volume_breakout（放量突破）
        # 注：需确认 alphaevo/strategies/builtin/volume_breakout.yaml 存在
        strategy = "volume_breakout"
        reason = f"上升趋势 → 放量突破（动量 {momentum_20:.2f}%）"
    else:
        strategy = "rsi_reversion_v1"
        reason = f"{trend_desc}（均值回归）"
    
    main_pct, alt_pct, def_pct, pos_reason = get_position_advice(trend, market_state, confidence)
    
    log("INFO", f"📊 上证指数: {current:.2f}, MA20: {ma20:.2f}, MA60: {ma60:.2f}")
    log("INFO", f"📊 近20日动量: {momentum_20:.2f}%, 科技溢价: {tech_premium:.2f}%")
    log("INFO", f"📊 趋势: {trend_desc}, 市场状态: {market_state}")
    log("INFO", f"🎯 选定策略: {strategy}")
    log("INFO", f"📝 原因: {reason}")
    log("INFO", f"💰 仓位: 主{main_pct}% / 备{alt_pct}% / 防{def_pct}% - {pos_reason}")
    log("INFO", "="*70)
    
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
    
    log("INFO", "✅ 结果已保存")

if __name__ == "__main__":
    main()