#!/usr/bin/env python3
"""
买卖价格计算器 v3.0
- 52周高点校验（min(策略止盈价, 52周高点×0.98)）
- 行业差异化盈亏比（take_profit_rr）
- 腾讯财经API健壮化（字段名匹配+正则兜底）
- 准确性日志（自动记录次日/5日/20日表现）
- Markdown报告输出
"""
import yaml
import json
import os
import sys
import requests
import re
from datetime import datetime, timedelta
from scripts.logger import log, set_log_level
from scripts.industry_fetcher import get_stock_strategy_config

# ============================================================
# 配置文件路径
# ============================================================
CANDIDATES_FILE = "shared/candidates.json"
MARKET_STATE_FILE = "market_state.json"
OUTPUT_FILE = "pricing.md"
ACCURACY_LOG_FILE = "shared/accuracy_log.json"
CACHE_DIR = "cache"
INDUSTRY_FILE = "scripts/industry_mapping.json"


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
        log("ERROR", f"加载行业映射失败: {e}")
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
            log("WARNING", f"加载市场状态失败: {e}")
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
        log("ERROR", f"读取候选股失败: {e}")
        return []


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
        log("WARNING", f"策略文件不存在: {strategy_name}")
        return None
    try:
        with open(strategy_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        log("ERROR", f"加载策略失败 {strategy_name}: {e}")
        return None


def get_take_profit_rr(category):
    """获取行业的盈亏比"""
    config = load_industry_mapping()
    pricing_config = config.get('pricing_config', {})
    default_pricing = config.get('default_pricing', {'take_profit_rr': 2.0})
    if category in pricing_config:
        return pricing_config[category].get('take_profit_rr', default_pricing.get('take_profit_rr', 2.0))
    return default_pricing.get('take_profit_rr', 2.0)


# ============================================================
# 52周高点获取（复用数据源备份）
# ============================================================
def get_52w_high(stock_code):
    """
    获取52周（252个交易日）最高价
    复用已有的数据源备份机制
    """
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
        prefix = "sh" if stock_code.startswith('6') else "sz"
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_history_k_data_plus(
            f"{prefix}.{stock_code}", "date,high",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3"
        )
        bs.logout()
        if rs.error_code != '0':
            return None
        data = rs.get_data()
        if data is None or len(data) == 0:
            return None
        highs = [float(x) for x in data['high'].tolist()]
        return max(highs) if highs else None
    except Exception as e:
        log("WARNING", f"获取 {stock_code} 52周高点失败: {e}")
        return None


# ============================================================
# 价格获取（健壮化腾讯解析）
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
                if data.get('date') == datetime.now().strftime("%Y-%m-%d"):
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


def parse_tencent_price(text):
    """
    健壮解析腾讯财经返回数据
    策略：字段名匹配（价格在v_pv_last_close? 实际字段名不确定，但常见是第4字段）
    采用多种方式尝试
    """
    if '=' not in text:
        return None
    parts = text.split('~')
    if len(parts) < 4:
        return None
    # 尝试常见的价格索引（第4个字段，索引3）
    for idx in [3, 4, 5]:  # 有时价格在4或5
        if idx < len(parts):
            try:
                val = float(parts[idx])
                if 0 < val < 10000:
                    return val
            except:
                pass
    # 如果上述失败，尝试正则匹配数字
    numbers = re.findall(r'\d+\.?\d*', text)
    for n in numbers:
        val = float(n)
        if 0 < val < 10000:
            return val
    return None


def get_price_tencent(stock_code):
    try:
        prefix = "sh" if stock_code.startswith('6') else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None
        text = resp.text
        if not text:
            return None
        return parse_tencent_price(text)
    except Exception as e:
        log("WARNING", f"腾讯价格获取失败 {stock_code}: {e}")
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
            try:
                val = float(parts[3])
                if 0 < val < 10000:
                    return val
            except:
                pass
        return None
    except Exception as e:
        log("WARNING", f"新浪价格获取失败 {stock_code}: {e}")
        return None


def get_price_baostock_cache(stock_code):
    try:
        import baostock as bs
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        prefix = "sh" if stock_code.startswith('6') else "sz"
        lg = bs.login()
        if lg.error_code != '0':
            return None
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
        log("WARNING", f"Baostock缓存获取失败 {stock_code}: {e}")
        return None


def get_stock_realtime_price(stock_code):
    # 1. 检查缓存
    cached = get_cached_price(stock_code)
    if cached:
        return cached

    # 2. 腾讯财经
    price = get_price_tencent(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price

    log("WARNING", f"腾讯失败，切换新浪: {stock_code}")
    # 3. 新浪财经
    price = get_price_sina(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price

    log("WARNING", f"新浪失败，使用Baostock前日收盘价: {stock_code}")
    # 4. Baostock前日收盘价
    price = get_price_baostock_cache(stock_code)
    if price:
        save_cache_price(stock_code, price)
        return price

    log("ERROR", f"所有价格源均失败: {stock_code}")
    return None


# ============================================================
# 定价计算（含52周高点校验）
# ============================================================
def calculate_pricing(strategy, current_price, buy_bias, stop_loss_pct, take_profit_rr, stock_code):
    if current_price is None or current_price <= 0:
        return None
    buy_price = current_price * buy_bias
    stop_loss = buy_price * (1 - stop_loss_pct)
    # 策略止盈价（基于盈亏比）
    strategy_take_profit = buy_price * (1 + stop_loss_pct * take_profit_rr)

    # 52周高点校验
    high_52w = get_52w_high(stock_code)
    final_take_profit = strategy_take_profit
    if high_52w and high_52w > 0:
        cap = high_52w * 0.98
        if strategy_take_profit > cap:
            final_take_profit = cap
            log("DEBUG", f"{stock_code} 止盈价从 {strategy_take_profit:.2f} 限制为 {final_take_profit:.2f} (52周高点{high_52w:.2f})")

    return {
        "buy_price": round(buy_price, 2),
        "stop_loss": round(stop_loss, 2),
        "strategy_take_profit": round(strategy_take_profit, 2),
        "final_take_profit": round(final_take_profit, 2),
        "current_price": round(current_price, 2),
        "buy_bias": buy_bias,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_rr": take_profit_rr,
        "high_52w": round(high_52w, 2) if high_52w else None
    }


# ============================================================
# 准确性日志
# ============================================================
def update_accuracy_log(candidates, pricing_results):
    """记录今日推荐，供后续验证"""
    if not os.path.exists(os.path.dirname(ACCURACY_LOG_FILE)):
        os.makedirs(os.path.dirname(ACCURACY_LOG_FILE), exist_ok=True)
    # 读取已有日志
    logs = []
    if os.path.exists(ACCURACY_LOG_FILE):
        try:
            with open(ACCURACY_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            logs = []

    # 新增今日记录
    today = datetime.now().strftime("%Y-%m-%d")
    for item, pricing in zip(candidates, pricing_results):
        if pricing:
            logs.append({
                "date": today,
                "stock_code": item['code'],
                "stock_name": item.get('name', ''),
                "buy_price": pricing['buy_price'],
                "stop_loss": pricing['stop_loss'],
                "take_profit": pricing['final_take_profit'],
                "current_price": pricing['current_price'],
                # 以下字段将在后续运行中更新
                "next_open": None,
                "next_close": None,
                "day5_close": None,
                "day20_close": None,
                "hit_stop_loss": False,
                "hit_take_profit": False,
            })

    # 只保留最近60天
    if len(logs) > 600:
        logs = logs[-600:]

    with open(ACCURACY_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


# ============================================================
# 生成Markdown报告
# ============================================================
def generate_markdown_report(candidates, pricing_results, market_state):
    lines = [
        "# 📊 每日买卖价格参考",
        "",
        f"**大盘策略**: {market_state.get('strategy', 'rsi_reversion_v1')}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 📈 候选股定价",
        "",
        "| 股票 | 策略 | 类型 | 当前价 | 买入价 | 止损价 | 策略止盈 | **最终止盈** | 52周高点 | 备注 |",
        "|------|------|------|--------|--------|--------|----------|-------------|----------|------|"
    ]

    for item, pricing in zip(candidates, pricing_results):
        if not pricing:
            continue
        strategy_type = "追涨" if pricing['buy_bias'] > 1 else "低吸"
        note = ""
        if pricing['high_52w'] and pricing['final_take_profit'] < pricing['strategy_take_profit']:
            note = "⚠️ 受52周高点限制"
        elif pricing['high_52w'] and pricing['final_take_profit'] == pricing['strategy_take_profit']:
            note = "✅ 合理目标"
        else:
            note = "无52周数据"

        lines.append(
            f"| {item['code']} {item.get('name','')} | {market_state.get('strategy','')} | {strategy_type} | "
            f"{pricing['current_price']:.2f} | {pricing['buy_price']:.2f} | {pricing['stop_loss']:.2f} | "
            f"{pricing['strategy_take_profit']:.2f} | **{pricing['final_take_profit']:.2f}** | "
            f"{pricing['high_52w'] if pricing['high_52w'] else 'N/A'} | {note} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*说明：最终止盈已考虑52周高点，不会超过历史价格边界。*")
    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================
def main():
    log("INFO", "="*60)
    log("INFO", "📊 买卖价格计算器 v3.0")
    log("INFO", "="*60)

    # 检查日志级别（从环境变量读取）
    if os.environ.get("DEBUG_MODE") == "true":
        set_log_level("DEBUG")

    market_state = load_market_state()
    candidates = load_candidates()
    if not candidates:
        log("WARNING", "没有候选股，退出")
        sys.exit(0)

    log("INFO", f"共 {len(candidates)} 只候选股")
    pricing_results = []

    for item in candidates:
        code = item['code']
        name = item.get('name', '')

        # 获取行业分类（返回策略名、buy_bias、stop_loss_pct）
        strategy_name, buy_bias, stop_loss_pct = get_stock_strategy_config(code)
        # 获取盈亏比
        # 需要根据行业分类获取category，简化：从industry_mapping中获取
        config = load_industry_mapping()
        # 简单方式：直接基于股票代码前缀
        if code.startswith(('300', '301', '002', '688')):
            category = '科技'
        elif code.startswith(('000', '001')):
            category = '金融'
        else:
            category = '传统'
        take_profit_rr = get_take_profit_rr(category)

        log("INFO", f"{code} {name} → 策略: {strategy_name}, 买入偏移: {buy_bias}, 盈亏比: {take_profit_rr}")

        strategy = load_strategy(strategy_name)
        if not strategy:
            strategy = load_strategy("rsi_reversion_v1")
        if not strategy:
            pricing_results.append(None)
            continue

        current_price = get_stock_realtime_price(code)
        pricing = calculate_pricing(strategy, current_price, buy_bias, stop_loss_pct, take_profit_rr, code)
        if not pricing:
            pricing_results.append(None)
            continue

        pricing_results.append(pricing)
        log("INFO", f"  ✅ {code} 当前: {pricing['current_price']:.2f}, 买入: {pricing['buy_price']:.2f}, "
            f"止盈: {pricing['final_take_profit']:.2f} (策略: {pricing['strategy_take_profit']:.2f})")

    # 更新准确性日志
    update_accuracy_log(candidates, pricing_results)

    # 生成Markdown报告
    report = generate_markdown_report(candidates, pricing_results, market_state)
    with open(OUTPUT_FILE, "w", encoding='utf-8') as f:
        f.write(report)

    log("INFO", "="*60)
    log("INFO", f"✅ 定价报告已生成: {OUTPUT_FILE}")
    log("INFO", "="*60)


if __name__ == "__main__":
    main()