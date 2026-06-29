#!/usr/bin/env python3
"""
买卖价格计算器 v2.0
读取候选股，根据行业匹配策略，计算买入/止损/止盈价
支持：追涨/低吸区分、3层价格源、缓存机制
"""
import yaml
import json
import os
import sys
import requests
from datetime import datetime, timedelta
from scripts.logger import log

# ============================================================
# 配置文件路径
# ============================================================
INDUSTRY_FILE = "scripts/industry_mapping.json"
CANDIDATES_FILE = "shared/candidates.json"
MARKET_STATE_FILE = "market_state.json"
OUTPUT_FILE = "pricing.txt"
CACHE_DIR = "cache"

# ============================================================
# 数据加载
# ============================================================
def load_industry_mapping():
    if not os.path.exists(INDUSTRY_FILE):
        log("WARNING", f"行业映射文件不存在: {INDUSTRY_FILE}")
        return {}
    try:
        with open(INDUSTRY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log("ERROR", f"[load_industry_mapping] 加载失败: {e}")
        return {}

def load_market_state():
    state_file = MARKET_STATE_FILE
    if not os.path.exists(state_file):
        state_file = "daily_stock_analysis/reports/market_state.json"
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                log("INFO", f"大盘策略: {state.get('strategy', 'rsi_reversion_v1')}")
                return state
        except Exception as e:
            log("WARNING", f"[load_market_state] 加载失败: {e}")
    return {}

def load_candidates():
    if not os.path.exists(CANDIDATES_FILE):
        log("WARNING", f"候选股文件不存在: {CANDIDATES_FILE}")
        return []
    try:
        with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        picks = data.get('picks', [])
        result = []
        for item in picks:
            if isinstance(item, str):
                result.append({'code': item, 'name': ''})
            elif isinstance(item, dict) and 'code' in item:
                result.append({'code': item['code'], 'name': item.get('name', '')})
        return result
    except Exception as e:
        log("ERROR", f"[load_candidates] 读取失败: {e}")
        return []

def get_stock_strategy_config(stock_code, industry_data):
    """返回: (strategy_name, buy_bias, stop_loss_pct)"""
    if not industry_data:
        return "rsi_reversion_v1", 0.98, 0.05
    
    mapping = industry_data.get("mapping", {})
    strategy_map = industry_data.get("strategy_mapping", {})
    pricing_config = industry_data.get("pricing_config", {})
    default_pricing = industry_data.get("default_pricing", {"buy_bias": 0.98, "stop_loss_pct": 0.05})
    default_strategy = industry_data.get("default_strategy", "rsi_reversion_v1")
    
    prefix = stock_code[:3] if len(stock_code) >= 3 else stock_code
    matched_industry = None
    
    for industry, codes in mapping.items():
        if prefix in codes or stock_code in codes:
            matched_industry = industry
            break
    
    if matched_industry:
        strategy = strategy_map.get(matched_industry, default_strategy)
        pricing = pricing_config.get(matched_industry, default_pricing)
        buy_bias = pricing.get("buy_bias", default_pricing.get("buy_bias", 0.98))
        stop_loss_pct = pricing.get("stop_loss_pct", default_pricing.get("stop_loss_pct", 0.05))
        return strategy, buy_bias, stop_loss_pct
    
    return default_strategy, default_pricing.get("buy_bias", 0.98), default_pricing.get("stop_loss_pct", 0.05)

def find_strategy_file(strategy_name):
    possible_names = [strategy_name, "rsi_reversion_v1", "rsi_reversion"]
    possible_dirs = ["alphaevo/strategies/builtin/", "alphaevo/strategies/"]
    for dir_path in possible_dirs:
        for name in possible_names:
            full_path = f"{dir_path}{name}.yaml"
            if os.path.exists(full_path):
                return full_path
    return None

def load_strategy(strategy_name):
    strategy_file = find_strategy_file(strategy_name)
    if not strategy_file:
        log("WARNING", f"[load_strategy] 策略文件不存在: {strategy_name}")
        return None
    try:
        with open(strategy_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        log("ERROR", f"[load_strategy] 加载策略失败 {strategy_name}: {e}")
        return None

# ============================================================
# 价格获取（3层 + 缓存）
# ============================================================
def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cached_price(stock_code):
    ensure_cache_dir()
    cache_file = f"{CACHE_DIR}/price_{stock_code}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cache_date = data.get('date')
                if cache_date == datetime.now().strftime("%Y-%m-%d"):
                    return data.get('price')
        except:
            pass
    return None

def save_cache_price(stock_code, price):
    ensure_cache_dir()
    cache_file = f"{CACHE_DIR}/price_{stock_code}.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({"date": datetime.now().strftime("%Y-%m-%d"), "price": price}, f)
    except:
        pass

def get_price_tencent(stock_code):
    try:
        prefix = "sh" if stock_code.startswith('6') else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None
        text = resp.text
        if '=' not in text:
            return None
        parts = text.split('~')
        if len(parts) > 3:
            price_str = parts[3]
            val = float(price_str)
            if 0 < val < 10000:
                return val
        return None
    except Exception as e:
        log("WARNING", f"[get_price_tencent] {stock_code} 失败: {e}")
        return None

def get_price_sina(stock_code):
    try:
        prefix = "sh" if stock_code.startswith('6') else "sz"
        url = f"https://hq.sinajs.cn/list={prefix}{stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None
        text = resp.text
        if '=' not in text or 'var' not in text:
            return None
        parts = text.split(',')
        if len(parts) > 3:
            price_str = parts[3]
            val = float(price_str)
            if 0 < val < 10000:
                return val
        return None
    except Exception as e:
        log("WARNING", f"[get_price_sina] {stock_code} 失败: {e}")
        return None

def get_price_baostock_cache(stock_code):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        lg = bs.login()
        if lg.error_code != '0':
            return None
        prefix = "sh" if stock_code.startswith('6') else "sz"
        rs = bs.query_history_k_data_plus(
            f"{prefix}.{stock_code}", "date,close",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) == 0:
            return None
        price = float(data['close'].values[-1])
        if 0 < price < 10000:
            return price
        return None
    except Exception as e:
        log("WARNING", f"[get_price_baostock_cache] {stock_code} 失败: {e}")
        return None

def get_stock_realtime_price(stock_code):
    # 1. 检查缓存
    cached = get_cached_price(stock_code)
    if cached:
        log("DEBUG", f"{stock_code} 使用缓存价格: {cached}")
        return cached
    
    # 2. 腾讯财经
    price = get_price_tencent(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price
    
    log("WARNING", f"腾讯财经失败，切换新浪财经: {stock_code}")
    
    # 3. 新浪财经
    price = get_price_sina(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price
    
    log("WARNING", f"新浪财经失败，使用Baostock前日收盘价: {stock_code}")
    
    # 4. Baostock 前日收盘价（兜底）
    price = get_price_baostock_cache(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price
    
    log("ERROR", f"所有价格源均失败: {stock_code}")
    return None

# ============================================================
# 定价计算
# ============================================================
def calculate_pricing(strategy, current_price, buy_bias, stop_loss_pct):
    if current_price is None or current_price <= 0:
        return None
    exit_params = strategy.get('exit', {}) if strategy else {}
    take_profit_rr = exit_params.get('take_profit', {}).get('value', 2.0)
    buy_price = current_price * buy_bias
    stop_loss = buy_price * (1 - stop_loss_pct)
    take_profit = buy_price * (1 + stop_loss_pct * take_profit_rr)
    return {
        "buy_price": round(buy_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "current_price": round(current_price, 2),
        "buy_bias": buy_bias,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_rr": take_profit_rr
    }

# ============================================================
# 主函数
# ============================================================
def main():
    log("INFO", "="*60)
    log("INFO", "📊 买卖价格计算器 v2.0")
    log("INFO", "="*60)
    
    industry_data = load_industry_mapping()
    market_state = load_market_state()
    candidates = load_candidates()
    
    if not candidates:
        log("WARNING", "没有候选股，退出")
        sys.exit(0)
    
    log("INFO", f"共 {len(candidates)} 只候选股")
    log("INFO", "="*60)
    
    report_lines = [
        "📊 买卖价格参考（个股级策略匹配）",
        "=" * 60,
        f"大盘策略: {market_state.get('strategy', 'rsi_reversion_v1')}",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "💡 说明：buy_bias > 1 为追涨，< 1 为低吸",
        ""
    ]
    
    success_count = 0
    fail_count = 0
    
    for item in candidates:
        code = item['code']
        name = item.get('name', '')
        
        strategy_name, buy_bias, stop_loss_pct = get_stock_strategy_config(code, industry_data)
        log("INFO", f"{code} {name} → 策略: {strategy_name}, 买入偏移: {buy_bias}")
        
        strategy = load_strategy(strategy_name)
        if not strategy:
            strategy = load_strategy("rsi_reversion_v1")
        if not strategy:
            report_lines.append(f"❌ {code} {name} → 策略加载失败")
            fail_count += 1
            continue
        
        current_price = get_stock_realtime_price(code)
        pricing = calculate_pricing(strategy, current_price, buy_bias, stop_loss_pct)
        if not pricing:
            report_lines.append(f"❌ {code} {name} → 无法获取价格")
            fail_count += 1
            continue
        
        strategy_type = "追涨" if buy_bias > 1 else "低吸"
        report_lines.append(f"📈 {code} {name}")
        report_lines.append(f"   匹配策略: {strategy_name}")
        report_lines.append(f"   策略类型: {strategy_type}")
        report_lines.append(f"   当前价: {pricing['current_price']:.2f}")
        report_lines.append(f"   参考买入价: {pricing['buy_price']:.2f}")
        report_lines.append(f"   止损价: {pricing['stop_loss']:.2f}")
        report_lines.append(f"   止盈价: {pricing['take_profit']:.2f}")
        report_lines.append("")
        success_count += 1
        log("INFO", f"  ✅ {code} 当前: {pricing['current_price']:.2f}, 买入: {pricing['buy_price']:.2f}")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    log("INFO", "="*60)
    log("INFO", f"✅ 定价报告已生成: {OUTPUT_FILE}")
    log("INFO", f"   成功: {success_count} 只, 失败: {fail_count} 只")
    log("INFO", "="*60)

if __name__ == "__main__":
    main()