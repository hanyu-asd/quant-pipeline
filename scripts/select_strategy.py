#!/usr/bin/env python3
"""
双窗口趋势判断 + 多信号验证
5个数据源备份：Baostock → efinance → 新浪 → 腾讯 → AkShare
判断依据：MA20/MA60 + 动量 + 确认天数 + 科技溢价 + 多信号（技术面/资金面/情绪面）
"""

import requests
import json
import re
import os
import sys
from datetime import datetime, timedelta

# 导入信号模块
from signals import aggregate_all_signals

STATE_FILE = "trend_state.json"


# ============================================================
# 数据源1：Baostock
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
    except Exception as e:
        print(f"  Baostock失败: {e}")
        return None


# ============================================================
# 数据源2：efinance
# ============================================================

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
    except Exception as e:
        print(f"  efinance失败: {e}")
        return None


# ============================================================
# 数据源3：新浪财经
# ============================================================

def get_index_history_sina(symbol, days=100):
    try:
        url = f"https://quotes.sina.com.cn/stock/api/json_v2.php/var/stock_day?symbol={symbol}&page=1&num={days}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn/'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or len(data) < 10:
            return None
        closes = [float(item['close']) for item in data]
        return closes
    except Exception as e:
        print(f"  新浪财经失败: {e}")
        return None


# ============================================================
# 数据源4：腾讯财经
# ============================================================

def get_index_history_tencent(symbol, days=100):
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
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
    except Exception as e:
        print(f"  腾讯财经失败: {e}")
        return None


# ============================================================
# 数据源5：AkShare
# ============================================================

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
    except Exception as e:
        print(f"  AkShare失败: {e}")
        return None


# ============================================================
# 统一获取函数
# ============================================================

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

    # 1. Baostock
    print("   1️⃣ 尝试 Baostock...")
    closes = get_index_history_baostock(code_map["baostock"], days)
    if closes:
        print(f"   ✅ Baostock成功: {len(closes)} 个交易日")
        return closes

    # 2. efinance
    print("   2️⃣ 尝试 efinance...")
    closes = get_index_history_efinance(code_map["efinance"], days)
    if closes:
        print(f"   ✅ efinance成功: {len(closes)} 个交易日")
        return closes

    # 3. 新浪财经
    print("   3️⃣ 尝试 新浪财经...")
    closes = get_index_history_sina(code_map["sina"], days)
    if closes:
        print(f"   ✅ 新浪财经成功: {len(closes)} 个交易日")
        return closes

    # 4. 腾讯财经
    print("   4️⃣ 尝试 腾讯财经...")
    closes = get_index_history_tencent(code_map["tencent"], days)
    if closes:
        print(f"   ✅ 腾讯财经成功: {len(closes)} 个交易日")
        return closes

    # 5. AkShare
    print("   5️⃣ 尝试 AkShare...")
    closes = get_index_history_akshare(code_map["akshare"], days)
    if closes:
        print(f"   ✅ AkShare成功: {len(closes)} 个交易日")
        return closes

    print(f"   ❌ 所有5个数据源均失败")
    return None


# ============================================================
# 核心函数：双窗口趋势判断 + 信号验证
# ============================================================

def calculate_ma(closes, period):
    if len(closes) < period:
        return closes[-1]
    return sum(closes[-period:]) / period


def detect_trend(sh_closes, cy_closes):
    """
    双窗口趋势判断 + 多信号验证
    """
    if not sh_closes or len(sh_closes) < 60:
        return "sideways", "rsi_reversion_v1", "数据不足", "数据不足", 0, []

    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60)
    current = sh_closes[-1]
    momentum_20 = (sh_closes[-1] / sh_closes[-20] - 1) * 100

    # ============================================================
    # 1. 双窗口基础判断
    # ============================================================
    if ma20 > ma60:
        long_trend = "up"
        long_desc = f"MA20({ma20:.2f}) > MA60({ma60:.2f})"
    elif ma20 < ma60:
        long_trend = "down"
        long_desc = f"MA20({ma20:.2f}) < MA60({ma60:.2f})"
    else:
        long_trend = "sideways"
        long_desc = "MA20 ≈ MA60"

    # 短期动量修正
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

    # 确认天数机制（3天确认）
    prev_trend = "sideways"
    confirm_days = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                prev_state = json.load(f)
                prev_trend = prev_state.get('trend', 'sideways')
                confirm_days = prev_state.get('confirm_days', 0)
        except:
            pass

    if base_trend == prev_trend:
        confirm_days = min(confirm_days + 1, 5)
        final_trend = base_trend
        trend_reason = f"{base_reason}（已确认 {confirm_days} 天）"
    else:
        confirm_days = 0
        final_trend = prev_trend
        trend_reason = f"{base_reason}（确认天数 {confirm_days}/3，暂不切换，保持 {prev_trend}）"
        if confirm_days >= 3:
            final_trend = base_trend
            trend_reason = f"{base_reason}（已确认 {confirm_days} 天，切换至 {base_trend}）"

    # ============================================================
    # 2. 多信号综合评分
    # ============================================================
    print("\n📊 信号采集:")
    total_score, signal_details = aggregate_all_signals(sh_closes)

    # 修正判断：如果双窗口判断为震荡，但信号评分强烈，则修正
    if final_trend == "sideways" and total_score >= 50:
        final_trend = "up"
        trend_reason = f"双窗口震荡，但多信号共振确认上升（综合评分 {total_score}）"
    elif final_trend == "sideways" and total_score <= -50:
        final_trend = "down"
        trend_reason = f"双窗口震荡，但多信号共振确认下降（综合评分 {total_score}）"
    else:
        trend_reason = f"{trend_reason}（综合评分 {total_score}）"

    # ============================================================
    # 3. 科技溢价
    # ============================================================
    tech_premium = 0
    if cy_closes and len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)

    # ============================================================
    # 4. 策略选择
    # ============================================================
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
        "confirm_days": confirm_days if final_trend == base_trend else 0,
        "last_check": datetime.now().strftime("%Y-%m-%d"),
        "ma20": ma20,
        "ma60": ma60,
        "momentum_20": momentum_20,
        "tech_premium": tech_premium,
        "total_score": total_score,
        "base_trend": base_trend
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    return final_trend, strategy, reason, trend_reason, tech_premium, signal_details


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 70)
    print("📊 双窗口趋势判断 + 多信号验证")
    print("=" * 70)

    # 获取上证指数
    sh_closes = get_index_data("sh000001", 100)
    if not sh_closes:
        print("⚠️ 无法获取指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return

    # 获取创业板指
    cy_closes = get_index_data("sz399006", 100)
    if not cy_closes:
        print("⚠️ 无法获取创业板指数据，将使用上证指数替代")
        cy_closes = sh_closes

    # 趋势判断
    trend, strategy, reason, trend_reason, tech_premium, signal_details = detect_trend(sh_closes, cy_closes)

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
    print("")
    print(f"✅ 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("=" * 70)

    # 输出策略名
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

    # 输出市场状态
    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trend": trend,
        "trend_desc": trend_desc,
        "strategy": strategy,
        "reason": reason,
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "momentum_20": momentum_20,
        "tech_premium": tech_premium,
        "signal_summary": signal_details
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print("✅ 结果已保存到 selected_strategy.txt 和 market_state.json")


if __name__ == "__main__":
    main()