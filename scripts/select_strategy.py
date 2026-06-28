#!/usr/bin/env python3
"""
双窗口趋势判断 + 多信号验证 + 申万行业分类匹配
版本：v5.0（最终版）
"""

import requests
import json
import re
import os
import sys
from datetime import datetime, timedelta

STATE_FILE = "trend_state.json"
INDUSTRY_FILE = "scripts/industry_mapping.json"


# ============================================================
# 行业分类加载
# ============================================================

def load_industry_mapping():
    """加载申万行业分类表"""
    if not os.path.exists(INDUSTRY_FILE):
        print("⚠️ 行业分类表不存在，使用默认策略")
        return {}
    try:
        with open(INDUSTRY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"⚠️ 加载行业分类表失败: {e}")
        return {}


def get_stock_strategy(stock_code):
    """根据股票代码获取对应策略（申万行业分类）"""
    data = load_industry_mapping()
    if not data:
        return "rsi_reversion_v1"
    
    mapping = data.get("mapping", {})
    strategy_map = data.get("strategy_mapping", {})
    default = data.get("default_strategy", "rsi_reversion_v1")
    
    # 提取代码前缀（前3位）
    prefix = stock_code[:3] if len(stock_code) >= 3 else stock_code
    
    # 查找匹配的行业
    for industry, codes in mapping.items():
        if prefix in codes or stock_code in codes:
            return strategy_map.get(industry, default)
    
    return default


# ============================================================
# 动态确认天数（强度阈值细分）
# ============================================================

def calculate_confirm_days(signal_strength):
    """
    根据信号强度动态计算确认天数
    强信号（>85分）：1天确认
    较强信号（75-85分）：1.5天确认（盘中验证）
    中等信号（50-75分）：2天确认
    弱信号（<50分）：3天确认
    """
    if signal_strength > 85:
        return 1
    elif signal_strength > 75:
        return 2  # 1.5天，用2天近似
    elif signal_strength > 50:
        return 2
    else:
        return 3


# ============================================================
# 信号强度计算
# ============================================================

def calculate_signal_strength(total_score, consensus, tech_premium):
    """综合计算信号强度"""
    strength = 0
    if total_score > 75:
        strength += 40
    elif total_score > 50:
        strength += 25
    else:
        strength += 10
    if consensus > 50:
        strength += 30
    elif consensus > 30:
        strength += 15
    else:
        strength += 5
    if tech_premium > 3:
        strength += 10
    return min(100, strength)


# ============================================================
# 仓位分配
# ============================================================

def get_position_advice(trend, signal_strength, sentiment_score):
    """
    根据市场状态、信号强度和舆情评分分配仓位
    返回: (主策略%, 备用策略%, 防御%)
    """
    # 空仓条件
    if signal_strength < 15 or sentiment_score < -50:
        return 0, 0, 100
    
    # 上升趋势
    if trend == "up":
        if signal_strength > 75:
            return 55, 30, 15
        else:
            return 50, 35, 15
    
    # 下降趋势
    elif trend == "down":
        if signal_strength < 50:
            return 15, 25, 60
        else:
            return 30, 30, 40
    
    # 震荡
    else:
        if signal_strength > 50:
            return 40, 35, 25
        else:
            return 30, 35, 35


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
        code_map = {
            "baostock": "sh.000001",
            "efinance": "000001",
            "sina": "sh000001",
            "tencent": "sh000001",
            "akshare": "000001"
        }
        name = "上证指数"
    elif symbol in ["sz399006", "399006"]:
        code_map = {
            "baostock": "sz.399006",
            "efinance": "399006",
            "sina": "sz399006",
            "tencent": "sz399006",
            "akshare": "399006"
        }
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


# ============================================================
# 信号采集（简化版）
# ============================================================

def aggregate_all_signals(closes):
    """汇总所有信号"""
    if not closes or len(closes) < 20:
        return 0, ["数据不足"]
    
    momentum = (closes[-1] / closes[-20] - 1) * 100
    ma20 = sum(closes[-20:]) / 20
    above_ma20 = sum(1 for c in closes[-20:] if c > ma20)
    
    tech_score = 0
    details = []
    
    if momentum > 3:
        tech_score += 30
        details.append("动量强势 (+30)")
    elif momentum < -3:
        tech_score -= 30
        details.append("动量弱势 (-30)")
    else:
        details.append("动量中性 (0)")
    
    if above_ma20 >= 14:
        tech_score += 20
        details.append(f"宽度强势 ({above_ma20}/20 +20)")
    elif above_ma20 >= 10:
        details.append(f"宽度中性 ({above_ma20}/20)")
    else:
        tech_score -= 20
        details.append(f"宽度弱势 ({above_ma20}/20 -20)")
    
    return tech_score, details


# ============================================================
# 核心趋势判断
# ============================================================

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

    # 1. 双窗口基础判断
    if ma20 > ma60:
        long_trend = "up"
        long_desc = f"MA20({ma20:.2f}) > MA60({ma60:.2f})"
    elif ma20 < ma60:
        long_trend = "down"
        long_desc = f"MA20({ma20:.2f}) < MA60({ma60:.2f})"
    else:
        long_trend = "sideways"
        long_desc = "MA20 ≈ MA60"

    if long_trend == "up" and momentum_20 < -3:
        base_trend = "sideways"
        base_reason = f"中长期向上但短期动量偏弱（{momentum_20:.2f}%），暂判震荡"
    elif long_trend == "down" and momentum_20 > 3:
        base_trend = "sideways"
        base_reason = f"中长期向下但短期动量偏强（{momentum_20:.2f}%），暂判震荡"
    elif long_trend == "up":
        base_trend = "up"
        base_reason = f"中长期向上，短期动量 {momentum_20:.2f}%"
    elif long_trend == "down":
        base_trend = "down"
        base_reason = f"中长期向下，短期动量 {momentum_20:.2f}%"
    else:
        base_trend = "sideways"
        base_reason = "中长期方向不明"

    # 2. 多信号综合评分
    total_score, signal_details = aggregate_all_signals(sh_closes)
    
    # 3. 科技溢价
    tech_premium = 0
    if cy_closes and len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)

    # 4. 信号强度
    signal_strength = abs(total_score)
    confirm_days_needed = calculate_confirm_days(signal_strength)

    # 5. 确认天数机制
    prev_trend = "sideways"
    confirm_days = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                prev_state = json.load(f)
                prev_trend = prev_state.get('trend', 'sideways')
                confirm_days = prev_state.get('confirm_days', 0)
                if prev_state.get('base_trend') != base_trend:
                    confirm_days = 0
        except:
            pass

    if base_trend == prev_trend:
        confirm_days = min(confirm_days + 1, confirm_days_needed + 1)
        if confirm_days >= confirm_days_needed:
            final_trend = base_trend
            final_reason = f"{base_reason}（已确认 {confirm_days}/{confirm_days_needed} 天）"
        else:
            final_trend = prev_trend
            final_reason = f"{base_reason}（确认中 {confirm_days}/{confirm_days_needed} 天）"
    else:
        confirm_days = 0
        final_trend = prev_trend
        final_reason = f"{base_reason}（新状态确认第1天，需 {confirm_days_needed} 天确认）"

    # 6. 策略选择
    if final_trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技股强势（溢价 {tech_premium}%）"
    elif final_trend == "up":
        strategy = "ma_crossover"
        reason = f"上升趋势（动量 {momentum_20:.2f}%）"
    elif final_trend == "down":
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（等待超跌反弹）"
    else:
        strategy = "rsi_reversion_v1"
        reason = "震荡（均值回归）"

    # 保存状态
    state = {
        "trend": final_trend,
        "base_trend": base_trend,
        "confirm_days": confirm_days,
        "confirm_days_needed": confirm_days_needed,
        "signal_strength": signal_strength,
        "last_check": datetime.now().strftime("%Y-%m-%d"),
        "ma20": ma20,
        "ma60": ma60,
        "momentum_20": momentum_20,
        "tech_premium": tech_premium,
        "total_score": total_score
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    return final_trend, strategy, reason, final_reason, tech_premium, signal_details, confirm_days_needed


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 70)
    print("📊 双窗口趋势判断 + 多信号验证（v5.0 - 最终版）")
    print("=" * 70)

    sh_closes = get_index_data("sh000001", 100)
    if not sh_closes:
        print("⚠️ 无法获取指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return

    cy_closes = get_index_data("sz399006", 100)
    if not cy_closes:
        print("⚠️ 无法获取创业板指数据，将使用上证指数替代")
        cy_closes = sh_closes

    trend, strategy, reason, trend_reason, tech_premium, signal_details, confirm_days = detect_trend(sh_closes, cy_closes)

    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60)
    current = sh_closes[-1]
    momentum_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100
    trend_desc = {"up": "上升趋势", "down": "下降趋势", "sideways": "震荡"}.get(trend, "未知")

    print("")
    print("📊 分析结果:")
    print(f"  上证指数: {current:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    print(f"  近20日动量: {momentum_20:.2f}%")
    print(f"  科技溢价（创-上）: {tech_premium}%")
    print("")
    print("📊 信号详情:")
    for detail in signal_details:
        print(f"  {detail}")
    print("")
    print(f"🎯 趋势判断: {trend_desc}")
    print(f"📝 判断依据: {trend_reason}")
    print(f"⏱️ 确认天数: {confirm_days} 天")
    print("")
    print(f"✅ 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("=" * 70)

    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trend": trend,
        "trend_desc": trend_desc,
        "strategy": strategy,
        "reason": reason,
        "confirm_days": confirm_days,
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "momentum_20": momentum_20,
        "tech_premium": tech_premium,
        "signal_summary": signal_details
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print("✅ 结果已保存")


if __name__ == "__main__":
    main()