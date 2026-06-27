#!/usr/bin/env python3
"""
自动判断市场状态并选择策略
5个数据源按优先级依次尝试：Baostock → efinance → 新浪 → 腾讯 → AkShare
趋势判断：双窗口（20天 + 60天）+ ATR动态阈值 + 确认天数机制
"""

import requests
import json
import re
import sys
import os
from datetime import datetime, timedelta

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
            "date,open,high,low,close,volume",
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
        highs = [float(x) for x in data['high'].tolist()]
        lows = [float(x) for x in data['low'].tolist()]
        volumes = [float(x) for x in data['volume'].tolist()] if 'volume' in data.columns else None
        return closes, highs, lows, volumes
    except Exception as e:
        print(f"  Baostock失败: {e}")
        return None, None, None, None


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
        highs = df.iloc[:, 3].tolist()
        lows = df.iloc[:, 4].tolist()
        volumes = df.iloc[:, 5].tolist()
        return closes, highs, lows, volumes
    except Exception as e:
        print(f"  efinance失败: {e}")
        return None, None, None, None


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
        highs = [float(item['high']) for item in data] if 'high' in data[0] else closes
        lows = [float(item['low']) for item in data] if 'low' in data[0] else closes
        return closes, highs, lows, None
    except Exception as e:
        print(f"  新浪财经失败: {e}")
        return None, None, None, None


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
        highs = [float(item[3]) for item in kline_data if len(item) > 3] else closes
        lows = [float(item[4]) for item in kline_data if len(item) > 4] else closes
        return closes, highs, lows, None
    except Exception as e:
        print(f"  腾讯财经失败: {e}")
        return None, None, None, None


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
        highs = df['最高'].values.tolist()
        lows = df['最低'].values.tolist()
        volumes = df['成交量'].values.tolist()
        return closes, highs, lows, volumes
    except Exception as e:
        print(f"  AkShare失败: {e}")
        return None, None, None, None


# ============================================================
# 统一获取函数
# ============================================================

def get_index_data(symbol, days=100):
    if symbol in ["sh000001", "000001"]:
        baostock_code = "sh.000001"
        efinance_code = "000001"
        sina_code = "sh000001"
        tencent_code = "sh000001"
        akshare_code = "000001"
        name = "上证指数"
    elif symbol in ["sz399006", "399006"]:
        baostock_code = "sz.399006"
        efinance_code = "399006"
        sina_code = "sz399006"
        tencent_code = "sz399006"
        akshare_code = "399006"
        name = "创业板指"
    else:
        return None, None, None, None, None

    print(f"  正在获取 {name} 数据...")

    # 1. Baostock
    print("   1️⃣ 尝试 Baostock...")
    closes, highs, lows, volumes = get_index_history_baostock(baostock_code, days)
    if closes:
        print(f"   ✅ Baostock成功: {len(closes)} 个交易日")
        return closes, highs, lows, volumes, name

    # 2. efinance
    print("   2️⃣ 尝试 efinance...")
    closes, highs, lows, volumes = get_index_history_efinance(efinance_code, days)
    if closes:
        print(f"   ✅ efinance成功: {len(closes)} 个交易日")
        return closes, highs, lows, volumes, name

    # 3. 新浪财经
    print("   3️⃣ 尝试 新浪财经...")
    closes, highs, lows, volumes = get_index_history_sina(sina_code, days)
    if closes:
        print(f"   ✅ 新浪财经成功: {len(closes)} 个交易日")
        return closes, highs, lows, volumes, name

    # 4. 腾讯财经
    print("   4️⃣ 尝试 腾讯财经...")
    closes, highs, lows, volumes = get_index_history_tencent(tencent_code, days)
    if closes:
        print(f"   ✅ 腾讯财经成功: {len(closes)} 个交易日")
        return closes, highs, lows, volumes, name

    # 5. AkShare
    print("   5️⃣ 尝试 AkShare...")
    closes, highs, lows, volumes = get_index_history_akshare(akshare_code, days)
    if closes:
        print(f"   ✅ AkShare成功: {len(closes)} 个交易日")
        return closes, highs, lows, volumes, name

    print(f"   ❌ 所有5个数据源均失败")
    return None, None, None, None, None


# ============================================================
# ATR 计算
# ============================================================

def calculate_atr(closes, highs, lows, period=20):
    if len(closes) < period or len(highs) < period or len(lows) < period:
        return 2.0
    tr_list = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i-1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_pct = tr / closes[i] * 100
        tr_list.append(tr_pct)
    if len(tr_list) < period:
        return 2.0
    atr_pct = sum(tr_list[-period:]) / period
    return round(atr_pct, 2)


# ============================================================
# 核心：双窗口趋势判断
# ============================================================

def detect_trend(closes, highs, lows, volumes=None):
    if len(closes) < 60:
        return "sideways", "数据不足", 0, 0, 0, 0, ""

    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    current = closes[-1]

    above_count = sum(1 for c in closes[-20:] if c > ma20)
    above_ratio = above_count / 20 * 100
    momentum_20 = (closes[-1] / closes[-20] - 1) * 100

    atr_pct = calculate_atr(closes, highs, lows, 20)
    extreme_threshold = max(2.0, atr_pct * 2.5)

    volume_confirmation = ""
    if volumes and len(volumes) >= 20:
        avg_volume_20 = sum(volumes[-20:]) / 20
        last_volume = volumes[-1]
        volume_ratio = last_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0
        if volume_ratio > 1.5:
            volume_confirmation = f"放量（{volume_ratio:.2f}倍）"
        elif volume_ratio < 0.7:
            volume_confirmation = f"缩量（{volume_ratio:.2f}倍）"
        else:
            volume_confirmation = f"正常（{volume_ratio:.2f}倍）"

    if ma20 > ma60:
        long_trend = "up"
        long_desc = f"中长期向上（MA20 {ma20:.2f} > MA60 {ma60:.2f}）"
    elif ma20 < ma60:
        long_trend = "down"
        long_desc = f"中长期向下（MA20 {ma20:.2f} < MA60 {ma60:.2f}）"
    else:
        long_trend = "sideways"
        long_desc = "中长期震荡（MA20 ≈ MA60）"

    if above_ratio >= 70:
        strength = "strong"
        strength_desc = f"趋势牢固（{above_count}/20 = {above_ratio:.0f}% 天数在MA20上方）"
    elif above_ratio >= 50:
        strength = "medium"
        strength_desc = f"趋势一般（{above_count}/20 = {above_ratio:.0f}% 天数在MA20上方）"
    else:
        strength = "weak"
        strength_desc = f"趋势较弱（{above_count}/20 = {above_ratio:.0f}% 天数在MA20上方）"

    is_extreme = False
    extreme_desc = ""
    if long_trend == "up" and momentum_20 < -extreme_threshold:
        is_extreme = True
        extreme_desc = f"短期跌幅 {momentum_20:.2f}% 超过阈值 {extreme_threshold:.2f}%（ATR×2.5）"
    elif long_trend == "down" and momentum_20 > extreme_threshold:
        is_extreme = True
        extreme_desc = f"短期反弹 {momentum_20:.2f}% 超过阈值 {extreme_threshold:.2f}%（ATR×2.5）"

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

    if long_trend == "up" and strength in ["strong", "medium"] and not is_extreme:
        base_trend = "up"
        base_reason = f"{long_desc}，{strength_desc}，趋势持续"
    elif long_trend == "down" and strength in ["strong", "medium"] and not is_extreme:
        base_trend = "down"
        base_reason = f"{long_desc}，{strength_desc}，趋势持续"
    else:
        if is_extreme:
            base_trend = "sideways"
            base_reason = f"{long_desc}，{extreme_desc}，转为震荡观察"
        else:
            base_trend = "sideways"
            base_reason = f"{long_desc}，{strength_desc}，按震荡处理"

    if base_trend == prev_trend:
        confirm_days = min(confirm_days + 1, 5)
        final_trend = base_trend
        final_reason = f"{base_reason}（已确认 {confirm_days} 天）"
    else:
        confirm_days = 0
        if confirm_days < 3:
            final_trend = prev_trend
            final_reason = f"{base_reason}（确认天数 {confirm_days}/3，暂不切换）"
        else:
            final_trend = base_trend
            final_reason = base_reason

    state = {
        "trend": final_trend,
        "confirm_days": confirm_days if final_trend == base_trend else 0,
        "last_check": datetime.now().strftime("%Y-%m-%d"),
        "ma20": ma20,
        "ma60": ma60,
        "above_count": above_count,
        "above_ratio": above_ratio,
        "momentum_20": momentum_20,
        "atr_pct": atr_pct,
        "extreme_threshold": extreme_threshold,
        "volume_confirmation": volume_confirmation,
        "base_trend": base_trend
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    return final_trend, final_reason, above_count, above_ratio, momentum_20, atr_pct, volume_confirmation


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 70)
    print("📊 市场状态分析（双窗口 + ATR动态阈值 + 确认天数机制）")
    print("=" * 70)

    sh_closes, sh_highs, sh_lows, sh_volumes, sh_name = get_index_data("sh000001", 100)
    if not sh_closes or len(sh_closes) < 60:
        print("⚠️ 无法获取上证指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return

    cy_closes, cy_highs, cy_lows, cy_volumes, cy_name = get_index_data("sz399006", 100)
    if not cy_closes:
        print("⚠️ 无法获取创业板指数据，将使用上证指数替代")
        cy_closes = sh_closes

    if len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)
    else:
        tech_premium = 0

    trend, trend_reason, above_count, above_ratio, momentum_20, atr_pct, volume_conf = detect_trend(
        sh_closes, sh_highs, sh_lows, sh_volumes
    )
    trend_desc = {"up": "上升趋势", "down": "下降趋势", "sideways": "震荡"}.get(trend, "未知")

    if trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技股强势（溢价 {tech_premium}%）"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = "上升趋势"
    elif trend == "down":
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（等待超跌反弹）"
    else:
        strategy = "rsi_reversion_v1"
        reason = "震荡（均值回归）"

    ma20 = sum(sh_closes[-20:]) / 20
    ma60 = sum(sh_closes[-60:]) / 60
    current = sh_closes[-1]

    print("")
    print("📊 分析结果:")
    print(f"  上证指数: {current:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    print(f"  ATR%: {atr_pct:.2f}%（极端阈值: {max(2.0, atr_pct*2.5):.2f}%）")
    print(f"  近20日涨幅: {momentum_20:.2f}%")
    print(f"  近20日 > MA20 天数: {above_count}/20 ({above_ratio:.0f}%)")
    print(f"  成交量: {volume_conf}")
    print("")
    print(f"🎯 趋势判断: {trend_desc}")
    print(f"📝 判断依据: {trend_reason}")
    print(f"  科技溢价（创-上）: {tech_premium}%")
    print("")
    print(f"✅ 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("=" * 70)

    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)

    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "atr_pct": atr_pct,
        "momentum_20": momentum_20,
        "above_count": above_count,
        "above_ratio": above_ratio,
        "trend": trend,
        "trend_desc": trend_desc,
        "trend_reason": trend_reason,
        "tech_premium": tech_premium,
        "strategy": strategy,
        "reason": reason,
        "volume_confirmation": volume_conf
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print("✅ 结果已保存")


if __name__ == "__main__":
    main()