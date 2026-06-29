#!/usr/bin/env python3
"""
动态主线识别模块
用ETF持仓重合度自动分组，识别当前市场最强主线子赛道
"""

import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# 配置：ETF赛道分组（自动计算+人工兜底）
# ============================================================

# ETF映射表：代码 → 名称 → 分组
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

# 赛道→策略映射
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

# 默认策略
DEFAULT_STRATEGY = "balanced_alpha"


# ============================================================
# 数据源函数（4层备份）
# ============================================================

def get_etf_data_baostock(code, days=80):
    """Baostock获取ETF数据"""
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
        print(f"   ⚠️ Baostock获取{code}失败: {e}")
        return None


def get_etf_data_tushare(code, days=80):
    """Tushare获取ETF数据（不同源备选）"""
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
        print(f"   ⚠️ Tushare获取{code}失败: {e}")
        return None


def get_etf_data_akshare(code, days=80):
    """AkShare获取ETF数据"""
    try:
        import akshare as ak
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        return df['收盘'].values.tolist()
    except Exception as e:
        print(f"   ⚠️ AkShare获取{code}失败: {e}")
        return None


def get_etf_data_efinance(code, days=80):
    """efinance获取ETF数据（兜底）"""
    try:
        import efinance as ef
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = ef.fund.get_fund_history(code, start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        return df['close'].values.tolist()
    except Exception as e:
        print(f"   ⚠️ efinance获取{code}失败: {e}")
        return None


def get_etf_data(code, days=80):
    """获取ETF数据，4层备份"""
    print(f"   📊 获取ETF {code} 数据...")
    closes = get_etf_data_baostock(code, days)
    if closes:
        print(f"      ✅ Baostock成功: {len(closes)}个交易日")
        return closes
    closes = get_etf_data_tushare(code, days)
    if closes:
        print(f"      ✅ Tushare成功: {len(closes)}个交易日")
        return closes
    closes = get_etf_data_akshare(code, days)
    if closes:
        print(f"      ✅ AkShare成功: {len(closes)}个交易日")
        return closes
    closes = get_etf_data_efinance(code, days)
    if closes:
        print(f"      ✅ efinance成功: {len(closes)}个交易日")
        return closes
    print(f"      ❌ 所有数据源均失败")
    return None


def get_benchmark_data(days=80):
    """获取大盘基准数据（沪深300）"""
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
        print(f"   ⚠️ 获取基准数据失败: {e}")
        return None


# ============================================================
# 核心计算函数
# ============================================================

def calculate_relative_strength(etf_closes, benchmark_closes):
    """计算相对强度"""
    if not etf_closes or not benchmark_closes:
        return 0, 0, 0
    if len(etf_closes) < 5 or len(benchmark_closes) < 5:
        return 0, 0, 0
    etf_5 = (etf_closes[-1] / etf_closes[-6] - 1) * 100 if len(etf_closes) > 5 else 0
    etf_20 = (etf_closes[-1] / etf_closes[-21] - 1) * 100 if len(etf_closes) > 20 else 0
    etf_60 = (etf_closes[-1] / etf_closes[-61] - 1) * 100 if len(etf_closes) > 60 else 0
    bench_5 = (benchmark_closes[-1] / benchmark_closes[-6] - 1) * 100 if len(benchmark_closes) > 5 else 0
    bench_20 = (benchmark_closes[-1] / benchmark_closes[-21] - 1) * 100 if len(benchmark_closes) > 20 else 0
    bench_60 = (benchmark_closes[-1] / benchmark_closes[-61] - 1) * 100 if len(benchmark_closes) > 60 else 0
    return etf_5 - bench_5, etf_20 - bench_20, etf_60 - bench_60


def calculate_atr(closes, period=20):
    """计算ATR（平均真实波幅百分比）"""
    if len(closes) < period + 1:
        return 0
    tr_list = []
    for i in range(1, len(closes)):
        if i < period:
            continue
        high = closes[i]
        low = closes[i-1]
        tr = high - low
        tr_pct = tr / closes[i] * 100
        tr_list.append(tr_pct)
    return sum(tr_list[-period:]) / period if tr_list else 0


# ============================================================
# 主线识别主函数
# ============================================================

def identify_mainline():
    """
    识别当前市场主线
    返回: (主线名称, 策略, 置信度, 确认天数)
    """
    benchmark = get_benchmark_data()
    if not benchmark:
        print("⚠️ 无法获取基准数据，使用默认策略")
        return None, DEFAULT_STRATEGY, 0, 0
    
    # 计算每个ETF的相对强度
    scores = []
    for code, info in ETF_MAP.items():
        etf = get_etf_data(code)
        if not etf:
            continue
        rs_5, rs_20, rs_60 = calculate_relative_strength(etf, benchmark)
        combined = rs_5 * 0.3 + rs_20 * 0.5 + rs_60 * 0.2
        scores.append({
            "code": code,
            "name": info["name"],
            "group": info["group"],
            "rs_5": rs_5,
            "rs_20": rs_20,
            "rs_60": rs_60,
            "combined": combined
        })
    
    if not scores:
        print("⚠️ 无法获取任何ETF数据，使用默认策略")
        return None, DEFAULT_STRATEGY, 0, 0
    
    # 按综合评分排序
    scores = sorted(scores, key=lambda x: x["combined"], reverse=True)
    top = scores[0]
    
    # 检查前5名是否属于同一分组
    top_groups = [s["group"] for s in scores[:5]]
    group_counts = {}
    for g in top_groups:
        group_counts[g] = group_counts.get(g, 0) + 1
    
    # 如果前5名中有3个以上属于同一分组，确认主线
    main_group = None
    for group, count in group_counts.items():
        if count >= 3:
            main_group = group
            break
    
    if main_group:
        # 计算主线的平均相对强度
        group_scores = [s["combined"] for s in scores if s["group"] == main_group]
        avg_strength = sum(group_scores) / len(group_scores) if group_scores else 0
        
        # 根据强度决定确认天数
        if avg_strength > 7:
            confirm_days = 2
        elif avg_strength > 3:
            confirm_days = 3
        else:
            confirm_days = 5
        
        # 获取策略
        strategy = STRATEGY_MAP.get(main_group, DEFAULT_STRATEGY)
        confidence = min(100, 50 + avg_strength * 5)
        
        print(f"   ✅ 当前主线: {main_group}")
        print(f"   📊 代表ETF: {top['name']}({top['code']})")
        print(f"   📊 相对强度: {avg_strength:.2f}%")
        print(f"   📊 确认天数: {confirm_days}天")
        print(f"   📊 置信度: {confidence:.0f}%")
        print(f"   📈 使用策略: {strategy}")
        
        return main_group, strategy, confidence, confirm_days
    
    # 无明确主线
    print("   ⚠️ 无明确主线，使用默认策略")
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
    print(f"\n✅ 结果已保存到 mainline_result.json")