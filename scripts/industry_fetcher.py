#!/usr/bin/env python3
"""
使用 Baostock 按需查询股票行业分类
只查询候选股，不拉取全量数据
"""
import json
import os
from logger import log

CONFIG_FILE = "scripts/industry_mapping.json"


def _load_config():
    """加载策略映射配置"""
    if not os.path.exists(CONFIG_FILE):
        log("WARNING", f"配置文件 {CONFIG_FILE} 不存在，使用默认")
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _query_stock_industry_baostock(stock_code):
    """
    查询单只股票的行业（使用 Baostock）
    返回行业名称字符串，查询失败返回空字符串
    """
    try:
        import baostock as bs
        
        # 判断市场前缀
        if stock_code.startswith(('6', '688')):
            code_with_prefix = f"sh.{stock_code}"
        elif stock_code.startswith(('0', '3')):
            code_with_prefix = f"sz.{stock_code}"
        else:
            log("WARNING", f"无法识别股票代码前缀: {stock_code}")
            return ""

        lg = bs.login()
        if lg.error_code != '0':
            log("WARNING", f"Baostock 登录失败: {lg.error_msg}")
            return ""

        rs = bs.query_stock_industry(code=code_with_prefix)
        if rs.error_code != '0':
            bs.logout()
            log("WARNING", f"查询 {stock_code} 失败: {rs.error_msg}")
            return ""

        if not rs.next():
            bs.logout()
            log("WARNING", f"未找到 {stock_code} 的行业信息")
            return ""

        row = rs.get_row_data()
        bs.logout()

        # row: [updateDate, code, code_name, industry, industryClassification]
        if len(row) >= 4:
            industry = row[3]
            log("DEBUG", f"{stock_code} 行业: {industry}")
            return industry
        return ""
    except Exception as e:
        log("WARNING", f"查询 {stock_code} 行业失败: {e}")
        return ""


def _map_industry_to_category(industry, stock_code):
    """
    根据行业关键词和股票代码前缀，映射到分类（科技/金融/传统）
    """
    config = _load_config()
    keyword_mapping = config.get('industry_keyword_mapping', {})
    
    # 优先按行业关键词映射
    if industry:
        for keyword, category in keyword_mapping.items():
            if keyword in industry:
                return category
    
    # 兜底：按股票代码前缀判断
    if stock_code.startswith(('600', '601', '603', '605')):
        return '传统'
    elif stock_code.startswith(('000', '001')):
        return '金融'
    elif stock_code.startswith(('300', '301', '002', '688')):
        return '科技'
    else:
        return '传统'  # 默认


def get_stock_strategy_config(stock_code):
    """
    获取股票的策略配置
    返回: (strategy_name, buy_bias, stop_loss_pct)
    """
    config = _load_config()
    strategy_mapping = config.get('strategy_mapping', {})
    pricing_config = config.get('pricing_config', {})
    default_strategy = config.get('default_strategy', 'rsi_reversion_v1')
    default_pricing = config.get('default_pricing', {'buy_bias': 0.98, 'stop_loss_pct': 0.05})

    # 查询行业
    industry = _query_stock_industry_baostock(stock_code)
    
    # 映射到分类
    category = _map_industry_to_category(industry, stock_code)
    
    # 获取策略
    strategy = strategy_mapping.get(category, default_strategy)
    pricing = pricing_config.get(category, default_pricing)
    buy_bias = pricing.get('buy_bias', default_pricing.get('buy_bias', 0.98))
    stop_loss_pct = pricing.get('stop_loss_pct', default_pricing.get('stop_loss_pct', 0.05))

    log("DEBUG", f"{stock_code} 行业: {industry} → 分类: {category} → 策略: {strategy}")
    return strategy, buy_bias, stop_loss_pct


# 测试
if __name__ == "__main__":
    # 测试歌尔股份
    print(get_stock_strategy_config('002241'))
    print(get_stock_strategy_config('600000'))