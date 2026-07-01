#!/usr/bin/env python3
"""
行业分类多源查询模块
优先级：Tushare → zzshare → AkShare → Baostock → 本地缓存 → 前缀兜底
"""
import json
import os
import sys
from logger import log

CACHE_FILE = "data/industry_cache.json"

# ============================================================
# 1. Tushare（首选，需Token）
# ============================================================
def query_tushare(stock_code):
    try:
        import tushare as ts
        token = os.environ.get('TUSHARE_TOKEN')
        if not token:
            return ""
        pro = ts.pro_api(token)
        suffix = "SH" if stock_code.startswith('6') else "SZ"
        df = pro.stock_basic(ts_code=f"{stock_code}.{suffix}", fields='ts_code,name,industry')
        if df is not None and not df.empty:
            industry = df.iloc[0]['industry']
            return industry if industry else ""
    except Exception as e:
        log("WARNING", f"Tushare 行业查询失败 ({stock_code}): {e}")
    return ""

# ============================================================
# 2. zzshare（无需Token，兼容Tushare）
# ============================================================
def query_zzshare(stock_code):
    try:
        import zzshare as zs
        # 尝试 stock_basic
        df = zs.stock_basic(ts_code=stock_code, fields='industry')
        if df is not None and not df.empty:
            return df.iloc[0]['industry']
    except AttributeError:
        try:
            df = zs.get_stock_info(stock_code)
            if df is not None and 'industry' in df.columns:
                return df.iloc[0]['industry']
        except:
            pass
    except Exception as e:
        log("WARNING", f"zzshare 行业查询失败 ({stock_code}): {e}")
    return ""

# ============================================================
# 3. AkShare
# ============================================================
def query_akshare(stock_code):
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df is not None and not df.empty:
            if '行业' in df['item'].values:
                return df[df['item'] == '行业']['value'].values[0]
    except Exception as e:
        log("WARNING", f"AkShare 行业查询失败 ({stock_code}): {e}")
    return ""

# ============================================================
# 4. Baostock
# ============================================================
def query_baostock(stock_code):
    try:
        import baostock as bs
        if stock_code.startswith('6'):
            code = f"sh.{stock_code}"
        elif stock_code.startswith(('0', '3')):
            code = f"sz.{stock_code}"
        else:
            return ""
        lg = bs.login()
        if lg.error_code != '0':
            return ""
        rs = bs.query_stock_industry(code=code)
        if rs.error_code != '0' or not rs.next():
            bs.logout()
            return ""
        row = rs.get_row_data()
        bs.logout()
        if len(row) >= 4:
            return row[3]
    except Exception as e:
        log("WARNING", f"Baostock 行业查询失败 ({stock_code}): {e}")
    return ""

# ============================================================
# 5. 本地缓存
# ============================================================
def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def query_cache(stock_code):
    cache = load_cache()
    return cache.get(stock_code, "")

# ============================================================
# 6. 终极兜底：根据代码前缀判断
# ============================================================
def query_prefix(stock_code):
    if stock_code.startswith('6'):
        return "传统"   # 沪市主板
    elif stock_code.startswith(('0', '3')):
        return "科技"   # 深市
    else:
        return "未知"

# ============================================================
# 统一入口
# ============================================================
def get_stock_industry(stock_code):
    """
    按优先级顺序获取行业：Tushare → zzshare → AkShare → Baostock → 缓存 → 前缀
    """
    for source, func in [
        ("Tushare", query_tushare),
        ("zzshare", query_zzshare),
        ("AkShare", query_akshare),
        ("Baostock", query_baostock),
        ("缓存", query_cache)
    ]:
        industry = func(stock_code)
        if industry:
            log("DEBUG", f"行业查询 {stock_code} 成功，来源: {source}")
            return industry
    # 终极兜底
    return query_prefix(stock_code)

# ============================================================
# 提供给其他模块的接口（向后兼容）
# ============================================================
def _query_stock_industry_baostock(stock_code):
    """向后兼容旧版调用"""
    return get_stock_industry(stock_code)

if __name__ == "__main__":
    # 简单测试
    if len(sys.argv) > 1:
        code = sys.argv[1]
        print(f"{code} -> {get_stock_industry(code)}")
    else:
        print("用法: python industry_fetcher.py <股票代码>")