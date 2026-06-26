#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股大盘每日深度分析报告 v2.0
  - 主要指数行情与K线技术指标
  - 北向资金 / 沪深港通
  - 行业资金流向与热点板块
  - 涨跌家数 / 涨停跌停
  - 外围市场（美股/原油/黄金/汇率/恒生）
  - 两融余额
  - MACD / RSI / KDJ / 布林带
  - 综合打分
  - PushPlus 微信推送
"""

import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ===================== 配置 =====================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
HOLIDAYS_2026 = {
    "01-01", "01-02",
    "02-16", "02-17", "02-18", "02-19", "02-20",
    "04-04", "04-05", "04-06",
    "05-01", "05-02", "05-03", "05-04", "05-05",
    "06-20", "06-21", "06-22",
    "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07", "10-08",
}

# 最新宏观数据（月度更新）
MACRO_DATA = {
    "PMI": "49.5", "PMI_month": "2026-05",
    "CPI": "0.3%", "CPI_month": "2026-05",
    "PPI": "-1.4%", "PPI_month": "2026-05",
    "M1": "1.2%", "M1_month": "2026-05",
    "M2": "7.0%", "M2_month": "2026-05",
    "MLF": "2.50%", "MLF_month": "2026-06",
}

# ===================== 工具函数 =====================
def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def today_md():
    return datetime.now().strftime("%m-%d")

def is_trading_day():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if today_md() in HOLIDAYS_2026:
        return False
    return True

def fetch_text(url, headers=None, timeout=15, encoding="utf-8"):
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return raw.decode(encoding, errors="ignore")
            except LookupError:
                return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR: {e}"

def fetch_json(url, headers=None, timeout=15):
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return f"ERROR: {e}"

def get_ma(klines, n):
    closes = [k["close"] for k in klines]
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def safe_float(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

def retry_call(func, args=None, kwargs=None, max_retries=2, delay=3):
    """带重试的函数调用，针对国内网站不稳定；全部失败时返回 None"""
    args = args or []
    kwargs = kwargs or {}
    last_err = None
    for attempt in range(1 + max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                import time
                time.sleep(delay)
    print(f"[WARN] {func.__name__} 重试{max_retries}次后仍失败: {last_err}")
    return None

# ===================== 技术指标计算 =====================
def calc_ema(values, period):
    """EMA 指数移动平均"""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema

def calc_macd(klines):
    """计算 MACD: 返回 (DIF, DEA, MACD柱)"""
    closes = [k["close"] for k in klines]
    if len(closes) < 26:
        return None, None, None
    ema12 = calc_ema([closes[-i] for i in range(min(12, len(closes)), 0, -1)], min(12, len(closes)))
    ema26 = calc_ema([closes[-i] for i in range(min(26, len(closes)), 0, -1)], min(26, len(closes)))
    if ema12 is None or ema26 is None:
        return None, None, None
    dif = ema12 - ema26
    # DEA = EMA of DIF (9日)
    dea_values = []
    for i in range(max(0, len(closes) - 35), len(closes)):
        c = closes[i]
        e12 = calc_ema(closes[max(0, i-11):i+1], min(12, i+1))
        e26 = calc_ema(closes[max(0, i-25):i+1], min(26, i+1))
        if e12 is not None and e26 is not None:
            dea_values.append(e12 - e26)
    if len(dea_values) < 9:
        dea = dif  # fallback
    else:
        dea = calc_ema(dea_values[-9:], 9) if len(dea_values) >= 9 else dif
    return dif, dea, 2 * (dif - dea)

def calc_rsi(klines, period=14):
    """RSI 相对强弱指标"""
    closes = [k["close"] for k in klines]
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_kdj(klines, period=9):
    """KDJ 随机指标"""
    if len(klines) < period:
        return None, None, None
    closes = [k["close"] for k in klines[-period:]]
    highs = [k["high"] for k in klines[-period:]]
    lows = [k["low"] for k in klines[-period:]]
    h_n = max(highs)
    l_n = min(lows)
    c = closes[-1]
    if h_n == l_n:
        return 50, 50, 50
    rsv = (c - l_n) / (h_n - l_n) * 100
    k_value = rsv
    d_value = k_value
    # 平滑
    for _ in range(3):
        k_value = 2/3 * k_value + 1/3 * rsv
        d_value = 2/3 * d_value + 1/3 * k_value
    j_value = 3 * k_value - 2 * d_value
    return k_value, d_value, j_value

def calc_bollinger(klines, period=20, k=2):
    """布林带"""
    closes = [k["close"] for k in klines]
    if len(closes) < period:
        return None, None, None
    ma = sum(closes[-period:]) / period
    variance = sum((c - ma) ** 2 for c in closes[-period:]) / period
    std = math.sqrt(variance)
    return ma, ma + k * std, ma - k * std

# ===================== 数据获取 =====================
def get_a_stock_index():
    """获取A股主要指数行情"""
    codes = "sh000001,sz399001,sz399006,sh000300,sh000016,sz399005"
    url = f"http://hq.sinajs.cn/list={codes}"
    text = fetch_text(url, headers={"Referer": "http://finance.sina.com.cn"})
    result = {}
    for line in text.strip().split("\n"):
        m = re.search(r'var hq_str_(\w+)="([^"]*)"', line)
        if not m:
            continue
        code, data = m.group(1), m.group(2)
        parts = data.split(",")
        if len(parts) < 30:
            continue
        name = parts[0]
        name_map = {
            "sh000001": "上证指数", "sz399001": "深证成指",
            "sz399006": "创业板指", "sh000300": "沪深300",
            "sh000016": "上证50", "sz399005": "中小板指"
        }
        name = name_map.get(code, name)
        try:
            open_p = float(parts[1])
            prev_close = float(parts[2])
            current = float(parts[3])
            high = float(parts[4])
            low = float(parts[5])
            volume = int(parts[6])
            turnover = float(parts[7])
            change = current - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0
            result[code] = {
                "name": name, "price": current, "open": open_p,
                "prev_close": prev_close, "high": high, "low": low,
                "change": change, "change_pct": change_pct,
                "volume": volume, "turnover": turnover / 1e8,
            }
        except (ValueError, IndexError):
            continue
    return result

def get_index_kline(secid, lmt=60):
    """获取指数K线（用于计算技术指标），东方财富失败后回退到腾讯"""
    # 东方财富 secid -> 腾讯 symbol 映射
    secid_map = {
        "1.000001": "sh000001",
        "0.399001": "sz399001",
        "1.000300": "sh000300",
    }
    tencent_symbol = secid_map.get(secid, secid)

    # 1. 先尝试东方财富
    url = (
        f"http://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0&end=20500101&lmt={lmt}"
    )
    data = fetch_json(url)
    if isinstance(data, dict) and "data" in data and data["data"] is not None:
        klines = data["data"].get("klines", [])
        parsed = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 11:
                parsed.append({
                    "date": parts[0], "open": float(parts[1]),
                    "close": float(parts[2]), "high": float(parts[3]),
                    "low": float(parts[4]), "volume": int(parts[5]),
                    "amount": float(parts[6]),
                })
        if len(parsed) >= 30:
            return parsed

    # 2. 东方财富失败后回退腾讯
    print(f"[WARN] 东方财富K线 {secid} 获取不足，尝试腾讯数据源...")
    tencent_url = (
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={tencent_symbol},day,,,{lmt},qfq"
    )
    data2 = fetch_json(tencent_url)
    if isinstance(data2, dict) and "data" in data2:
        day_data = data2["data"].get(tencent_symbol, {}).get("day", [])
        parsed2 = []
        for k in day_data:
            if len(k) >= 6:
                # 腾讯格式: [date, open, close, high, low, volume]
                parsed2.append({
                    "date": k[0], "open": float(k[1]),
                    "close": float(k[2]), "high": float(k[3]),
                    "low": float(k[4]), "volume": int(float(k[5])),
                    "amount": 0.0,
                })
        if len(parsed2) >= 30:
            return parsed2

    raise Exception(f"无法获取K线数据: {secid}")

def get_advance_decline():
    """获取涨跌家数"""
    h = {"User-Agent": "Mozilla/5.0"}
    indices = {
        "1.000001": "上证",
        "0.399001": "深证",
        "0.399006": "创业板",
    }
    result = {}
    for secid, name in indices.items():
        url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f168,f169,f170,f171,f58,f57"
        data = fetch_json(url, headers=h)
        if isinstance(data, dict) and "data" in data and data["data"]:
            d = data["data"]
            result[name] = {
                "up": abs(safe_float(d.get("f168", 0))),
                "down": abs(safe_float(d.get("f169", 0))),
                "flat": abs(safe_float(d.get("f170", 0))),
            }
    return result

def get_sector_flow(top_n=5):
    """获取行业资金流向（热点板块）"""
    url = ("http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=1&np=1"
           "&fields=f12,f14,f3,f62,f184,f66,f69"
           "&fid=f62&fs=m:90+t:2")
    data = fetch_json(url, headers={"User-Agent": "Mozilla/5.0"})
    if isinstance(data, str) or "data" not in data:
        return [], []
    items = data["data"].get("diff", [])
    # 按主力净流入排序（f62=主力净流入）
    sorted_by_inflow = sorted(items, key=lambda x: safe_float(x.get("f62", 0)), reverse=True)
    # 按涨幅排序
    sorted_by_gain = sorted(items, key=lambda x: safe_float(x.get("f3", 0)), reverse=True)

    inflows = []
    for s in sorted_by_inflow[:top_n]:
        name = s.get("f14", "")
        flow = safe_float(s.get("f62", 0)) / 1e8  # 转亿元
        inflows.append((name, flow))

    gainers = []
    for s in sorted_by_gain[:top_n]:
        name = s.get("f14", "")
        gain = safe_float(s.get("f3", 0)) / 100  # 转百分比
        flow = safe_float(s.get("f62", 0)) / 1e8
        gainers.append((name, gain, flow))

    return inflows, gainers

def get_northbound_flow():
    """获取北向资金（沪深港通）"""
    url = ("http://push2.eastmoney.com/api/qt/kamt.kline/get?"
           "fields1=f1,f2,f3,f4,f5,f6,f7"
           "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62"
           "&klt=1&lmt=2")
    data = fetch_json(url, headers={"User-Agent": "Mozilla/5.0"})
    if isinstance(data, str) or "data" not in data:
        return None
    d = data["data"]
    try:
        # s2n = 沪股通+深股通净流入 (北向合计)
        s2n = d.get("s2n", [])
        if s2n:
            parts = s2n[-1].split(",")
            if len(parts) >= 4:
                return {
                    "date": parts[0],
                    "sh_net": safe_float(d["hk2sh"][-1].split(",")[1]) if d.get("hk2sh") else 0,
                    "sz_net": safe_float(d["hk2sz"][-1].split(",")[1]) if d.get("hk2sz") else 0,
                    "total_net": safe_float(parts[1]) if parts[1] else 0,
                    "total_turnover": safe_float(parts[2]) if len(parts) > 2 else 0,
                }
    except (IndexError, KeyError):
        pass
    return None

def get_margin_balance():
    """获取两融余额"""
    url = "https://data.10jqka.com.cn/market/rzrq/"
    text = fetch_text(url, headers={"User-Agent": "Mozilla/5.0"}, encoding="gbk")
    if "ERROR" not in text:
        # 从 dataDay JS 数组提取（取最新日期）
        # 格式: dataDay = [[["2026-04-24",27127.86,...], ["2026-04-27",27285.30,...], ...]]
        matches = re.findall(r'"(\d{4}-\d{2}-\d{2})",([\d.]+)', text)
        if matches:
            # 找到最新日期的那条
            with_date = [(m[0], safe_float(m[1])) for m in matches
                         if safe_float(m[1]) > 10000]  # 只取大于10000的（过滤小数值）
            if with_date:
                with_date.sort(key=lambda x: x[0], reverse=True)
                return with_date[0][1]
        # 降级: 从表格最后一行获取总和
        rows = re.findall(r'<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>', text)
        if rows:
            return safe_float(rows[-1][2])
    return None

def get_global_markets():
    """获取外围市场数据"""
    codes = "fx_susdcnh,hf_CL,hf_GC,gb_ixic,gb_dji,gb_GSPC"
    url = f"http://hq.sinajs.cn/list={codes}"
    text = fetch_text(url, headers={"Referer": "http://finance.sina.com.cn"})
    result = {}
    for line in text.strip().split("\n"):
        m = re.search(r'var hq_str_(\w+)="([^"]*)"', line)
        if not m:
            continue
        code, data = m.group(1), m.group(2)
        parts = data.split(",")
        if len(parts) < 3:
            continue
        try:
            if code == "fx_susdcnh":
                pct = safe_float(parts[11]) * 100 if len(parts) > 11 else 0
                result["USDCNH"] = {"name": "离岸人民币", "price": safe_float(parts[1]), "change_pct": round(pct, 2)}
            elif code == "hf_CL":
                p = safe_float(parts[0])
                prev = safe_float(parts[7]) if len(parts) > 7 and parts[7] else 0
                cp = ((p - prev) / prev * 100) if prev else 0
                result["OIL"] = {"name": "WTI原油", "price": p, "change_pct": round(cp, 2)}
            elif code == "hf_GC":
                p = safe_float(parts[0])
                prev = safe_float(parts[7]) if len(parts) > 7 and parts[7] else 0
                cp = ((p - prev) / prev * 100) if prev else 0
                result["GOLD"] = {"name": "黄金", "price": p, "change_pct": round(cp, 2)}
            elif code == "gb_ixic":
                result["NASDAQ"] = {"name": "纳斯达克", "price": safe_float(parts[1]) if parts[1] else 0,
                                    "change_pct": safe_float(parts[2]) if len(parts) > 2 else 0}
            elif code == "gb_dji":
                result["DJI"] = {"name": "道琼斯", "price": safe_float(parts[1]) if parts[1] else 0,
                                 "change_pct": safe_float(parts[2]) if len(parts) > 2 else 0}
            elif code == "gb_GSPC":
                result["SP500"] = {"name": "标普500", "price": safe_float(parts[1]) if parts[1] else 0,
                                   "change_pct": safe_float(parts[2]) if len(parts) > 2 else 0}
        except (ValueError, IndexError):
            continue
    return result

def get_hang_seng():
    """获取恒生指数"""
    text = fetch_text("http://hq.sinajs.cn/list=rt_hkHSI",
                      headers={"Referer": "http://finance.sina.com.cn"})
    m = re.search(r'HSI,.*?,([\d.]+),', text)
    if m:
        return safe_float(m.group(1))
    return None

def get_us_futures():
    """获取美股期货"""
    codes = "hf_NQ,hf_ES"
    text = fetch_text(f"http://hq.sinajs.cn/list={codes}",
                      headers={"Referer": "http://finance.sina.com.cn"})
    result = {}
    for line in text.strip().split("\n"):
        m = re.search(r'var hq_str_(\w+)="([^"]*)"', line)
        if not m:
            continue
        code, data = m.group(1), m.group(2)
        parts = data.split(",")
        if len(parts) < 8:
            continue
        try:
            price = safe_float(parts[6])
            prev = safe_float(parts[14]) if len(parts) > 14 else 0
            change_pct = ((price - prev) / prev * 100) if prev else 0
            name = "纳指100期货" if code == "hf_NQ" else "标普500期货"
            result[code] = {"name": name, "price": price, "change_pct": change_pct}
        except (ValueError, IndexError):
            continue
    return result

# ===================== 分析逻辑 =====================
def analyze_market(index_data, klines_sh, klines_sz, klines_300, global_data, futures,
                   adv_dec, sector_inflows, sector_gainers, northbound, margin_bal):
    today_cn = datetime.now().strftime("%Y年%m月%d日")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
    lines = [f"A股大盘深度分析报告", f"{today_cn} {weekday_cn}", "=" * 35, ""]

    all_signals = []

    # ===== 1. 指数表现 =====
    lines.append("【📊 指数表现】")
    for code in ["sh000001", "sz399001", "sz399006", "sh000300", "sh000016"]:
        if code not in index_data:
            continue
        d = index_data[code]
        sign = "+" if d["change_pct"] >= 0 else ""
        arrow = "🔴" if d["change_pct"] > 0 else ("🟢" if d["change_pct"] < 0 else "⚪")
        lines.append(f"  {arrow} {d['name']}: {d['price']:.2f} ({sign}{d['change_pct']:.2f}%)")
        lines.append(f"     开 {d['open']:.2f}  高 {d['high']:.2f}  低 {d['low']:.2f}  成交 {d['turnover']:.0f}亿")
    lines.append("")

    # ===== 2. 技术指标 =====
    lines.append("【📈 技术指标】")
    if klines_sh and len(klines_sh) >= 30:
        closes = [k["close"] for k in klines_sh]
        current = klines_sh[-1]["close"]

        # 均线
        ma5 = get_ma(klines_sh, 5)
        ma10 = get_ma(klines_sh, 10)
        ma20 = get_ma(klines_sh, 20)
        lines.append(f"  均线系统 (上证):")
        lines.append(f"    MA5={ma5:.2f}  MA10={ma10:.2f}  MA20={ma20:.2f}")
        if current > ma5 > ma20:
            lines.append(f"    → 多头排列 ✓ (短期趋势向上)")
            all_signals.append(("均线", 2))
        elif current < ma5 < ma20:
            lines.append(f"    → 空头排列 ⚠ (短期趋势向下)")
            all_signals.append(("均线", -2))
        elif current > ma5:
            lines.append(f"    → 站上MA5, 短线偏强")
            all_signals.append(("均线", 1))
        elif current < ma5:
            lines.append(f"    → 跌破MA5, 短线偏弱")
            all_signals.append(("均线", -1))
        else:
            all_signals.append(("均线", 0))

        # MACD
        dif, dea, macd_bar = calc_macd(klines_sh)
        if dif is not None:
            macd_signal = "金叉 ✓" if macd_bar > 0 else ("死叉 ⚠" if macd_bar < 0 else "零轴")
            lines.append(f"  MACD: DIF={dif:.2f}  DEA={dea:.2f}  MACD柱={macd_bar:.2f} ({macd_signal})")
            all_signals.append(("MACD", 1 if macd_bar > 0 else (-1 if macd_bar < 0 else 0)))

        # RSI
        rsi = calc_rsi(klines_sh)
        if rsi is not None:
            rsi_desc = "超买区⚠" if rsi > 70 else ("超卖区💡" if rsi < 30 else "中性区间")
            lines.append(f"  RSI(14): {rsi:.1f} ({rsi_desc})")
            all_signals.append(("RSI", -1 if rsi > 70 else (1 if rsi < 30 else 0)))

        # KDJ
        k, d_val, j = calc_kdj(klines_sh)
        if k is not None:
            kdj_signal = "超买⚠" if k > 80 else ("超卖💡" if k < 20 else "中性")
            lines.append(f"  KDJ: K={k:.1f}  D={d_val:.1f}  J={j:.1f} ({kdj_signal})")

        # 布林带
        mid, upper, lower = calc_bollinger(klines_sh)
        if mid is not None:
            bb_pos = "上轨附近" if current >= upper else ("下轨附近" if current <= lower else "中轨附近")
            lines.append(f"  布林带: 中轨={mid:.0f} 上轨={upper:.0f} 下轨={lower:.0f}")
            lines.append(f"    现价在{bb_pos}")
            if current >= upper:
                all_signals.append(("布林带", -1))
            elif current <= lower:
                all_signals.append(("布林带", 1))
    else:
        lines.append("  数据不足")
    lines.append("")

    # ===== 3. 涨跌家数 =====
    lines.append("【📊 涨跌家数】")
    for market, data in adv_dec.items():
        total = data["up"] + data["down"] + data["flat"]
        ratio = data["up"] / max(data["down"], 1)
        emoji = "🔴" if ratio > 1 else "🟢"
        lines.append(f"  {market}: 涨{int(data['up'])} 跌{int(data['down'])} 平{int(data['flat'])} (涨跌比={ratio:.2f}) {emoji}")
        all_signals.append(("涨跌比", 1 if ratio > 1 else (-1 if ratio < 0.7 else 0)))
    lines.append("")

    # ===== 4. 热点板块 =====
    lines.append("【🔥 热点板块】")
    if sector_gainers:
        lines.append("  涨幅前5:")
        for name, gain, flow in sector_gainers[:5]:
            arrow = "🔴" if gain > 0 else "🟢"
            flow_str = f"主力净流入{flow:.1f}亿" if flow > 0 else f"主力净流出{abs(flow):.1f}亿"
            lines.append(f"  {arrow} {name}: +{gain:.2f}% ({flow_str})")
    lines.append("")
    if sector_inflows:
        lines.append("  主力资金流入前5:")
        for name, flow in sector_inflows[:5]:
            lines.append(f"  💰 {name}: 净流入{flow:.2f}亿")
    lines.append("")

    # ===== 5. 资金面 =====
    lines.append("【💰 资金面】")
    if northbound:
        total = northbound.get("total_net", 0) / 1e4  # 转亿元
        if total != 0:
            sign = "+" if total > 0 else ""
            lines.append(f"  北向资金(沪深港通): {sign}{total:.2f}亿 {'🔴' if total > 0 else '🟢'}")
            all_signals.append(("北向", 1 if total > 0 else (-1 if total < 0 else 0)))
        else:
            lines.append(f"  北向资金: 数据未更新(盘前或假期)")
    else:
        lines.append(f"  北向资金: 获取失败")

    if margin_bal:
        lines.append(f"  两融余额: {margin_bal:.2f}亿")
        # 判断两融趋势
        if margin_bal > 29000:
            lines.append(f"    两融余额处于较高水平，市场情绪活跃")
            all_signals.append(("两融", 1))
        elif margin_bal < 26000:
            lines.append(f"    两融余额偏低，市场谨慎")
            all_signals.append(("两融", -1))
        else:
            all_signals.append(("两融", 0))
    else:
        lines.append(f"  两融余额: 待接口更新")

    if "sh000001" in index_data:
        d = index_data["sh000001"]
        lines.append(f"  成交额: {d['turnover']:.1f}亿")
        prev_vol = None
        if klines_sh and len(klines_sh) >= 2:
            prev_vol = klines_sh[-2]["volume"]
            today_vol = klines_sh[-1]["volume"]
            ratio = today_vol / prev_vol if prev_vol else 1
            sign = "↑" if ratio > 1 else "↓"
            lines.append(f"  量能变化: {sign} {ratio:.2f}x")
            if ratio > 1.15:
                lines.append(f"    放量, 资金活跃")
                all_signals.append(("量能", 1))
            elif ratio < 0.85:
                lines.append(f"    缩量, 观望为主")
                all_signals.append(("量能", -1))
            else:
                all_signals.append(("量能", 0))
    lines.append("")

    # ===== 6. 外围市场 =====
    lines.append("【🌏 外围市场】")
    for key in ["NASDAQ", "DJI", "SP500"]:
        if key in global_data:
            item = global_data[key]
            if item["price"]:
                sign = "+" if item["change_pct"] >= 0 else ""
                lines.append(f"  {item['name']}: {item['price']:.0f} ({sign}{item['change_pct']:.2f}%)")

    hsi = get_hang_seng()
    if hsi:
        lines.append(f"  恒生指数: {hsi:.1f}")

    for key in ["USDCNH", "OIL", "GOLD"]:
        if key in global_data:
            item = global_data[key]
            sign = "+" if item["change_pct"] >= 0 else ""
            lines.append(f"  {item['name']}: {item['price']:.2f} ({sign}{item['change_pct']:.2f}%)")

    # 外围影响评分
    nasdaq = global_data.get("NASDAQ", {}).get("change_pct", 0)
    if nasdaq:
        all_signals.append(("美股", 1 if nasdaq > 0.5 else (-1 if nasdaq < -0.5 else 0)))
    lines.append("")

    # ===== 7. 宏观数据 =====
    lines.append("【📋 宏观指标（月）】")
    lines.append(f"  PMI: {MACRO_DATA['PMI']} ({MACRO_DATA['PMI_month']})  "
                 f"CPI: {MACRO_DATA['CPI']} ({MACRO_DATA['CPI_month']})")
    lines.append(f"  PPI: {MACRO_DATA['PPI']} ({MACRO_DATA['PPI_month']})  "
                 f"MLF: {MACRO_DATA['MLF']} ({MACRO_DATA['MLF_month']})")
    lines.append(f"  M1: {MACRO_DATA['M1']} ({MACRO_DATA['M1_month']})  "
                 f"M2: {MACRO_DATA['M2']} ({MACRO_DATA['M2_month']})")
    # 宏观判断
    if safe_float(MACRO_DATA.get("PMI", "49")) >= 50:
        all_signals.append(("PMI", 1))
    else:
        all_signals.append(("PMI", -1))
    if safe_float(MACRO_DATA.get("M2", "0").replace("%", "")) > 6:
        all_signals.append(("M2", 1))
    lines.append("")

    # ===== 8. 综合评分 =====
    lines.append("【⭐ 综合评分】")
    total_score = 0
    max_score = 0
    for name, score in all_signals:
        total_score += score
        max_score += 2  # 每个信号满分2分
    if max_score > 0:
        pct = int((total_score + max_score) / (2 * max_score) * 100)
    else:
        pct = 50

    # 多空判定
    if total_score >= 4:
        verdict = "偏多 📈"
        stars = "★★★★★" if total_score >= 6 else "★★★★☆"
    elif total_score >= 1:
        verdict = "中性偏多 ➡📈"
        stars = "★★★☆☆"
    elif total_score >= -1:
        verdict = "中性震荡 ➡➡"
        stars = "★★☆☆☆"
    elif total_score >= -4:
        verdict = "中性偏空 ➡📉"
        stars = "★☆☆☆☆"
    else:
        verdict = "偏空 📉"
        stars = "☆☆☆☆☆"

    lines.append(f"  当日倾向: {verdict} {stars}")
    lines.append(f"  综合评分: {pct}/100 (信号分 {total_score}/{max_score})")
    lines.append("")
    lines.append("  信号明细:")
    signal_emojis = {"均线": "📐", "MACD": "📊", "RSI": "📏", "涨跌比": "📋",
                     "北向": "💰", "两融": "📒", "量能": "📉", "美股": "🌏",
                     "PMI": "🏭", "M2": "💵", "布林带": "📦"}
    for name, score in all_signals:
        emoji = signal_emojis.get(name, "📌")
        if score > 0:
            lines.append(f"    {emoji} {name}: 偏多 (+{score})")
        elif score < 0:
            lines.append(f"    {emoji} {name}: 偏空 ({score})")
        else:
            lines.append(f"    {emoji} {name}: 中性 (0)")

    # 成交量均线
    if klines_sh and len(klines_sh) >= 10:
        vols = [k["volume"] for k in klines_sh[-10:]]
        vol_ma5 = sum(vols[-5:]) / 5
        vol_ma10 = sum(vols) / 10
        lines.append(f"    量均: VOL-MA5 {int(vol_ma5/1e4)}万手   VOL-MA10 {int(vol_ma10/1e4)}万手")

    lines.append("")
    lines.append("=" * 35)
    lines.append("⚠ 本分析仅供参考，不构成投资建议。")

    return verdict, "\n".join(lines)

# ===================== 推送 =====================
def push_to_wechat(title, content, token=PUSHPLUS_TOKEN):
    if not token:
        print("[WARN] 未配置 PUSHPLUS_TOKEN，跳过推送")
        return {"code": -1, "msg": "no token"}
    url = "https://www.pushplus.plus/send"
    payload = json.dumps({
        "token": token, "title": title,
        "content": content, "template": "txt"
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"code": -1, "msg": str(e)}

# ===================== 主程序 =====================
def main(force=False):
    if not force and not is_trading_day():
        print(f"[{today_str()}] 非交易日，跳过分析。")
        return

    print(f"[{today_str()}] ===== A股大盘深度分析 v2.0 =====")
    print("正在获取数据（网络不稳定会自动重试）...")

    index_data = retry_call(get_a_stock_index)
    klines_sh = retry_call(get_index_kline, args=("1.000001", 60))
    klines_sz = retry_call(get_index_kline, args=("0.399001", 60))
    klines_300 = retry_call(get_index_kline, args=("1.000300", 60))
    global_data = retry_call(get_global_markets)
    futures = retry_call(get_us_futures)
    adv_dec = retry_call(get_advance_decline)
    sector_inflows, sector_gainers = retry_call(get_sector_flow, args=(5,)) or ([], [])
    northbound = retry_call(get_northbound_flow)
    margin_bal = retry_call(get_margin_balance)

    print("数据获取完成，开始分析...")

    verdict, report = analyze_market(
        index_data, klines_sh, klines_sz, klines_300,
        global_data, futures, adv_dec,
        sector_inflows, sector_gainers,
        northbound, margin_bal
    )

    print(report)

    # 保存报告
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(report)

    # PushPlus 推送
    title = f"A股大盘分析 {today_str()} {verdict}"
    push_result = push_to_wechat(title, report)
    print(f"\nPushPlus 推送结果: {push_result}")
    if push_result.get("code") == 200:
        print("[OK] 微信推送成功！")
    else:
        print(f"[ERROR] 推送失败: {push_result.get('msg', 'unknown')}")

if __name__ == "__main__":
    force = "--force" in sys.argv or "FORCE" in os.environ
    main(force=force)
