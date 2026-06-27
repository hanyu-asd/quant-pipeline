#!/usr/bin/env python3
"""
自动判断市场状态并选择策略
5个数据源按优先级依次尝试：Baostock → efinance → 新浪 → 腾讯 → AkShare
哪个成功用哪个
"""

import requests
import json
import re
import sys
from datetime import datetime, timedelta

# ============================================================
# 数据源1：Baostock（最准确，专注A股历史数据）
# ============================================================

def get_index_history_baostock(symbol, days=80):
    """
    使用 Baostock 获取指数历史数据
    symbol: sh.000001（上证）, sz.399006（创业板）
    """
    try:
        import baostock as bs
        import pandas as pd
        
        # 登录
        lg = bs.login()
        if lg.error_code != '0':
            return None
        
        # 计算日期范围
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        
        # 获取数据
        rs = bs.query_history_k_data_plus(
            symbol,
            "date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 不复权
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
# 数据源2：efinance（东方财富，数据准确）
# ============================================================

def get_index_history_efinance(symbol, days=80):
    """
    使用 efinance 获取指数历史数据
    symbol: 000001（上证）, 399006（创业板）
    """
    try:
        import efinance as ef
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        
        df = ef.stock.get_quote_history(
            symbol,
            beg=start_date,
            end=end_date
        )
        
        if df is None or len(df) < 10:
            return None
        
        # efinance 返回的列名可能是中文
        if '收盘' in df.columns:
            closes = df['收盘'].tolist()
        elif 'close' in df.columns:
            closes = df['close'].tolist()
        else:
            # 尝试按位置取
            closes = df.iloc[:, 2].tolist()
        
        return closes
        
    except Exception as e:
        print(f"  efinance失败: {e}")
        return None


# ============================================================
# 数据源3：新浪财经 API
# ============================================================

def get_index_history_sina(symbol, days=80):
    """
    使用新浪财经获取指数历史数据
    symbol: sh000001（上证）, sz399006（创业板）
    """
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
# 数据源4：腾讯财经 API
# ============================================================

def get_index_history_tencent(symbol, days=80):
    """
    使用腾讯财经获取指数历史数据
    symbol: sh000001（上证）, sz399006（创业板）
    """
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
# 数据源5：AkShare（最后备选）
# ============================================================

def get_index_history_akshare(symbol, days=80):
    """
    使用 AkShare 获取指数历史数据
    symbol: 000001（上证）, 399006（创业板）
    """
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
# 统一获取函数：5个数据源按优先级依次尝试
# ============================================================

def get_index_data(symbol, days=80):
    """
    获取指数历史数据，5个数据源按优先级依次尝试
    上证指数: sh000001 / 000001
    创业板指: sz399006 / 399006
    优先级: Baostock → efinance → 新浪 → 腾讯 → AkShare
    """
    # 确定各数据源的代码格式
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
        return None
    
    print(f"  正在获取 {name} 数据...")
    
    # 1. Baostock（最准确）
    print("   1️⃣ 尝试 Baostock...")
    closes = get_index_history_baostock(baostock_code, days)
    if closes:
        print(f"   ✅ Baostock成功: {len(closes)} 个交易日")
        return closes
    
    # 2. efinance（东方财富）
    print("   2️⃣ 尝试 efinance...")
    closes = get_index_history_efinance(efinance_code, days)
    if closes:
        print(f"   ✅ efinance成功: {len(closes)} 个交易日")
        return closes
    
    # 3. 新浪财经
    print("   3️⃣ 尝试 新浪财经...")
    closes = get_index_history_sina(sina_code, days)
    if closes:
        print(f"   ✅ 新浪财经成功: {len(closes)} 个交易日")
        return closes
    
    # 4. 腾讯财经
    print("   4️⃣ 尝试 腾讯财经...")
    closes = get_index_history_tencent(tencent_code, days)
    if closes:
        print(f"   ✅ 腾讯财经成功: {len(closes)} 个交易日")
        return closes
    
    # 5. AkShare（最后备选）
    print("   5️⃣ 尝试 AkShare...")
    closes = get_index_history_akshare(akshare_code, days)
    if closes:
        print(f"   ✅ AkShare成功: {len(closes)} 个交易日")
        return closes
    
    print(f"   ❌ 所有5个数据源均失败")
    return None


# ============================================================
# 市场状态判断
# ============================================================

def calculate_ma(closes, period):
    if len(closes) < period:
        return closes[-1]
    return sum(closes[-period:]) / period


def main():
    print("=" * 60)
    print("📊 市场状态分析（5个数据源备份）")
    print("优先级: Baostock → efinance → 新浪 → 腾讯 → AkShare")
    print("=" * 60)
    
    # 获取上证指数
    sh_closes = get_index_data("sh000001", 80)
    if not sh_closes or len(sh_closes) < 20:
        print("⚠️ 无法获取上证指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return
    
    # 获取创业板指
    cy_closes = get_index_data("sz399006", 80)
    if not cy_closes:
        print("⚠️ 无法获取创业板指数据，将使用上证指数替代")
        cy_closes = sh_closes
    
    # 计算均线
    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60) if len(sh_closes) >= 60 else ma20
    current = sh_closes[-1]
    
    # 趋势判断
    if current > ma20 and ma20 > ma60:
        trend = "up"
        trend_desc = "上升趋势"
    elif current < ma20 and ma20 < ma60:
        trend = "down"
        trend_desc = "下降趋势"
    else:
        trend = "sideways"
        trend_desc = "震荡"
    
    # 科技股溢价（近20日涨幅差）
    tech_premium = 0
    if len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)
    
    # 动量
    momentum = round((sh_closes[-1] / sh_closes[-20] - 1) * 100, 2)
    
    # 选择策略
    if trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技股强势（溢价 {tech_premium}%）"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = f"上升趋势（动量 {momentum}%）"
    elif trend == "down":
        strategy = "rsi_reversion_v1"
        reason = "下降趋势（等待超跌反弹）"
    else:
        strategy = "rsi_reversion_v1"
        reason = "震荡（均值回归）"
    
    # 输出
    print("")
    print("📊 分析结果:")
    print(f"  上证指数: {current:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    print(f"  趋势: {trend_desc}")
    print(f"  科技溢价（创-上）: {tech_premium}%")
    print(f"  动量（近20日）: {momentum}%")
    print("")
    print(f"🎯 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("=" * 60)
    
    # 写入结果
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)
    
    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "trend": trend,
        "trend_desc": trend_desc,
        "tech_premium": tech_premium,
        "momentum": momentum,
        "strategy": strategy,
        "reason": reason
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    print("✅ 结果已保存到 selected_strategy.txt 和 market_state.json")


if __name__ == "__main__":
    main()