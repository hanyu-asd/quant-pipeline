#!/usr/bin/env python3
"""
自动判断市场状态并选择策略
使用腾讯财经 API 获取指数数据（无需 akshare，只依赖 requests）
"""

import requests
import json
import re
from datetime import datetime, timedelta

# ============================================================
# 腾讯财经 API 封装
# ============================================================

def get_index_history(symbol, days=80):
    """
    获取指数历史K线数据（腾讯财经）
    
    symbol: sh000001（上证指数）, sz399006（创业板指）
    days: 获取最近多少个交易日的数据
    
    返回: 收盘价列表（从旧到新）
    """
    try:
        # 腾讯财经历史K线接口
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_day&param={symbol},day,,,{days}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"获取 {symbol} 历史数据失败: HTTP {resp.status_code}")
            return None
        
        # 提取 JSON 数据
        # 返回格式: kline_day=({...});
        data_str = resp.text
        match = re.search(r'kline_day=({.*})', data_str)
        if not match:
            print(f"获取 {symbol} 历史数据失败: 无法解析响应")
            return None
        
        data_json = json.loads(match.group(1))
        
        # 检查数据是否存在
        if 'data' not in data_json or symbol not in data_json['data']:
            print(f"获取 {symbol} 历史数据失败: 数据为空")
            return None
        
        kline_data = data_json['data'][symbol].get('day', [])
        if not kline_data:
            print(f"获取 {symbol} 历史数据失败: 无K线数据")
            return None
        
        # 提取收盘价 (每项: [日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额])
        closes = [float(item[2]) for item in kline_data if len(item) > 2]
        return closes
        
    except Exception as e:
        print(f"获取 {symbol} 历史数据异常: {e}")
        return None


def get_index_realtime(symbol):
    """
    获取指数实时行情（腾讯财经）
    
    symbol: sh000001（上证指数）, sz399006（创业板指）
    
    返回: {'price': 价格, 'change_pct': 涨跌幅%}
    """
    try:
        url = f"https://qt.gtimg.cn/q={symbol}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        
        # 解析数据
        # 格式: v_sh000001="1~上证指数~000001~3215.67~-0.35~...";
        data = resp.text
        if '=' in data:
            data = data.split('=')[1].strip().strip(';').strip('"')
            parts = data.split('~')
            if len(parts) > 4:
                return {
                    'price': float(parts[3]) if parts[3] else 0,
                    'change_pct': float(parts[4]) if parts[4] else 0
                }
        return None
        
    except Exception as e:
        print(f"获取 {symbol} 实时行情异常: {e}")
        return None


# ============================================================
# 市场状态判断
# ============================================================

def calculate_ma(closes, period):
    """计算移动平均线"""
    if len(closes) < period:
        return closes[-1]
    return sum(closes[-period:]) / period


def main():
    print("=" * 60)
    print("📊 市场状态分析（腾讯财经 API）")
    print("=" * 60)
    
    # 1. 获取上证指数历史数据
    sh_closes = get_index_history("sh000001", 80)
    if not sh_closes or len(sh_closes) < 20:
        print("⚠️ 无法获取上证指数数据，使用默认策略: rsi_reversion_v1")
        with open("selected_strategy.txt", "w") as f:
            f.write("rsi_reversion_v1")
        return
    
    print(f"✅ 获取上证指数数据: {len(sh_closes)} 个交易日")
    
    # 2. 获取创业板指历史数据
    cy_closes = get_index_history("sz399006", 80)
    if cy_closes:
        print(f"✅ 获取创业板指数据: {len(cy_closes)} 个交易日")
    else:
        print("⚠️ 无法获取创业板指数据，将使用上证指数替代")
        cy_closes = sh_closes
    
    # 3. 计算均线
    ma20 = calculate_ma(sh_closes, 20)
    ma60 = calculate_ma(sh_closes, 60) if len(sh_closes) >= 60 else ma20
    current = sh_closes[-1]
    
    # 4. 趋势判断
    if current > ma20 and ma20 > ma60:
        trend = "up"
        trend_desc = "上升趋势"
    elif current < ma20 and ma20 < ma60:
        trend = "down"
        trend_desc = "下降趋势"
    else:
        trend = "sideways"
        trend_desc = "震荡"
    
    # 5. 科技股溢价（近20日涨幅差）
    tech_premium = 0
    if len(cy_closes) >= 20 and len(sh_closes) >= 20:
        ret_cy = (cy_closes[-1] / cy_closes[-20] - 1) * 100
        ret_sh = (sh_closes[-1] / sh_closes[-20] - 1) * 100
        tech_premium = round(ret_cy - ret_sh, 2)
    
    # 6. 动量强度（近20日涨幅）
    momentum = round((sh_closes[-1] / sh_closes[-20] - 1) * 100, 2)
    
    # 7. 波动率（近20日标准差）
    if len(sh_closes) >= 20:
        import statistics
        volatility = round(statistics.stdev(sh_closes[-20:]) / sum(sh_closes[-20:]) * 20 * 100, 2)
    else:
        volatility = 0
    
    # 8. 选择策略
    if trend == "up" and tech_premium > 3:
        strategy = "trend_pullback_rebound"
        reason = f"上升趋势 + 科技股强势（溢价 {tech_premium}%）"
    elif trend == "up":
        strategy = "ma_crossover"
        reason = f"上升趋势（动量 {momentum}%）"
    elif trend == "down":
        strategy = "rsi_reversion_v1"
        reason = f"下降趋势（等待超跌反弹）"
    else:
        strategy = "rsi_reversion_v1"
        reason = f"震荡（均值回归）"
    
    # 9. 输出结果
    print("")
    print("📊 分析结果:")
    print(f"  上证指数: {current:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    print(f"  趋势: {trend_desc}")
    print(f"  科技溢价（创-上）: {tech_premium}%")
    print(f"  动量（近20日）: {momentum}%")
    print(f"  波动率（近20日）: {volatility}%")
    print("")
    print(f"🎯 选定策略: {strategy}")
    print(f"📝 原因: {reason}")
    print("=" * 60)
    
    # 10. 写入结果文件
    with open("selected_strategy.txt", "w") as f:
        f.write(strategy)
    
    # 11. 同时保存完整状态（供后续使用）
    state = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "current_price": current,
        "ma20": ma20,
        "ma60": ma60,
        "trend": trend,
        "trend_desc": trend_desc,
        "tech_premium": tech_premium,
        "momentum": momentum,
        "volatility": volatility,
        "strategy": strategy,
        "reason": reason
    }
    with open("market_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    print("✅ 结果已保存到 selected_strategy.txt 和 market_state.json")


if __name__ == "__main__":
    main()