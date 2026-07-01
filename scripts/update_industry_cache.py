#!/usr/bin/env python3
"""
更新行业分类本地缓存
从 Tushare 获取全量股票行业数据，保存到 data/industry_cache.json
建议每周运行一次（或当有新股上市时手动运行）
"""
import json
import os
import sys
import tushare as ts

CACHE_FILE = "data/industry_cache.json"

def update_cache():
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        print("❌ 未设置 TUSHARE_TOKEN，无法更新缓存")
        print("请在环境变量中设置 TUSHARE_TOKEN，或在 GitHub Secrets 中配置")
        sys.exit(1)
    pro = ts.pro_api(token)
    print("⏳ 正在从 Tushare 获取全量股票信息...")
    try:
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry')
    except Exception as e:
        print(f"❌ Tushare 请求失败: {e}")
        sys.exit(1)
    if df.empty:
        print("❌ 返回数据为空")
        sys.exit(1)
    cache = {}
    for _, row in df.iterrows():
        code = row['ts_code'].split('.')[0]  # 如 '000001.SZ' -> '000001'
        industry = row['industry']
        if industry:
            cache[code] = industry
    os.makedirs('data', exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    print(f"✅ 已缓存 {len(cache)} 只股票的行业信息到 {CACHE_FILE}")

if __name__ == "__main__":
    update_cache()