#!/usr/bin/env python3
"""
动态主线识别模块
用ETF持仓重合度自动分组，识别当前市场最强主线子赛道
v6.1 - 增强异常处理和日志
"""
import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from logger import log

# ============================================================
# 配置：ETF赛道分组
# ============================================================
ETF_MAP = {
    "512480": {"name": "半导体ETF", "group": "半导体"},
    "159995": {"name": "芯片ETF", "group": "半导体"},
    "588000": {"name": "科创50ETF", "group": "AI算力"},
    "515050": {"name": "5GETF", "group": "AI算力"},
    "159852": {"name": "软件ETF", "group": "软件"},
    "515230": {"name": "信创ETF", "group": "软件"},
    "515880": {"name": "通信ETF", "group": "通信"},
    "159732": {"name": "消费电子ETF", "group": "消费电子"},
    "515790": {"name": "光伏ETF", "group": "光伏"},
    "516160": {"name": "新能源ETF", "group": "光伏"},
    "515030": {"name": "新能源车ETF", "group": "新能源车"},
    "512690": {"name": "酒ETF", "group": "消费"},
    "512010": {"name": "医药ETF", "group": "医药"},
    "512400": {"name": "有色ETF", "group": "有色"},
    "512800": {"name": "银行ETF", "group": "金融"},
    "512880": {"name": "证券ETF", "group": "金融"},
}

STRATEGY_MAP = {
    "半导体": "momentum_quality",
    "AI算力": "momentum_quality",
    "软件": "momentum_quality",
    "通信": "momentum_quality",
    "消费电子": "momentum_quality",
    "光伏": "momentum_quality",
    "新能源车": "momentum_quality",
    "消费": "quality_value",
    "医药": "quality_value",
    "有色": "dual_low",
    "金融": "balanced_alpha",
}
DEFAULT_STRATEGY = "balanced_alpha"

# ============================================================
# 数据源函数（3层备份）
# ============================================================
def get_etf_data_baostock(code, days=80):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_history_k_data_plus(
            f"sh.{code}", "date,close",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) < 60:
            return None
        return [float(x) for x in data['close'].tolist()]
    except Exception as e:
        log("WARNING", f"[get_etf_data_baostock] 获取 {code} 失败: {e}")
        return None

def get_etf_data_tushare(code, days=80):
    try:
        import tushare as ts
        import os
        token = os.environ.get('TUSHARE_TOKEN')
        if not token:
            return None
        pro = ts.pro_api(token)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d")
        df = pro.fund_daily(ts_code=f"{code}.SH", start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        df = df.sort_values('trade_date')
        return df['close'].values.tolist()
    except Exception as e:
        log("WARNING", f"[get_etf_data_tushare] 获取 {code} 失败: {e}")
        return None

def get_etf_data_akshare(code, days=80):
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        return df['收盘'].values.tolist()
    except Exception as e:
        log("WARNING", f"[get_etf_data_akshare] 获取 {code} 失败: {e}")
        return None

def get_etf_data(code, days=80):
    log("INFO", f"获取ETF {code} 数据...")
    closes = get_etf_data_baostock(code, days)
    if closes:
        log("INFO", f"  ✅ Baostock成功: {len(closes)}个交易日")
        return closes
    log("WARNING", f"  Baostock失败，切换Tushare")
    closes = get_etf_data_tushare(code, days)
    if closes:
        log("INFO", f"  ✅ Tushare成功: {len(closes)}个交易日")
        return closes
    log("WARNING", f"  Tushare失败，切换AkShare")
    closes = get_etf_data_akshare(code, days)
    if closes:
        log("INFO", f"  ✅ AkShare成功: {len(closes)}个交易日")
        return closes
    log("ERROR", f"  所有数据源均失败: {code}")
    return None

def get_benchmark_data(days=80):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_history_k_data_plus(
            "sh.000300", "date,close",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) < 60:
            return None
        return [float(x) for x in data['close'].tolist()]
    except Exception as e:
        log("WARNING", f"[get_benchmark_data] 获取基准失败: {e}")
        return None

# ============================================================
# 核心计算
# ============================================================
def calculate_relative_strength(etf_closes, benchmark_closes):
    if not etf_closes or not benchmark_closes or len(etf_closes)<5 or len(benchmark_closes)<5:
        return 0,0,0
    etf_5 = (etf_closes[-1]/etf_closes[-6]-1)*100 if len(etf_closes)>5 else 0
    etf_20 = (etf_closes[-1]/etf_closes[-21]-1)*100 if len(etf_closes)>20 else 0
    etf_60 = (etf_closes[-1]/etf_closes[-61]-1)*100 if len(etf_closes)>60 else 0
    bench_5 = (benchmark_closes[-1]/benchmark_closes[-6]-1)*100 if len(benchmark_closes)>5 else 0
    bench_20 = (benchmark_closes[-1]/benchmark_closes[-21]-1)*100 if len(benchmark_closes)>20 else 0
    bench_60 = (benchmark_closes[-1]/benchmark_closes[-61]-1)*100 if len(benchmark_closes)>60 else 0
    return etf_5-bench_5, etf_20-bench_20, etf_60-bench_60

def identify_mainline():
    benchmark = get_benchmark_data()
    if not benchmark:
        log("WARNING", "无法获取基准，使用默认策略")
        return None, DEFAULT_STRATEGY, 0, 0
    scores = []
    for code, info in ETF_MAP.items():
        etf = get_etf_data(code)
        if not etf:
            continue
        rs_5, rs_20, rs_60 = calculate_relative_strength(etf, benchmark)
        combined = rs_5*0.3 + rs_20*0.5 + rs_60*0.2
        scores.append({
            "code": code,
            "name": info["name"],
            "group": info["group"],
            "combined": combined
        })
    if not scores:
        log("WARNING", "无ETF数据，使用默认策略")
        return None, DEFAULT_STRATEGY, 0, 0
    scores = sorted(scores, key=lambda x: x["combined"], reverse=True)
    top = scores[0]
    top_groups = [s["group"] for s in scores[:5]]
    group_counts = {}
    for g in top_groups:
        group_counts[g] = group_counts.get(g, 0) + 1
    main_group = None
    for group, count in group_counts.items():
        if count >= 3:
            main_group = group
            break
    if main_group:
        group_scores = [s["combined"] for s in scores if s["group"] == main_group]
        avg_strength = sum(group_scores)/len(group_scores) if group_scores else 0
        if avg_strength > 7:
            confirm_days = 2
        elif avg_strength > 3:
            confirm_days = 3
        else:
            confirm_days = 5
        strategy = STRATEGY_MAP.get(main_group, DEFAULT_STRATEGY)
        confidence = min(100, 50 + avg_strength*5)
        log("INFO", f"当前主线: {main_group}, 强度: {avg_strength:.2f}%, 置信度: {confidence:.0f}%, 策略: {strategy}")
        return main_group, strategy, confidence, confirm_days
    log("INFO", "无明确主线，使用默认策略")
    return None, DEFAULT_STRATEGY, 0, 0

if __name__ == "__main__":
    group, strategy, confidence, days = identify_mainline()
    with open("mainline_result.json", "w") as f:
        json.dump({
            "group": group,
            "strategy": strategy,
            "confidence": confidence,
            "confirm_days": days,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, f, indent=2)
    log("INFO", "主线识别结果已保存到 mainline_result.json")