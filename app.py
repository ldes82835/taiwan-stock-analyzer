"""
台股當沖分析系統 - Flask Backend v2.2
新增：產業族群、開盤強度、VWAP狀態
"""

from flask import Flask, render_template, jsonify, Response
from flask_cors import CORS
import requests
import urllib3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import math
import time

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)


@app.after_request
def discourage_indexing(response):
    # This is privacy hygiene, not authentication. It keeps compliant search
    # engines from listing a personal tool without changing how the owner uses it.
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response

# Reuse HTTPS connections and retry short-lived upstream failures.  The TWSE
# endpoints are the slowest part of a request, so connection pooling matters.
HTTP = requests.Session()
HTTP.headers.update(HEADERS if "HEADERS" in globals() else {})
HTTP.mount("https://", HTTPAdapter(
    pool_connections=8,
    pool_maxsize=16,
    max_retries=Retry(total=2, connect=2, read=1, backoff_factor=0.25,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(("GET",))),
))

_CACHE = {}
_CACHE_LOCK = Lock()


def cached(key, ttl, loader, stale_ttl=600):
    """Small in-memory stale-while-error cache suitable for one Render worker."""
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and now - item[0] < ttl:
            return item[1], True, False
    try:
        value = loader()
        with _CACHE_LOCK:
            _CACHE[key] = (now, value)
        return value, False, False
    except Exception:
        with _CACHE_LOCK:
            item = _CACHE.get(key)
        if item and now - item[0] < stale_ttl:
            return item[1], True, True
        raise

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/",
}
HTTP.headers.update(HEADERS)

# ─────────────────────────────────────────
#  產業族群對照表
# ─────────────────────────────────────────
SECTOR_MAP = {
    # 半導體製造
    "2330": "半導體", "2303": "半導體", "2344": "半導體",
    "2408": "半導體", "3711": "半導體", "6770": "半導體",
    "5347": "半導體", "2449": "半導體", "6147": "半導體",
    "2385": "半導體",
    # IC設計
    "2454": "IC設計", "2379": "IC設計", "3034": "IC設計",
    "5274": "IC設計", "2388": "IC設計", "3406": "IC設計",
    "6414": "IC設計", "2436": "IC設計", "3533": "IC設計",
    "3260": "IC設計", "3691": "IC設計", "4966": "IC設計",
    "6488": "IC設計", "5269": "IC設計", "6531": "IC設計",
    "3665": "IC設計", "3023": "IC設計", "4967": "IC設計",
    "3682": "IC設計", "6469": "IC設計", "3035": "IC設計",
    "4919": "IC設計", "3581": "IC設計", "3443": "IC設計",
    # 散熱模組
    "3017": "散熱模組", "2230": "散熱模組", "6120": "散熱模組",
    "3229": "散熱模組", "3324": "散熱模組", "6285": "散熱模組",
    "3033": "散熱模組",
    # 光通訊/高速傳輸
    "3491": "光通訊", "4979": "光通訊", "6088": "光通訊",
    "3380": "光通訊", "6176": "光通訊", "4182": "光通訊",
    "3707": "光通訊", "3413": "光通訊", "4924": "光通訊",
    "6719": "光通訊", "3455": "光通訊",
    # 伺服器/AI雲端
    "2317": "伺服器", "3231": "伺服器", "2356": "伺服器",
    "2324": "伺服器", "2353": "伺服器", "3060": "伺服器",
    "6582": "伺服器", "3704": "伺服器", "3032": "伺服器",
    "2382": "伺服器",
    # PCB/電路板
    "3037": "PCB", "2368": "PCB", "2374": "PCB",
    "2383": "PCB", "6274": "PCB", "8046": "PCB",
    "4977": "PCB", "3376": "PCB", "3673": "PCB",
    "4952": "PCB", "8131": "PCB", "3293": "PCB",
    "4938": "PCB",
    # 電源模組
    "6409": "電源模組", "3530": "電源模組", "6239": "電源模組",
    "2352": "電源模組", "3611": "電源模組",
    # 重電/電力
    "1519": "重電", "1503": "重電", "1504": "重電",
    "1514": "重電", "1528": "重電", "1521": "重電",
    "1507": "重電", "1605": "重電", "1516": "重電",
    # 面板/顯示器
    "2409": "面板", "3481": "面板", "8163": "面板", "3454": "面板",
    # 網通設備
    "2345": "網通", "3498": "網通", "4956": "網通",
    "6277": "網通", "3540": "網通", "2342": "網通",
    # 被動元件
    "2327": "被動元件", "2492": "被動元件", "2499": "被動元件",
    "2496": "被動元件", "2313": "被動元件",
    # 光學/鏡頭
    "3008": "光學鏡頭", "2439": "音響光學",
    # LED
    "2393": "LED", "2448": "LED",
    # 太陽能
    "3576": "太陽能", "6244": "太陽能",
    # 汽車/電動車
    "2206": "汽車", "2207": "汽車", "2201": "汽車",
    "2204": "汽車", "1590": "汽車零件", "2114": "汽車零件",
    "1536": "汽車零件", "1537": "汽車零件",
    # 金融
    "2882": "金融", "2886": "金融", "2884": "金融",
    "2885": "金融", "2891": "金融", "2892": "金融",
    "5880": "金融", "2883": "金融", "2887": "金融",
    "2888": "金融", "2890": "金融", "2880": "金融",
    "2881": "金融", "2889": "金融", "5876": "金融",
    # 航運/航空
    "2603": "航運", "2615": "航運", "2609": "航運",
    "2610": "航空", "2618": "航空",
    # 鋼鐵
    "2002": "鋼鐵", "2006": "鋼鐵", "2007": "鋼鐵",
    "2014": "鋼鐵", "2008": "鋼鐵",
    # 生技/醫療
    "1789": "生技", "4726": "生技", "4743": "生技",
    "6548": "生技", "1762": "生技", "4147": "生技",
    "4167": "生技", "6547": "生技", "4144": "生技",
    # 石化
    "1301": "石化", "1303": "石化", "1326": "石化", "1308": "石化",
    # 食品
    "1216": "食品", "1227": "食品", "1229": "食品", "2912": "食品",
    # 紡織
    "1402": "紡織", "1409": "紡織",
    # 建設
    "2915": "建設", "5522": "建設", "2501": "建設",
    # 其他
    "1802": "玻璃", "2105": "橡膠",
}

# ─────────────────────────────────────────
#  工具函式
# ─────────────────────────────────────────

def safe_float(s):
    if not s or str(s).strip() in ("--", "N/A", ""):
        return None
    try:
        return float(str(s).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def market_session():
    now = datetime.now()
    t = now.hour * 60 + now.minute
    if t < 9 * 60:
        return "pre", "盤前（尚未開盤）"
    if t < 13 * 60 + 30:
        return "intraday", "盤中（09:00–13:30 交易中）"
    return "post", "盤後（已收盤）"


def sub_session():
    now = datetime.now()
    t = now.hour * 60 + now.minute
    if t < 9 * 60:
        return "pre_open", "開盤前準備"
    if t <= 9 * 60 + 30:
        return "early", "早盤衝刺（09:00–09:30）"
    if t < 12 * 60:
        return "mid", "中場盤整（09:30–12:00）"
    if t < 13 * 60:
        return "late_mid", "尾盤前段（12:00–13:00）"
    if t < 13 * 60 + 25:
        return "late", "尾盤決戰（13:00–13:25）"
    if t <= 13 * 60 + 30:
        return "closing", "最後試算（13:25–13:30）"
    return "closed", "已收盤"


# ─────────────────────────────────────────
#  資料取得
# ─────────────────────────────────────────

def get_all_stocks():
    # 優先用 TWSE Open API（可從海外伺服器存取）
    url_open = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        r = HTTP.get(url_open, timeout=(3.5, 12))
        r.raise_for_status()
        items = r.json()
        if items and isinstance(items, list) and len(items) > 100:
            rows = []
            date_str = items[0].get("Date", datetime.now().strftime("%Y%m%d")) if items else ""
            for item in items:
                chg = str(item.get("Change", "0") or "0").strip()
                # 確保漲跌有 +/- 前綴，供後續計數使用
                if chg and chg[0] not in ("+", "-"):
                    try:
                        chg = ("+" if float(chg) >= 0 else "") + chg
                    except Exception:
                        pass
                row = [
                    item.get("Code", ""),
                    item.get("Name", ""),
                    str(item.get("TradeVolume", "0")).replace(",", ""),
                    str(item.get("TradeValue", "0")).replace(",", ""),
                    item.get("OpeningPrice", "0"),
                    item.get("HighestPrice", "0"),
                    item.get("LowestPrice", "0"),
                    item.get("ClosingPrice", "0"),
                    chg,
                ]
                rows.append(row)
            print(f"[OPENAPI OK] {len(rows)} 檔，date={date_str}")
            return rows, date_str
    except Exception as e:
        print(f"[OPENAPI ERROR] {e}")

    # 備用：舊版 TWSE 端點（台灣 IP 才能用）
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"
    try:
        r = HTTP.get(url, timeout=(3.5, 10))
        r.raise_for_status()
        body = r.json()
        if body.get("stat") == "OK":
            return body.get("data", []), body.get("date", "")
    except Exception as e:
        print(f"[TWSE ERROR] {e}")
    return [], ""


def _fetch_mis_index(ex_ch):
    url = (
        "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        f"?ex_ch={ex_ch}&json=1&delay=0"
    )
    try:
        r = HTTP.get(url, timeout=(3, 7))
        items = r.json().get("msgArray", [])
        if items:
            it = items[0]
            price = float(it.get("z") or it.get("y") or 0)
            prev  = float(it.get("y") or price)
            chg   = price - prev
            return {
                "price":      price,
                "change":     round(chg, 2),
                "change_pct": round(chg / prev * 100, 2) if prev else 0,
                "open":  float(it.get("o") or 0),
                "high":  float(it.get("h") or 0),
                "low":   float(it.get("l") or 0),
            }
    except Exception as e:
        print(f"[MIS ERROR {ex_ch}] {e}")
    return None


def get_market_index():
    return _fetch_mis_index("tse_t00.tw")


def get_otc_index():
    return _fetch_mis_index("otc_o00.tw")


def _get_realtime_chunk(codes):
    if not codes:
        return {}
    ex_ch = "|".join(f"tse_{c}.tw" for c in codes[:20])
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
    try:
        r = HTTP.get(url, timeout=(3, 7))
        result = {}
        for it in r.json().get("msgArray", []):
            code = it.get("c", "")
            z = safe_float(it.get("z"))
            y = safe_float(it.get("y"))
            v = safe_float(str(it.get("v", "0")).replace(",", ""))
            h = safe_float(it.get("h"))
            l = safe_float(it.get("l"))
            if not z:
                z = y
            if code and z and y:
                chg_pct   = round((z - y) / y * 100, 2)
                bid       = safe_float((it.get("b") or "").split("_")[0])
                ask       = safe_float((it.get("a") or "").split("_")[0])
                avg_price = round((h + l + z) / 3, 2) if h and l and z else z
                above_avg = z >= avg_price if avg_price else None
                result[code] = {
                    "realtime_price":      z,
                    "realtime_change_pct": chg_pct,
                    "realtime_volume_k":   int(v * 1000) if v else 0,
                    "bid": bid, "ask": ask,
                    "intraday_high": h, "intraday_low": l,
                    "avg_price": avg_price, "above_avg": above_avg,
                }
        return result
    except Exception as e:
        print(f"[REALTIME ERROR] {e}")
        return {}


def get_realtime_prices(codes):
    """Fetch up to 60 quotes in parallel batches instead of one slow request."""
    unique = list(dict.fromkeys(codes))[:60]
    chunks = [unique[i:i + 20] for i in range(0, len(unique), 20)]
    if not chunks:
        return {}

    def load():
        result = {}
        with ThreadPoolExecutor(max_workers=min(3, len(chunks))) as pool:
            for part in pool.map(_get_realtime_chunk, chunks):
                result.update(part)
        return result

    cache_key = "quotes:" + ",".join(unique)
    # Browser refreshes every 30 seconds; a 12-second cache prevents duplicate
    # requests from overlapping tabs without making the screen feel stale.
    return cached(cache_key, 12, load, stale_ttl=90)[0]


# ─────────────────────────────────────────
#  選股篩選
# ─────────────────────────────────────────

def screen_stocks(rows):
    candidates = []
    for row in rows:
        try:
            if len(row) < 9:
                continue
            code = row[0].strip()
            name = row[1].strip()
            if not (code.isdigit() and len(code) == 4):
                continue

            vol      = safe_float(row[2])
            turnover = safe_float(row[3])
            open_p   = safe_float(row[4])
            high_p   = safe_float(row[5])
            low_p    = safe_float(row[6])
            close_p  = safe_float(row[7])
            chg_str  = row[8].strip() if len(row) > 8 else "0"

            if not all([vol, open_p, high_p, low_p, close_p]):
                continue
            if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                continue
            if not (20 <= open_p <= 300):
                continue
            if vol < 3_000_000:
                continue

            amplitude = (high_p - low_p) / open_p * 100
            if amplitude < 3.0:
                continue

            change     = safe_float(chg_str) or 0.0
            prev_close = close_p - change
            chg_pct    = (change / prev_close * 100) if prev_close > 0 else 0.0
            if chg_pct < -8.0:
                continue

            day_range  = high_p - low_p
            momentum   = (close_p - low_p) / day_range * 100 if day_range > 0 else 50.0
            vol_m      = vol / 1_000_000

            vol_factor = round(vol_m ** 0.5, 2)
            amp_factor = round(amplitude, 2)
            mom_factor = round(momentum / 50, 2)
            score      = vol_factor * amp_factor * mom_factor

            # 開盤強度（跳空幅度）
            gap_pct = round((open_p - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0

            # 均價估算（(H+L+C)/3）及位階判斷
            vwap_est   = round((high_p + low_p + close_p) / 3, 2)
            above_vwap = close_p >= vwap_est

            candidates.append({
                "code": code, "name": name,
                "open": open_p, "high": high_p, "low": low_p, "close": close_p,
                "volume":     int(vol),
                "turnover":   int(turnover) if turnover else 0,
                "amplitude":  round(amplitude, 2),
                "change":     change,
                "change_pct": round(chg_pct, 2),
                "momentum":   round(momentum, 1),
                "score":      round(score, 2),
                "score_breakdown": {
                    "vol_factor": vol_factor,
                    "amp_factor": amp_factor,
                    "mom_factor": mom_factor,
                    "formula":    f"√{vol_m:.1f}M × {amplitude:.1f}% × {momentum/50:.2f}",
                    "total":      round(score, 1),
                },
                "sector":      SECTOR_MAP.get(code, "電子其他"),
                "gap_pct":     gap_pct,
                "vwap_est":    vwap_est,
                "above_vwap":  above_vwap,
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# ─────────────────────────────────────────
#  停損 / 停利計算
# ─────────────────────────────────────────

def tick_size(price):
    if price < 10: return 0.01
    if price < 50: return 0.05
    if price < 100: return 0.1
    if price < 500: return 0.5
    if price < 1000: return 1.0
    return 5.0


def to_tick(price, mode="nearest"):
    tick = tick_size(max(price, 0.01))
    units = price / tick
    units = math.floor(units) if mode == "floor" else math.ceil(units) if mode == "ceil" else round(units)
    decimals = 2 if tick < .1 else 1 if tick < 1 else 0
    return round(units * tick, decimals)


def calc_levels(stock, price=None, direction=None):
    """Risk-first plan. Supports both long and short and respects TWSE ticks."""
    direction = direction or stock.get("direction", "long")
    entry = price or stock.get("realtime_price") or stock["close"]
    high, low = stock["high"], stock["low"]
    day_range = max(high - low, entry * .012)
    # Use nearby structure, but cap single-trade price risk around 2% so a small
    # account is not forced into a large loss. A minimum avoids market noise.
    min_risk = max(entry * .006, tick_size(entry) * 3)
    max_risk = entry * .02
    structural = (entry - low) + tick_size(entry) * 2 if direction == "long" else (high - entry) + tick_size(entry) * 2
    risk = min(max(structural, min_risk, day_range * .18), max_risk)

    if direction == "short":
        stop_loss = to_tick(entry + risk, "ceil")
        tp1 = to_tick(entry - risk * 1.5, "floor")
        tp2 = to_tick(entry - risk * 2.2, "floor")
        zone_low, zone_high = to_tick(entry - risk * .15, "floor"), to_tick(entry + risk * .10, "ceil")
    else:
        stop_loss = to_tick(entry - risk, "floor")
        tp1 = to_tick(entry + risk * 1.5, "ceil")
        tp2 = to_tick(entry + risk * 2.2, "ceil")
        zone_low, zone_high = to_tick(entry - risk * .10, "floor"), to_tick(entry + risk * .15, "ceil")

    actual_risk = abs(entry - stop_loss)
    # Illustration for NT$100k: risk 0.75%, exposure capped at 35%.
    shares_by_risk = math.floor(750 / actual_risk) if actual_risk else 0
    shares_by_cash = math.floor(35000 / entry) if entry else 0
    suggested_shares = max(0, min(shares_by_risk, shares_by_cash))
    return {
        "entry": to_tick(entry), "entry_zone_low": zone_low, "entry_zone_high": zone_high,
        "stop_loss": stop_loss, "take_profit_1": tp1, "take_profit_2": tp2,
        "risk_pct": round(actual_risk / entry * 100, 2),
        "reward_risk_1": round(abs(tp1-entry) / actual_risk, 2) if actual_risk else 0,
        "reward_risk_2": round(abs(tp2-entry) / actual_risk, 2) if actual_risk else 0,
        "suggested_shares_100k": suggested_shares,
        "estimated_max_loss_100k": round(suggested_shares * actual_risk),
        "position_note": "以本金10萬、單筆風險0.75%、單檔投入上限35%試算；請依實際本金等比例調整",
    }


def intraday_decision(stock, rt):
    """Turn a liquid daily candidate into an actionable live trade/no-trade plan."""
    price = rt.get("realtime_price") if rt else stock["close"]
    change = rt.get("realtime_change_pct", stock["change_pct"]) if rt else stock["change_pct"]
    high = rt.get("intraday_high") or stock["high"] if rt else stock["high"]
    low = rt.get("intraday_low") or stock["low"] if rt else stock["low"]
    avg = rt.get("avg_price") if rt else stock.get("vwap_est")
    above = rt.get("above_avg") if rt else stock.get("above_vwap")
    spread_pct = 0.0
    if rt and rt.get("bid") and rt.get("ask") and price:
        spread_pct = (rt["ask"] - rt["bid"]) / price * 100
    range_pos = (price - low) / (high - low) * 100 if high and low and high > low else 50
    liquidity = min(25, math.log10(max(stock["turnover"], 1)) * 3)

    long_score = liquidity + min(22, max(0, change) * 3.2) + (18 if above else 0) + min(18, max(0, range_pos - 45) * .45)
    short_score = liquidity + min(22, max(0, -change) * 3.2) + (18 if above is False else 0) + min(18, max(0, 55 - range_pos) * .45)
    # Penalize chasing near the daily limit and names with a costly spread.
    chase_penalty = max(0, abs(change) - 6) * 6
    spread_penalty = max(0, spread_pct - .18) * 80
    long_score -= chase_penalty + spread_penalty
    short_score -= chase_penalty + spread_penalty
    direction = "long" if long_score >= short_score else "short"
    score = max(long_score, short_score)

    if score < 48 or spread_pct > .5:
        direction, action = "neutral", "wait"
        trigger = "訊號不足：等待價格重新站上/跌破盤中均價，且買賣價差收斂"
    elif direction == "long":
        action = "watch" if change > 6 or range_pos > 92 else "enter"
        trigger = f"回踩均價 {avg:.2f} 不破後轉強，或帶量突破 {high:.2f}" if avg else f"帶量突破 {high:.2f}"
    else:
        action = "watch" if change < -6 or range_pos < 8 else "enter"
        trigger = f"反彈均價 {avg:.2f} 不過後轉弱，或放量跌破 {low:.2f}" if avg else f"放量跌破 {low:.2f}"

    confidence = "A" if score >= 72 else "B" if score >= 58 else "C"
    return {
        "direction": direction, "action": action, "trade_score": round(max(0, min(100, score)), 1),
        "confidence": confidence, "trigger": trigger, "range_position": round(range_pos, 1),
        "spread_pct": round(spread_pct, 3),
        "short_warning": "放空前須確認可當沖資格、券源與強制回補時間" if direction == "short" else None,
    }


def build_reason(stock):
    parts = []
    vol_m = stock["volume"] / 1_000_000
    if vol_m >= 20:   parts.append(f"超大量 {vol_m:.0f}M 股")
    elif vol_m >= 10: parts.append(f"大量 {vol_m:.0f}M 股")
    else:             parts.append(f"量能 {vol_m:.1f}M 股")
    parts.append(f"振幅 {stock['amplitude']:.1f}%")
    if stock["momentum"] >= 75:    parts.append("強勢收高")
    elif stock["momentum"] >= 50:  parts.append("偏多走勢")
    else:                           parts.append("震盪量大")
    if stock["change_pct"] > 3:    parts.append(f"漲幅 +{stock['change_pct']:.1f}%")
    elif stock["change_pct"] < -2: parts.append(f"注意回調 {stock['change_pct']:.1f}%")
    return "  ｜  ".join(parts)


# ─────────────────────────────────────────
#  委託建議
# ─────────────────────────────────────────

def suggest_order_type(stock, rt):
    if rt:
        change_pct = rt.get("realtime_change_pct", stock["change_pct"])
        above_avg  = rt.get("above_avg")
    else:
        change_pct = stock["change_pct"]
        above_avg  = stock["momentum"] >= 50

    mom = stock["momentum"]

    if abs(change_pct) > 6:
        return {"type": "WAIT", "color": "neutral", "label": "漲跌過度，不追價",
                "tip": "價格已大幅偏離昨收，小資金最怕追價後被震出；等待拉回/反彈確認，不使用市價或 IOC 搶單。"}
    elif above_avg is True and change_pct > 1:
        return {"type": "ROD", "color": "blue", "label": "限價 ROD 等回踩",
                "tip": "多方仍占優，但只在進場區間用限價單等待；沒有回踩就放棄，不為了成交而追高。"}
    elif above_avg is False and change_pct < -1:
        return {"type": "ROD", "color": "green", "label": "限價 ROD 等反彈空點",
                "tip": "空方占優，等反彈不過均價再考慮放空；先確認可當沖與券源，不直接追殺低點。"}
    elif change_pct > 1 and mom > 55:
        return {"type": "ROD", "color": "amber", "label": "限價 ROD 等確認",
                "tip": "只在系統進場區間內掛限價單；若停損距離或買賣價差擴大，取消交易。"}
    else:
        return {"type": "WAIT", "color": "neutral", "label": "觀望等訊號",
                "tip": "目前盤勢方向不明，建議等待明確量能放大或方向確立後再進場，不急於下單。"}


# ─────────────────────────────────────────
#  盤前：開盤確認條件
# ─────────────────────────────────────────

def calc_open_conditions(stock):
    avg_5min    = stock["volume"] / 54
    confirm_vol = int(avg_5min * 1.5)
    chg = stock["change_pct"]
    mom = stock["momentum"]
    if chg > 5:
        strategy  = "強勢股，開盤若跳空 > 2% 建議等回測 5 日線再進場，避免追高"
        entry_tip = "等回測至昨收 ±1% 附近再進"
    elif chg > 0 and mom >= 70:
        strategy  = "多方格局，開盤量能確認後直接跟進，設好停損"
        entry_tip = "開盤5分鐘量 > 確認量後進場"
    elif chg < -3:
        strategy  = "注意反彈操作，量大跌深可觀察是否有止跌訊號"
        entry_tip = "等低點止穩 + 量縮再考慮進場"
    else:
        strategy  = "量能充裕，開盤方向確認後順勢操作"
        entry_tip = "開盤5分鐘量 > 確認量後進場"
    return {
        "confirm_volume":     confirm_vol,
        "confirm_volume_str": f"{confirm_vol // 1000:,} 張",
        "strategy":  strategy,
        "entry_tip": entry_tip,
    }


def tomorrow_setup(stock):
    """Rank next-session watch candidates without pretending today's close is an entry."""
    chg = stock["change_pct"]
    close_pos = stock["momentum"]
    turnover_m = stock.get("turnover", 0) / 1_000_000
    liquidity = min(24, math.log10(max(turnover_m, 1)) * 8)
    tradable_range = min(16, stock["amplitude"] * 2.2)

    # Continuation candidates need a decisive close; reversal-style guesses are
    # deliberately avoided because tomorrow has not supplied confirmation yet.
    long_score = liquidity + tradable_range + min(24, max(0, close_pos - 50) * .55) + min(16, max(0, chg) * 2.5)
    short_score = liquidity + tradable_range + min(24, max(0, 50 - close_pos) * .55) + min(16, max(0, -chg) * 2.5)

    # Limit-up/down proximity and oversized gaps leave little room for a small
    # account to enter with controlled risk on the following morning.
    overheat = max(0, abs(chg) - 6) * 8 + max(0, abs(stock.get("gap_pct", 0)) - 4) * 4
    long_score -= overheat
    short_score -= overheat
    direction = "long" if long_score >= short_score else "short"
    score = max(long_score, short_score)
    levels = calc_levels(stock, stock["close"], direction)

    if direction == "long":
        invalidation = f"開盤跌破 {levels['stop_loss']:.2f}，或前15分鐘始終無法站回昨收 {stock['close']:.2f}"
        if chg > 5:
            trigger = f"不追跳空；回測 {levels['entry_zone_low']:.2f}～{levels['entry_zone_high']:.2f} 止穩且重新站上後才做多"
        else:
            trigger = f"前5～15分鐘守住 {levels['entry_zone_low']:.2f}，再帶量突破 {levels['entry_zone_high']:.2f} 才做多"
    else:
        invalidation = f"開盤突破 {levels['stop_loss']:.2f}，或前15分鐘始終站在昨收 {stock['close']:.2f} 之上"
        if chg < -5:
            trigger = f"不追低；反彈 {levels['entry_zone_low']:.2f}～{levels['entry_zone_high']:.2f} 遇壓轉弱才放空"
        else:
            trigger = f"前5～15分鐘無法站回 {levels['entry_zone_high']:.2f}，再跌破 {levels['entry_zone_low']:.2f} 才放空"

    action = "watch" if score >= 55 else "wait"
    confidence = "A" if score >= 72 else "B" if score >= 60 else "C"
    return {
        **levels,
        "direction": direction,
        "action": action,
        "trade_score": round(max(0, min(100, score)), 1),
        "confidence": confidence,
        "trigger": trigger,
        "invalidation": invalidation,
        "short_warning": "明日放空前須確認可當沖資格、券源與強制回補時間" if direction == "short" else None,
    }


# ─────────────────────────────────────────
#  盤後：績效評估
# ─────────────────────────────────────────

def assess_performance(stock, levels):
    high  = stock["high"]; low = stock["low"]
    tp1   = levels["take_profit_1"]; tp2 = levels["take_profit_2"]
    sl    = levels["stop_loss"];     entry = levels["entry"]
    is_short = sl > entry
    hit_tp2 = low <= tp2 if is_short else high >= tp2
    hit_tp1 = low <= tp1 if is_short else high >= tp1
    hit_sl = high >= sl if is_short else low <= sl
    sign = -1 if is_short else 1
    if hit_tp2:
        result="tp2"; label="✅ 停利② 達成"; color="green2"
        profit=round((tp2-entry)/entry*100*sign,2)
        note=f"{'最低' if is_short else '最高'} {low if is_short else high:.2f} 觸及停利② {tp2:.2f}，報酬約 +{profit}%"
    elif hit_tp1:
        result="tp1"; label="✅ 停利① 達成"; color="green"
        profit=round((tp1-entry)/entry*100*sign,2)
        note=f"{'最低' if is_short else '最高'} {low if is_short else high:.2f} 觸及停利① {tp1:.2f}，報酬約 +{profit}%"
    elif hit_sl:
        result="sl"; label="❌ 觸及停損"; color="red"
        profit=round((sl-entry)/entry*100*sign,2)
        note=f"{'最高' if is_short else '最低'} {high if is_short else low:.2f} 觸及停損 {sl:.2f}，損失約 {profit}%"
    else:
        result="none"; label="⏳ 未觸發"; color="neutral"
        profit=round((stock["close"]-entry)/entry*100,2)
        note=f"收盤 {stock['close']:.2f}，未觸及任何條件，浮動 {'+' if profit>=0 else ''}{profit}%"
    return {"result":result,"label":label,"color":color,"profit_pct":profit,"note":note}


def build_common_result(session_type, session_label):
    def load_rows():
        value = get_all_stocks()
        if not value[0]:
            raise RuntimeError("TWSE returned no rows")
        return value

    # These three upstream calls are independent. Running them concurrently
    # changes normal latency from their sum to roughly the slowest one.
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows_future = pool.submit(cached, "all_stocks", 25 if session_type == "intraday" else 180, load_rows, 1800)
        index_future = pool.submit(cached, "market_index", 10 if session_type == "intraday" else 60, get_market_index, 300)
        otc_future = pool.submit(cached, "otc_index", 10 if session_type == "intraday" else 60, get_otc_index, 300)
        (raw_rows, data_date), rows_cached, rows_stale = rows_future.result()
        index_data, _, index_stale = index_future.result()
        otc_data, _, otc_stale = otc_future.result()
    ss_type, ss_label   = sub_session()
    result = {
        "status": session_type, "status_label": session_label,
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date":   data_date,
        "market_index": index_data,
        "otc_index":    otc_data,
        "sub_session":  {"type": ss_type, "label": ss_label},
        "freshness": {
            "market_rows_cached": rows_cached,
            "using_stale_fallback": bool(rows_stale or index_stale or otc_stale),
            "quotes_cache_seconds": 12,
        },
        "recommendations": [], "market_stats": {}, "error": None,
    }
    if not raw_rows:
        result["error"] = "無法取得市場數據。可能原因：今日為非交易日、TWSE API 暫時無回應。"
        return result, []
    up   = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("+"))
    down = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("-"))
    candidates = screen_stocks(raw_rows)
    result["market_stats"] = {"total": len(raw_rows), "up": up, "down": down, "filtered": len(candidates)}
    if not candidates:
        result["error"] = "今日無符合當沖篩選條件的標的（振幅≥3%、成交量≥3000張、股價20–300元）。"
    return result, candidates


# ─────────────────────────────────────────
#  Flask 路由
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/pre")
def api_pre():
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)
    recs = []
    for stock in candidates[:5]:
        open_cond = calc_open_conditions(stock)
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        levels    = calc_levels(stock, direction=direction if direction != "neutral" else "long")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({**stock, **levels, "direction": direction, "strength": strength,
                     "reason": build_reason(stock), "open_conditions": open_cond})
    result["recommendations"] = recs
    return jsonify(result)


@app.route("/api/intraday")
def api_intraday():
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)
    # Use daily data only to form a liquid universe, then rerank with live data.
    universe = candidates[:45]
    realtime = get_realtime_prices([s["code"] for s in universe])
    ranked = []
    for stock in universe:
        rt = realtime.get(stock["code"])
        if not rt:
            continue
        decision = intraday_decision(stock, rt)
        ranked.append((decision["trade_score"], stock, rt, decision))
    ranked.sort(key=lambda item: item[0], reverse=True)

    recs = []
    for _, stock, rt, decision in ranked[:5]:
        direction = decision["direction"]
        levels = calc_levels(stock, rt.get("realtime_price"), direction if direction != "neutral" else "long")
        strength = "strong" if decision["trade_score"] >= 72 else ("medium" if decision["trade_score"] >= 58 else "weak")
        recs.append({**stock, **levels, **decision, "strength": strength,
                     "reason": build_reason(stock), "realtime": rt,
                     "order_tip": suggest_order_type(stock, rt)})
    if not recs:
        result["error"] = "即時報價暫時不可用；為避免用舊資料產生交易訊號，本次不推薦標的。"
    result["recommendations"] = recs
    return jsonify(result)


@app.route("/api/post")
def api_post():
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)
    ranked = []
    # Evaluate every liquid candidate here; the original daily score favors
    # strong closes and would otherwise hide valid short setups near the bottom.
    for stock in candidates:
        setup = tomorrow_setup(stock)
        ranked.append((setup["trade_score"], stock, setup))
    ranked.sort(key=lambda item: item[0], reverse=True)
    recs = []
    for _, stock, setup in ranked[:5]:
        strength = "strong" if setup["trade_score"] >= 72 else ("medium" if setup["trade_score"] >= 60 else "weak")
        recs.append({**stock, **setup, "strength": strength,
                     "reason": build_reason(stock), "setup_type": "tomorrow"})
    result["recommendations"] = recs
    result["analysis_label"] = "明日開盤候選；須等待開盤後觸發條件成立，不代表預測必漲或必跌"
    return jsonify(result)


@app.route("/api/analysis")
def api_analysis():
    return api_intraday()


@app.route("/health")
def health():
    return "OK", 200


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("  台股當沖分析系統（三時段版 v2.2）")
    print(f"  port={port}")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=port)
