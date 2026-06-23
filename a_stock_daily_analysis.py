#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import re
import urllib.request
from datetime import datetime

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")

HOLIDAYS_2026 = {
    "01-01", "01-02",
    "02-16", "02-17", "02-18", "02-19", "02-20",
    "04-04", "04-05", "04-06",
    "05-01", "05-02", "05-03", "05-04", "05-05",
    "06-20", "06-21", "06-22",
    "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07", "10-08",
}

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

def fetch_text(url, headers=None, timeout=15):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR: {e}"

def get_a_stock_index():
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
        if code == "sh000001": name = "上证指数"
        elif code == "sz399001": name = "深证成指"
        elif code == "sz399006": name = "创业板指"
        elif code == "sh000300": name = "沪深300"
        elif code == "sh000016": name = "上证50"
        elif code == "sz399005": name = "中小板指"
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

def get_index_kline(secid, lmt=30):
    url = (
        f"http://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0&end=20500101&lmt={lmt}"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    if "data" not in data or data["data"] is None:
        return []
    klines = data["data"].get("klines", [])
    parsed = []
    for k in klines:
        parts = k.split(",")
        if len(parts) >= 6:
            parsed.append({
                "date": parts[0], "open": float(parts[1]),
                "close": float(parts[2]), "high": float(parts[3]),
                "low": float(parts[4]), "volume": int(parts[5]),
            })
    return parsed

def get_ma(klines, n):
    closes = [k["close"] for k in klines]
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def get_global_markets():
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
        if len(parts) < 2:
            continue
        try:
            if code == "fx_susdcnh":
                result["USDCNH"] = {"name": "离岸人民币", "price": float(parts[1]), "change_pct": float(parts[3]) if len(parts) > 3 else 0}
            elif code == "hf_CL":
                result["OIL"] = {"name": "WTI原油", "price": float(parts[0]) if parts[0] else 0, "change_pct": float(parts[1]) if len(parts) > 1 and parts[1] else 0}
            elif code == "hf_GC":
                result["GOLD"] = {"name": "黄金", "price": float(parts[0]) if parts[0] else 0, "change_pct": float(parts[1]) if len(parts) > 1 and parts[1] else 0}
            elif code in ("gb_ixic", "gb_dji", "gb_GSPC"):
                name_map = {"gb_ixic": "纳斯达克", "gb_dji": "道琼斯", "gb_GSPC": "标普500"}
                result[code] = {"name": name_map.get(code, code), "price": float(parts[1]) if len(parts) > 1 else 0, "change_pct": float(parts[3]) if len(parts) > 3 else 0}
        except (ValueError, IndexError):
            continue
    return result

def get_us_futures():
    codes = "hf_NQ,hf_ES"
    url = f"http://hq.sinajs.cn/list={codes}"
    text = fetch_text(url, headers={"Referer": "http://finance.sina.com.cn"})
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
            price = float(parts[6]) if len(parts) > 6 else 0
            prev = float(parts[14]) if len(parts) > 14 else 0
            change_pct = ((price - prev) / prev * 100) if prev else 0
            result[code] = {"name": "纳指100期货" if code == "hf_NQ" else "标普500期货", "price": price, "change_pct": change_pct}
        except (ValueError, IndexError):
            continue
    return result

def analyze_market(index_data, klines_sh, global_data, futures):
    today = datetime.now().strftime("%Y年%m月%d日")
    lines = [f"A股大盘分析报告 - {today}", "=" * 30, ""]
    lines.append("【主要指数】")
    for code in ["sh000001", "sz399001", "sz399006", "sh000300"]:
        if code not in index_data:
            continue
        d = index_data[code]
        sign = "+" if d["change_pct"] >= 0 else ""
        lines.append(f"  {d['name']}: {d['price']:.2f} ({sign}{d['change_pct']:.2f}%)")
    lines.append("")
    lines.append("【均线状态】")
    ma_signals = []
    if klines_sh and len(klines_sh) >= 20:
        ma5 = get_ma(klines_sh, 5)
        ma20 = get_ma(klines_sh, 20)
        current = klines_sh[-1]["close"]
        lines.append(f"  上证指数: 现价 {current:.2f}")
        lines.append(f"    MA5:  {ma5:.2f} {'▲' if current > ma5 else '▼'}")
        lines.append(f"    MA20: {ma20:.2f} {'▲' if current > ma20 else '▼'}")
        if current > ma5 > ma20:
            ma_signals.append("上证多头排列，短期趋势向上")
        elif current < ma5 < ma20:
            ma_signals.append("上证空头排列，短期趋势向下")
        elif current > ma5 and current < ma20:
            ma_signals.append("上证上穿MA5但未过MA20，处于反弹试探")
        elif current < ma5 and current > ma20:
            ma_signals.append("上证跌破MA5但MA20有支撑，短期回调")
        else:
            ma_signals.append("上证均线交织，方向不明")
    else:
        lines.append("  上证指数: 均线数据不足")
    secid_300 = "1.000300"
    klines_300 = get_index_kline(secid_300, 25)
    if klines_300 and len(klines_300) >= 20:
        ma5_300 = get_ma(klines_300, 5)
        ma20_300 = get_ma(klines_300, 20)
        current_300 = klines_300[-1]["close"]
        lines.append(f"  沪深300: 现价 {current_300:.2f}")
        lines.append(f"    MA5:  {ma5_300:.2f} {'▲' if current_300 > ma5_300 else '▼'}")
        lines.append(f"    MA20: {ma20_300:.2f} {'▲' if current_300 > ma20_300 else '▼'}")
    else:
        lines.append("  沪深300: 均线数据不足")
    lines.append("")
    lines.append("【成交量】")
    if "sh000001" in index_data:
        d = index_data["sh000001"]
        lines.append(f"  上证成交额: {d['turnover']:.1f} 亿元")
        if klines_sh and len(klines_sh) >= 2:
            prev_vol = klines_sh[-2]["volume"]
            today_vol = klines_sh[-1]["volume"]
            ratio = today_vol / prev_vol if prev_vol else 1
            sign = "↑" if ratio > 1 else "↓"
            lines.append(f"  较上一交易日: {sign} {ratio:.2f}x")
            if ratio > 1.2:
                ma_signals.append("成交量放大，资金活跃度提升")
            elif ratio < 0.8:
                ma_signals.append("成交量萎缩，观望情绪浓厚")
    lines.append("")
    lines.append("【外围市场】")
    for key, item in global_data.items():
        sign = "+" if item["change_pct"] >= 0 else ""
        lines.append(f"  {item['name']}: {sign}{item['change_pct']:.2f}%")
    for key, item in futures.items():
        sign = "+" if item["change_pct"] >= 0 else ""
        lines.append(f"  {item['name']}: {sign}{item['change_pct']:.2f}%")
    lines.append("")
    lines.append("【综合判断】")
    score = 0
    total = 0
    if klines_sh and len(klines_sh) >= 20:
        ma5 = get_ma(klines_sh, 5)
        ma20 = get_ma(klines_sh, 20)
        current = klines_sh[-1]["close"]
        if current > ma5 > ma20:
            score += 2; total += 2
        elif current > ma5:
            score += 1; total += 2
        elif current < ma5 < ma20:
            score -= 1; total += 2
        else:
            total += 2
    if futures:
        nq = futures.get("hf_NQ", {}).get("change_pct", 0)
        es = futures.get("hf_ES", {}).get("change_pct", 0)
        avg = (nq + es) / 2
        if avg > 0.5: score += 1
        elif avg < -0.5: score -= 1
        total += 1
    if "USDCNH" in global_data:
        usd = global_data["USDCNH"]["price"]
        if usd > 7.25:
            score -= 1
            lines.append("  ⚠ 离岸人民币偏弱（>7.25），北向资金承压")
        elif usd < 7.15:
            score += 1
            lines.append("  ✓ 离岸人民币偏强，利于外资流入")
        total += 1
    if score >= 2:
        verdict = "偏多"
    elif score >= 0:
        verdict = "中性偏谨慎"
    else:
        verdict = "偏空"
    lines.append(f"  当日倾向: {verdict}")
    lines.append(f"  信号汇总: {'; '.join(ma_signals) if ma_signals else '暂无明确信号'}")
    lines.append("")
    lines.append("=" * 30)
    lines.append("⚠ 本分析仅供参考，不构成投资建议")
    return verdict, "\n".join(lines)

def push_to_wechat(title, content, token=PUSHPLUS_TOKEN):
    if not token:
        print("[WARN] 未配置 PUSHPLUS_TOKEN，跳过推送")
        return {"code": -1, "msg": "no token"}
    url = "https://www.pushplus.plus/send"
    payload = json.dumps({"token": token, "title": title, "content": content, "template": "txt"}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"code": -1, "msg": str(e)}

def main(force=False):
    if not force and not is_trading_day():
        print(f"[{today_str()}] 非交易日，跳过分析。")
        return
    print(f"[{today_str()}] 开始获取A股大盘数据...")
    index_data = get_a_stock_index()
    klines_sh = get_index_kline("1.000001", 25)
    global_data = get_global_markets()
    futures = get_us_futures()
    print("数据获取完成，开始分析...")
    verdict, report = analyze_market(index_data, klines_sh, global_data, futures)
    print(report)
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    title = f"A股大盘分析 - {today_str()} [{verdict}]"
    push_result = push_to_wechat(title, report)
    print(f"PushPlus 推送结果: {push_result}")
    if push_result.get("code") == 200:
        print("[OK] 推送成功！")
    else:
        print(f"[ERROR] 推送失败: {push_result}")

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv or "FORCE" in os.environ
    main(force=force)
