#!/usr/bin/env python3
"""
动态主线识别模块
v6.5 - 集成 TickFlow 作为 ETF 历史数据源
"""
import json
import sys
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from logger import log

# ============================================================
# 配置：ETF赛道分组（稳定沪市ETF）
# ============================================================
ETF_MAP = {
    # 半导体
    "512480": {"name": "半导体ETF", "group": "半导体", "backup": "512760"},
    "512760": {"name": "芯片ETF", "group": "半导体", "backup": "512480"},
    # AI算力
    "588000": {"name": "科创50ETF", "group": "AI算力", "backup": None},
    "515050": {"name": "5GETF", "group": "AI算力", "backup": None},
    # 软件
    "515230": {"name": "信创ETF", "group": "软件", "backup": "512720"},
    "512720": {"name": "计算机ETF", "group": "软件", "backup": "515230"},
    # 通信
    "515880": {"name": "通信ETF", "group": "通信", "backup": None},
    # 光伏
    "515790": {"name": "光伏ETF", "group": "光伏", "backup": None},
    "516160": {"name": "新能源ETF", "group": "光伏", "backup": None},
    # 新能源车
    "515030": {"name": "新能源车ETF", "group": "新能源车", "backup": None},
    # 消费
    "512690": {"name": "酒ETF", "group": "消费", "backup": None},
    # 医药
    "512010": {"name": "医药ETF", "group": "医药", "backup": None},
    # 有色
    "512400": {"name": "有色ETF", "group": "有色", "backup": None},
    # 金融
    "512800": {"name": "银行ETF", "group": "金融", "backup": None},
    "512880": {"name": "证券ETF", "group": "金融", "backup": None},
    # 红利
    "512890": {"name": "红利低波ETF", "group": "红利", "backup": None},
    "515080": {"name": "中证红利ETF", "group": "红利", "backup": None},
}

STRATEGY_MAP = {
    "半导体": "momentum_quality",
    "AI算力": "momentum_quality",
    "软件": "momentum_quality",
    "通信": "momentum_quality",
    "光伏": "momentum_quality",
    "新能源车": "momentum_quality",
    "消费": "quality_value",
    "医药": "quality_value",
    "红利": "quality_value",
    "有色": "dual_low",
    "金融": "balanced_alpha",
}
DEFAULT_STRATEGY = "balanced_alpha"

ETF_STATUS = {}


def init_etf_status():
    for code in ETF_MAP:
        ETF_STATUS[code] = {"fail_count": 0, "status": "active", "last_switch": None}


init_etf_status()


# ============================================================
# ETF 数据源：TickFlow（新增）
# ============================================================
def get_etf_data_tickflow(code, days=80):
    try:
        import tickflow as tf
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        df = tf.get_daily(symbol=code, market='cn',
                          start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        return df['close'].values.tolist()
    except Exception as e:
        log("WARNING", f"[TickFlow] 获取 {code} 失败: {e}")
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
        suffix = "SH" if code.startswith('6') else "SZ"
        df = pro.fund_daily(ts_code=f"{code}.{suffix}", start_date=start_date, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        df = df.sort_values('trade_date')
        return df['close'].values.tolist()
    except Exception as e:
        log("WARNING", f"[Tushare] 获取 {code} 失败: {e}")
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
        log("WARNING", f"[AkShare] 获取 {code} 失败: {e}")
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


def _fetch_etf_from_baostock_with_session(code, days, bs_session):
    try:
        import baostock as bs
        prefix = "sh" if code.startswith('6') else "sz"
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y-%m-%d")
        rs = bs.query_history_k_data_plus(
            f"{prefix}.{code}", "date,close",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3",
            connection=bs_session
        )
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) < 60:
            return None
        return [float(x) for x in data['close'].tolist()]
    except Exception as e:
        log("WARNING", f"[Baostock会话] 获取 {code} 失败: {e}")
        return None


def get_etf_data_with_fallback(code, days, bs_session=None):
    # 1. Baostock 会话
    if bs_session is not None:
        closes = _fetch_etf_from_baostock_with_session(code, days, bs_session)
        if closes:
            log("DEBUG", f"  ✅ Baostock会话成功: {code}")
            ETF_STATUS[code]["fail_count"] = 0
            ETF_STATUS[code]["status"] = "active"
            return closes
        else:
            ETF_STATUS[code]["fail_count"] += 1
            log("WARNING", f"  Baostock会话获取 {code} 失败 (连续{ETF_STATUS[code]['fail_count']}次)")
    else:
        log("WARNING", f"  无Baostock会话，跳过主源")

    # 2. TickFlow
    log("WARNING", f"  尝试TickFlow: {code}")
    closes = get_etf_data_tickflow(code, days)
    if closes:
        log("INFO", f"  ✅ TickFlow成功: {len(closes)}个交易日")
        ETF_STATUS[code]["fail_count"] = 0
        return closes

    # 3. 备选ETF切换（连续失败>=3）
    if ETF_STATUS[code]["fail_count"] >= 3 and ETF_MAP[code].get("backup"):
        backup_code = ETF_MAP[code]["backup"]
        log("INFO", f"  切换到备选ETF {backup_code}")
        ETF_STATUS[code]["status"] = "degraded"
        ETF_STATUS[code]["last_switch"] = datetime.now().strftime("%Y-%m-%d")
        closes = get_etf_data_tushare(backup_code, days)
        if not closes:
            closes = get_etf_data_akshare(backup_code, days)
        if closes:
            log("INFO", f"  ✅ 备选 {backup_code} 成功")
            ETF_STATUS[code]["fail_count"] = 0
            return closes

    # 4. Tushare
    log("WARNING", f"  尝试Tushare: {code}")
    closes = get_etf_data_tushare(code, days)
    if closes:
        log("INFO", f"  ✅ Tushare成功: {len(closes)}个交易日")
        ETF_STATUS[code]["fail_count"] = 0
        return closes

    # 5. AkShare
    log("WARNING", f"  尝试AkShare: {code}")
    closes = get_etf_data_akshare(code, days)
    if closes:
        log("INFO", f"  ✅ AkShare成功: {len(closes)}个交易日")
        ETF_STATUS[code]["fail_count"] = 0
        return closes

    log("ERROR", f"  所有数据源均失败: {code}")
    return None


def calculate_relative_strength(etf_closes, benchmark_closes):
    if not etf_closes or not benchmark_closes or len(etf_closes) < 5 or len(benchmark_closes) < 5:
        return 0, 0, 0
    etf_5 = (etf_closes[-1] / etf_closes[-6] - 1) * 100 if len(etf_closes) > 5 else 0
    etf_20 = (etf_closes[-1] / etf_closes[-21] - 1) * 100 if len(etf_closes) > 20 else 0
    etf_60 = (etf_closes[-1] / etf_closes[-61] - 1) * 100 if len(etf_closes) > 60 else 0
    bench_5 = (benchmark_closes[-1] / benchmark_closes[-6] - 1) * 100 if len(benchmark_closes) > 5 else 0
    bench_20 = (benchmark_closes[-1] / benchmark_closes[-21] - 1) * 100 if len(benchmark_closes) > 20 else 0
    bench_60 = (benchmark_closes[-1] / benchmark_closes[-61] - 1) * 100 if len(benchmark_closes) > 60 else 0
    return etf_5 - bench_5, etf_20 - bench_20, etf_60 - bench_60


def identify_mainline():
    benchmark = get_benchmark_data()
    if not benchmark:
        log("WARNING", "无法获取基准，使用默认策略")
        return {
            "main_group": None,
            "strategy": DEFAULT_STRATEGY,
            "confidence": 0,
            "confirm_days": 0,
            "relative_strength": 0,
            "etf_count": 0,
            "ranking": 0
        }

    import baostock as bs
    log("INFO", "登录Baostock获取ETF数据...")
    lg = bs.login()
    if lg.error_code != '0':
        log("WARNING", f"Baostock登录失败: {lg.error_msg}，将仅使用TickFlow/Tushare/AkShare")
        bs_session = None
    else:
        bs_session = lg

    scores = []
    for code, info in ETF_MAP.items():
        if ETF_STATUS.get(code, {}).get("status") == "disabled":
            continue
        etf = get_etf_data_with_fallback(code, 80, bs_session)
        if not etf:
            continue
        rs_5, rs_20, rs_60 = calculate_relative_strength(etf, benchmark)
        combined = rs_5 * 0.3 + rs_20 * 0.5 + rs_60 * 0.2
        scores.append({
            "code": code,
            "name": info["name"],
            "group": info["group"],
            "combined": combined
        })
        time.sleep(0.3)  # 频率控制

    if bs_session is not None:
        bs.logout()
        log("INFO", "Baostock登出")

    if not scores:
        log("WARNING", "无ETF数据，使用默认策略")
        return {
            "main_group": None,
            "strategy": DEFAULT_STRATEGY,
            "confidence": 0,
            "confirm_days": 0,
            "relative_strength": 0,
            "etf_count": 0,
            "ranking": 0
        }

    scores = sorted(scores, key=lambda x: x["combined"], reverse=True)
    top_groups = [s["group"] for s in scores[:5]]
    group_counts = {}
    for g in top_groups:
        group_counts[g] = group_counts.get(g, 0) + 1

    main_group = None
    confidence = 0
    confirm_days = 0
    main_strength = 0
    etf_count = 0
    ranking = 0

    for group, count in group_counts.items():
        if count >= 3:
            main_group = group
            confidence = 80
            group_scores = [s["combined"] for s in scores if s["group"] == group]
            main_strength = sum(group_scores) / len(group_scores) if group_scores else 0
            etf_count = len(group_scores)
            confirm_days = 2 if main_strength > 7 else 3
            break

    if not main_group:
        for group, count in group_counts.items():
            if count >= 2:
                group_scores = [s["combined"] for s in scores if s["group"] == group]
                avg_strength = sum(group_scores) / len(group_scores) if group_scores else 0
                if avg_strength > 5:
                    main_group = group
                    confidence = 60
                    main_strength = avg_strength
                    etf_count = len(group_scores)
                    confirm_days = 3
                    break

    if not main_group:
        log("INFO", "无明确主线，使用默认策略")
        return {
            "main_group": None,
            "strategy": DEFAULT_STRATEGY,
            "confidence": 0,
            "confirm_days": 0,
            "relative_strength": 0,
            "etf_count": 0,
            "ranking": 0
        }

    strategy = STRATEGY_MAP.get(main_group, DEFAULT_STRATEGY)
    same_strategy_groups = [g for g, s in STRATEGY_MAP.items() if s == strategy and g in group_counts]
    if len(same_strategy_groups) > 1:
        group_avg = {}
        for g in same_strategy_groups:
            gs = [s["combined"] for s in scores if s["group"] == g]
            group_avg[g] = sum(gs) / len(gs) if gs else 0
        main_group = max(group_avg, key=group_avg.get)
        main_strength = group_avg[main_group]
        log("INFO", f"主线去重: {same_strategy_groups} → 选择 {main_group} (强度 {main_strength:.2f}%)")

    group_avg_all = {}
    for group in group_counts.keys():
        gs = [s["combined"] for s in scores if s["group"] == group]
        group_avg_all[group] = sum(gs) / len(gs) if gs else 0
    sorted_groups = sorted(group_avg_all.items(), key=lambda x: x[1], reverse=True)
    ranking = [g[0] for g in sorted_groups].index(main_group) + 1

    log("INFO", f"当前主线: {main_group}, 强度: {main_strength:.2f}%, 置信度: {confidence}%, 策略: {strategy}")
    return {
        "main_group": main_group,
        "strategy": strategy,
        "confidence": confidence,
        "confirm_days": confirm_days,
        "relative_strength": main_strength,
        "etf_count": etf_count,
        "ranking": ranking
    }


if __name__ == "__main__":
    result = identify_mainline()
    with open("mainline_result.json", "w") as f:
        json.dump(result, f, indent=2)
    log("INFO", "主线识别结果已保存到 mainline_result.json")