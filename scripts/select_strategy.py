#!/usr/bin/env python3
"""
双窗口趋势判断 + 主线识别 + 策略选择
v6.8 - 修正 TickFlow API，移除易方达 AI
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
CACHE_DIR = "cache"


# ============================================================
# 缓存工具函数
# ============================================================
def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def save_index_cache(symbol, closes):
    ensure_cache_dir()
    cache_file = f"{CACHE_DIR}/index_{symbol}.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "closes": closes
            }, f)
    except Exception as e:
        log("WARNING", f"保存指数缓存失败 {symbol}: {e}")


def load_index_cache(symbol):
    cache_file = f"{CACHE_DIR}/index_{symbol}.json"
    if not os.path.exists(cache_file):
        return None, None
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("date"), data.get("closes")
    except Exception as e:
        log("WARNING", f"读取指数缓存失败 {symbol}: {e}")
        return None, None


def is_cache_valid(cache_date):
    if not cache_date:
        return False
    return cache_date == datetime.now().strftime("%Y-%m-%d")


# ============================================================
# 指数数据获取（多源）
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
        log("WARNING", f"[Baostock] 获取指数失败: {e}")
        return None


def get_index_history_tickflow(symbol, days=100):
    """使用 TickFlow 获取指数日线数据（正确 API）"""
    try:
        from tickflow import TickFlow
        tf = TickFlow.free()
        # 转换 symbol: sh000001 → 000001.SH
        code = symbol.replace('sh', '').replace('sz', '')
        market = 'SH' if 'sh' in symbol else 'SZ'
        full_symbol = f"{code}.{market}"
        df = tf.klines.get(
            symbol=full_symbol,
            period="1d",
            count=days,
            as_dataframe=True
        )
        if df is not None and len(df) >= 10:
            df = df.sort_values('trade_date')
            return df['close'].values.tolist()
        return None
    except Exception as e:
        log("WARNING", f"[TickFlow] 获取指数 {symbol} 失败: {e}")
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
        log("WARNING", f"[新浪] 获取指数失败: {e}")
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
        return [float(item[2]) for item in kline_data if len(item) > 2]
    except Exception as e:
        log("WARNING", f"[腾讯] 获取指数失败: {e}")
        return None


def get_index_history_akshare(symbol, days=100):
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        code = symbol.replace('sh', '').replace('sz', '')
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="")
        if df.empty or len(df) < 10:
            return None
        return df['收盘'].values.tolist()
    except Exception as e:
        log("WARNING", f"[AkShare] 获取指数失败: {e}")
        return None


def get_index_data(symbol, days=100):
    if symbol in ["sh000001", "000001"]:
        name = "上证指数"
    elif symbol in ["sz399006", "399006"]:
        name = "创业板指"
    else:
        return None

    log("INFO", f"正在获取 {name} 数据...")

    # 1. Baostock
    closes = get_index_history_baostock(symbol, days)
    if closes:
        log("INFO", f"  ✅ Baostock成功: {len(closes)}个交易日")
        return closes

    # 2. TickFlow
    log("WARNING", f"  Baostock失败，切换TickFlow")
    closes = get_index_history_tickflow(symbol, days)
    if closes:
        log("INFO", f"  ✅ TickFlow成功: {len(closes)}个交易日")
        return closes

    # 3. 新浪
    log("WARNING", f"  TickFlow失败，切换新浪财经")
    closes = get_index_history_sina(symbol, days)
    if closes:
        log("INFO", f"  ✅ 新浪财经成功: {len(closes)}个交易日")
        return closes

    # 4. 腾讯
    log("WARNING", f"  新浪失败，切换腾讯财经")
    closes = get_index_history_tencent(symbol, days)
    if closes:
        log("INFO", f"  ✅ 腾讯财经成功: {len(closes)}个交易日")
        return closes

    # 5. AkShare
    log("WARNING", f"  腾讯失败，切换AkShare")
    closes = get_index_history_akshare(symbol, days)
    if closes:
        log("INFO", f"  ✅ AkShare成功: {len(closes)}个交易日")
        return closes

    log("ERROR", f"  所有数据源均失败")
    return None


# ============================================================
# 趋势判断与策略决策
# ============================================================
def calculate_ma(closes, period):
    if len(closes) < period:
        return closes[-1]
    return sum(closes[-period:]) / period


def detect_trend_and_state(sh_closes, cy_closes, mainline_result):
    if not sh_closes or len(sh_closes) < 60:
        return "震荡", "normal", "震荡", 0, 0, 0, 0, 0

    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60)
    current = sh_closes[-1]
    momentum_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100 if len(sh_closes) >= 20 else 0

    if ma20 > ma60:
        trend = "上升趋势"
    elif ma20 < ma60:
        trend = "下降趋势"
    else:
        trend = "震荡"

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

    tech_premium = 0
    if cy_closes and len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)

    pattern = "震荡"
    if trend == "上升趋势":
        pattern = "普涨"
    elif trend == "下降趋势":
        if mainline_result.get("confidence", 0) > 50 and mainline_result.get("relative_strength", 0) > 5:
            pattern = "结构性行情"
        else:
            pattern = "普跌"
    else:
        if mainline_result.get("confidence", 0) > 50:
            pattern = "结构性行情"

    return trend, market_state, pattern, tech_premium, ma20, ma60, momentum_20, current


def get_position_advice(trend, pattern, mainline_confidence, market_state):
    if market_state == "extreme":
        return 0, 0, 100, "极端模式，建议空仓观望"
    if market_state == "high_risk":
        return 30, 30, 40, "高风险模式，建议轻仓防守"

    if pattern == "普涨":
        return 70, 20, 10, "普涨行情，积极配置"
    elif pattern == "结构性行情":
        if mainline_confidence > 70:
            return 50, 30, 20, "结构性行情（高置信度），适度积极"
        elif mainline_confidence > 50:
            return 40, 35, 25, "结构性行情（中等置信度），温和配置"
        else:
            return 30, 35, 35, "结构性行情（低置信度），谨慎"
    elif pattern == "普跌":
        return 20, 30, 50, "普跌行情，防御为主"
    else:
        return 40, 30, 30, "震荡行情，均衡配置"


def generate_default_market_state():
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trend": "下降趋势",
        "market_state": "normal",
        "pattern": "普跌",
        "strategy": "rsi_reversion_v1",
        "reason": "数据获取失败，使用默认防守策略",
        "main_group": None,
        "main_confidence": 0,
        "main_strength": 0,
        "main_strategy": "rsi_reversion_v1",
        "position_main": 20,
        "position_alt": 30,
        "position_def": 50,
        "position_reason": "数据缺失，防御为主",
        "current_price": 0,
        "ma20": 0,
        "ma60": 0,
        "momentum_20": 0,
        "tech_premium": 0
    }


def main():
    log("INFO", "=" * 70)
    log("INFO", "📊 双窗口趋势判断 + 动态主线识别（v6.8）")
    log("INFO", "=" * 70)

    # 获取上证指数数据（优先实时，缓存仅作兜底）
    sh_closes = get_index_data("sh000001", 100)
    sh_cache_date, sh_cache_closes = load_index_cache("sh000001")
    use_realtime = sh_closes is not None

    if use_realtime:
        log("INFO", f"✅ 使用实时数据，交易日数: {len(sh_closes)}")
        save_index_cache("sh000001", sh_closes)
    else:
        log("WARNING", "❌ 上证指数实时数据获取失败")
        if is_cache_valid(sh_cache_date) and sh_cache_closes:
            log("WARNING", "⚠️ 使用今日缓存数据（仅作容错）")
            sh_closes = sh_cache_closes
        elif sh_cache_closes:
            log("WARNING", "⚠️ 使用过期缓存数据（仅作容错）")
            sh_closes = sh_cache_closes
        else:
            log("ERROR", "❌ 无任何可用数据，使用默认策略")
            default_state = generate_default_market_state()
            with open("market_state.json", "w", encoding="utf-8") as f:
                json.dump(default_state, f, indent=2, ensure_ascii=False)
            with open("selected_strategy.txt", "w") as f:
                f.write("rsi_reversion_v1")
            default_context = {
                "strategy": "rsi_reversion_v1",
                "strategy_type": "均值回归/超卖反弹",
                "decision_reason": "数据缺失，默认防守策略",
                "expected_action": "按防守策略执行",
                "risk_level": "防守"
            }
            with open("strategy_context.json", "w", encoding="utf-8") as f:
                json.dump(default_context, f, indent=2, ensure_ascii=False)
            log("INFO", "默认市场状态和策略上下文已保存")
            return

    # 获取创业板指数据（若无则用上证替代）
    cy_closes = get_index_data("sz399006", 100)
    if cy_closes:
        log("INFO", f"✅ 创业板指数据获取成功，交易日数: {len(cy_closes)}")
        save_index_cache("sz399006", cy_closes)
    else:
        log("WARNING", "创业板指数据获取失败，将使用上证指数替代")
        cy_closes = sh_closes

    # 如果数据来自缓存，强制使用默认防守策略（不计算趋势）
    if not use_realtime:
        log("WARNING", "⚠️ 数据来源为缓存，不进行趋势判断，采用默认防守策略")
        default_state = generate_default_market_state()
        default_state["current_price"] = sh_closes[-1] if sh_closes else 0
        default_state["date"] = datetime.now().strftime("%Y-%m-%d")
        with open("market_state.json", "w", encoding="utf-8") as f:
            json.dump(default_state, f, indent=2, ensure_ascii=False)
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        context = {
            "strategy": "rsi_reversion_v1",
            "strategy_type": "均值回归/超卖反弹",
            "decision_reason": "数据不可用，采用默认防守策略",
            "expected_action": "按防守策略执行",
            "risk_level": "防守"
        }
        with open("strategy_context.json", "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2, ensure_ascii=False)
        log("INFO", "✅ 默认防守策略已保存")
        return

    # 主线识别
    log("INFO", "正在识别市场主线...")
    mainline_result = identify_mainline()

    # 趋势判断
    trend, market_state, pattern, tech_premium, ma20, ma60, momentum_20, current = detect_trend_and_state(
        sh_closes, cy_closes, mainline_result
    )

    # 策略决策
    strategy = None
    reason = ""

    if market_state in ("extreme", "high_risk"):
        strategy = "rsi_reversion_v1"
        reason = f"{market_state}，强制防守策略"
    elif mainline_result.get("confidence", 0) > 50:
        strategy = mainline_result.get("strategy", "balanced_alpha")
        reason = f"主线识别: {mainline_result.get('main_group', '未知')}（置信度 {mainline_result.get('confidence', 0)}%）"
    elif trend == "上升趋势":
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势，趋势跟踪策略"
    elif trend == "震荡":
        strategy = "balanced_alpha"
        reason = "震荡行情，均衡配置"
    else:
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（无主线），均值回归防守"

    main_pct, alt_pct, def_pct, pos_reason = get_position_advice(
        trend, pattern, mainline_result.get("confidence", 0), market_state
    )

    log("INFO", f"📊 上证指数: {current:.2f}, MA20: {ma20:.2f}, MA60: {ma60:.2f}")
    log("INFO", f"📊 近20日动量: {momentum_20:.2f}%, 科技溢价: {tech_premium:.2f}%")
    log("INFO", f"📊 趋势: {trend}, 市场状态: {market_state}, pattern: {pattern}")
    if mainline_result.get("main_group"):
        log("INFO", f"📊 主线: {mainline_result.get('main_group')} (置信度 {mainline_result.get('confidence')}%, 强度 {mainline_result.get('relative_strength', 0):.2f}%)")
    else:
        log("INFO", "📊 主线: 无")
    log("INFO", f"🎯 选定策略: {strategy}")
    log("INFO", f"📝 原因: {reason}")
    log("INFO", f"💰 仓位: 主{main_pct}% / 备{alt_pct}% / 防{def_pct}% - {pos_reason}")
    log("INFO", "=" * 70)

    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trend": trend,
        "market_state": market_state,
        "pattern": pattern,
        "strategy": strategy,
        "reason": reason,
        "main_group": mainline_result.get("main_group"),
        "main_confidence": mainline_result.get("confidence", 0),
        "main_strength": mainline_result.get("relative_strength", 0),
        "main_strategy": mainline_result.get("strategy"),
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

    # 生成策略上下文
    strategy_context = {
        "strategy": strategy,
        "strategy_type": {
            "rsi_reversion_v1": "均值回归/超卖反弹",
            "trend_pullback_rebound": "趋势跟踪/回调买入",
            "momentum_quality": "动量质量/强势股",
            "volume_breakout": "放量突破",
            "balanced_alpha": "均衡配置",
            "dual_low": "双低策略",
            "quality_value": "质量价值"
        }.get(strategy, "未知策略"),
        "decision_reason": reason,
        "expected_action": {
            "rsi_reversion_v1": "寻找超卖股票，等待技术性反弹",
            "trend_pullback_rebound": "寻找上升趋势中的回调机会",
            "momentum_quality": "寻找动量强劲的优质股票",
            "volume_breakout": "寻找放量突破的强势股",
            "balanced_alpha": "均衡配置，分散风险",
            "dual_low": "寻找低估值低波动股票",
            "quality_value": "寻找高质量价值股"
        }.get(strategy, "按策略信号执行"),
        "risk_level": {
            "rsi_reversion_v1": "防守",
            "trend_pullback_rebound": "积极",
            "momentum_quality": "积极",
            "volume_breakout": "激进",
            "balanced_alpha": "中性",
            "dual_low": "防守",
            "quality_value": "中性"
        }.get(strategy, "中性")
    }
    with open("strategy_context.json", "w", encoding="utf-8") as f:
        json.dump(strategy_context, f, indent=2, ensure_ascii=False)

    log("INFO", "✅ 结果已保存")


if __name__ == "__main__":
    main()