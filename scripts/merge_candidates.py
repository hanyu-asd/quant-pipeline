#!/usr/bin/env python3
"""
合并主线候选与全市场候选
- 读取 AlphaSift 全市场扫描结果（shared/candidates_all.json）
- 根据主线分组，从候选股中筛选属于主线的股票
- 主线候选加分，去重排序
"""
import json
import os
import sys
from scripts.industry_fetcher import get_stock_industry

# 主线分组 → 行业关键词映射（与 workflow 中的过滤保持一致）
MAINLINE_INDUSTRY_MAP = {
    "半导体": ["半导体", "电子", "芯片", "集成电路"],
    "AI算力": ["计算机", "通信", "电子", "人工智能", "AI"],
    "软件": ["计算机", "软件", "信息技术"],
    "通信": ["通信", "5G", "光通信"],
    "光伏": ["光伏", "太阳能", "新能源"],
    "新能源车": ["汽车", "新能源车", "锂电池"],
    "消费": ["食品饮料", "白酒", "消费"],
    "医药": ["医药", "生物", "医疗"],
    "有色": ["有色金属", "金属", "矿产"],
    "金融": ["银行", "证券", "保险", "金融"],
    "红利": ["银行", "公用事业", "红利"],
}

def load_candidates(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('picks', [])
    except Exception as e:
        print(f"⚠️ 读取候选文件失败: {e}")
        return []

def get_mainline_industries(main_group):
    return MAINLINE_INDUSTRY_MAP.get(main_group, [])

def is_stock_in_mainline(stock_code, mainline_industries):
    if not mainline_industries:
        return False
    industry = get_stock_industry(stock_code)
    if not industry:
        return False
    for kw in mainline_industries:
        if kw in industry:
            return True
    return False

def merge_and_rank(picks_all, main_group):
    mainline_industries = get_mainline_industries(main_group)
    if not mainline_industries:
        return sorted(picks_all, key=lambda x: x.get('final_score', 0), reverse=True)

    merged = {}
    for p in picks_all:
        code = p.get('code')
        if not code:
            continue
        is_main = is_stock_in_mainline(code, mainline_industries)
        new_p = p.copy()
        new_p['is_mainline'] = is_main
        if is_main:
            new_p['final_score'] = p.get('final_score', 0) + 5.0
        if code not in merged or new_p.get('final_score', 0) > merged[code].get('final_score', 0):
            merged[code] = new_p

    result = sorted(merged.values(), key=lambda x: x.get('final_score', 0), reverse=True)
    return result

def main():
    mainline_file = "mainline_result.json"
    main_group = None
    if os.path.exists(mainline_file):
        try:
            with open(mainline_file, 'r', encoding='utf-8') as f:
                main_data = json.load(f)
                main_group = main_data.get('main_group')
                print(f"📊 当前主线: {main_group}")
        except Exception as e:
            print(f"⚠️ 读取主线结果失败: {e}")

    candidates_all_file = "shared/candidates_all.json"
    picks_all = load_candidates(candidates_all_file)
    if not picks_all:
        print("⚠️ 全市场候选为空，无法合并")
        with open("shared/candidates.json", "w", encoding='utf-8') as f:
            json.dump({"picks": []}, f, indent=2)
        sys.exit(0)

    merged_picks = merge_and_rank(picks_all, main_group)
    main_count = sum(1 for p in merged_picks if p.get('is_mainline', False))
    print(f"全市场候选: {len(picks_all)} 只")
    print(f"主线候选 (加分后): {main_count} 只")
    print(f"合并后总数: {len(merged_picks)} 只")

    output_data = {
        "picks": merged_picks[:10],
        "original_count": len(picks_all),
        "mainline_count": main_count,
        "merged_count": len(merged_picks)
    }
    with open("shared/candidates.json", "w", encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print("✅ 合并完成，结果已保存到 shared/candidates.json")

if __name__ == "__main__":
    main()