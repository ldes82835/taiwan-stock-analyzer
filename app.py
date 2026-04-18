"""
台股當沖分析系統 - Flask Backend v2.2
新增：產業族群、開盤強度、VWAP狀態
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

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
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
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
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
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


def get_realtime_prices(codes):
    if not codes:
        return {}
    ex_ch = "|".join(f"tse_{c}.tw" for c in codes[:20])
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
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

def calc_levels(stock):
    entry    = stock["close"]
    low      = stock["low"]
    sl_low   = round(low   * 0.995, 2)
    sl_fixed = round(entry * 0.985, 2)
    stop_loss = max(sl_low, sl_fixed)
    risk    = entry - stop_loss
    tp1_r   = round(entry + risk * 1.5, 2)
    tp1_f   = round(entry * 1.020, 2)
    tp1     = min(tp1_r, tp1_f)
    tp2_r   = round(entry + risk * 2.5, 2)
    tp2_f   = round(entry * 1.035, 2)
    tp2     = max(tp2_r, tp2_f)
    rr1 = round((tp1 - entry) / risk, 2) if risk > 0 else 0
    rr2 = round((tp2 - entry) / risk, 2) if risk > 0 else 0
    return {
        "entry": entry, "stop_loss": stop_loss,
        "take_profit_1": round(tp1, 2), "take_profit_2": round(tp2, 2),
        "risk_pct":      round(risk / entry * 100, 2),
        "reward_risk_1": rr1, "reward_risk_2": rr2,
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

    if change_pct > 4 and mom > 70:
        return {"type": "IOC", "color": "red",  "label": "建議 IOC 搶單",
                "tip": "強勢突破動能中，建議用 IOC（立即成交否則取消）搶進，避免掛單未成交後反被套在高點。"}
    elif above_avg is True and change_pct > 1:
        return {"type": "ROD", "color": "blue", "label": "站上均價 ROD 追進",
                "tip": "股價站上盤中均價估算線，多方格局相對確立，可掛 ROD（當日有效）在現價附近分批布局。"}
    elif change_pct < -2 or (above_avg is False and mom < 40):
        return {"type": "ROD", "color": "green", "label": "支撐位 ROD 低接",
                "tip": "股價回測至均價估算線下方，可掛 ROD 在關鍵支撐位耐心等候，停損設在最近低點下方。"}
    elif change_pct > 1 and mom > 55:
        return {"type": "ROD", "color": "amber", "label": "順勢 ROD 跟進",
                "tip": "走勢偏多但未到強勢突破，建議掛 ROD 在合理進場點，切勿追高，設好停損再操作。"}
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


# ─────────────────────────────────────────
#  盤後：績效評估
# ─────────────────────────────────────────

def assess_performance(stock, levels):
    high  = stock["high"]; low = stock["low"]
    tp1   = levels["take_profit_1"]; tp2 = levels["take_profit_2"]
    sl    = levels["stop_loss"];     entry = levels["entry"]
    if high >= tp2:
        result="tp2"; label="✅ 停利② 達成"; color="green2"
        profit=round((tp2-entry)/entry*100,2)
        note=f"最高 {high:.2f} 超越停利② {tp2:.2f}，報酬約 +{profit}%"
    elif high >= tp1:
        result="tp1"; label="✅ 停利① 達成"; color="green"
        profit=round((tp1-entry)/entry*100,2)
        note=f"最高 {high:.2f} 觸及停利① {tp1:.2f}，報酬約 +{profit}%"
    elif low <= sl:
        result="sl"; label="❌ 觸及停損"; color="red"
        profit=round((sl-entry)/entry*100,2)
        note=f"最低 {low:.2f} 跌破停損 {sl:.2f}，損失約 {profit}%"
    else:
        result="none"; label="⏳ 未觸發"; color="neutral"
        profit=round((stock["close"]-entry)/entry*100,2)
        note=f"收盤 {stock['close']:.2f}，未觸及任何條件，浮動 {'+' if profit>=0 else ''}{profit}%"
    return {"result":result,"label":label,"color":color,"profit_pct":profit,"note":note}


def build_common_result(session_type, session_label):
    raw_rows, data_date = get_all_stocks()
    index_data          = get_market_index()
    otc_data            = get_otc_index()
    ss_type, ss_label   = sub_session()
    result = {
        "status": session_type, "status_label": session_label,
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date":   data_date,
        "market_index": index_data,
        "otc_index":    otc_data,
        "sub_session":  {"type": ss_type, "label": ss_label},
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
        levels    = calc_levels(stock)
        open_cond = calc_open_conditions(stock)
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
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
    top10_codes = [s["code"] for s in candidates[:10]]
    realtime    = get_realtime_prices(top10_codes)
    recs = []
    for stock in candidates[:5]:
        levels    = calc_levels(stock)
        rt        = realtime.get(stock["code"])
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        order_tip = suggest_order_type(stock, rt)
        recs.append({**stock, **levels, "direction": direction, "strength": strength,
                     "reason": build_reason(stock), "realtime": rt if rt else None,
                     "order_tip": order_tip})
    result["recommendations"] = recs
    return jsonify(result)


@app.route("/api/post")
def api_post():
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)
    recs = []
    for stock in candidates[:5]:
        levels    = calc_levels(stock)
        perf      = assess_performance(stock, levels)
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({**stock, **levels, "direction": direction, "strength": strength,
                     "reason": build_reason(stock), "performance": perf})
    tomorrow = []
    for stock in candidates[5:10]:
        levels = calc_levels(stock)
        tomorrow.append({"code": stock["code"], "name": stock["name"],
                         "close": stock["close"], "amplitude": stock["amplitude"],
                         "volume_lots": stock["volume"] // 1000,
                         "change_pct": stock["change_pct"], "sector": stock["sector"],
                         "entry": levels["entry"], "stop_loss": levels["stop_loss"],
                         "take_profit_1": levels["take_profit_1"]})
    result["recommendations"]    = recs
    result["tomorrow_watchlist"] = tomorrow
    return jsonify(result)


@app.route("/api/analysis")
def api_analysis():
    return api_intraday()


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("  台股當沖分析系統（三時段版 v2.2）")
    print(f"  port={port}")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=port)
