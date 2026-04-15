"""
台股當沖分析系統 - Flask Backend
三時段獨立分析：盤前 / 盤中即時 / 盤後總結
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


def get_market_index():
    url = (
        "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        "?ex_ch=tse_t00.tw&json=1&delay=0"
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
        print(f"[INDEX ERROR] {e}")
    return None


def get_realtime_prices(codes):
    """從 TWSE MIS API 取得即時報價（盤中用）"""
    if not codes:
        return {}
    ex_ch = "|".join(f"tse_{c}.tw" for c in codes[:20])
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        result = {}
        for it in r.json().get("msgArray", []):
            code = it.get("c", "")
            z = safe_float(it.get("z"))   # 成交價
            y = safe_float(it.get("y"))   # 昨收
            v = safe_float(str(it.get("v", "0")).replace(",", ""))  # 成交量(千股)
            if not z:
                z = y
            if code and z and y:
                chg_pct = round((z - y) / y * 100, 2)
                result[code] = {
                    "realtime_price":      z,
                    "realtime_change_pct": chg_pct,
                    "realtime_volume_k":   int(v * 1000) if v else 0,
                    "bid": safe_float((it.get("b") or "").split("_")[0]),
                    "ask": safe_float((it.get("a") or "").split("_")[0]),
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

            vol     = safe_float(row[2])
            turnover= safe_float(row[3])
            open_p  = safe_float(row[4])
            high_p  = safe_float(row[5])
            low_p   = safe_float(row[6])
            close_p = safe_float(row[7])
            chg_str = row[8].strip() if len(row) > 8 else "0"

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

            change    = safe_float(chg_str) or 0.0
            prev_close = close_p - change
            chg_pct   = (change / prev_close * 100) if prev_close > 0 else 0.0
            if chg_pct < -8.0:
                continue

            day_range = high_p - low_p
            momentum  = (close_p - low_p) / day_range * 100 if day_range > 0 else 50.0
            vol_m     = vol / 1_000_000
            score     = (vol_m ** 0.5) * amplitude * (momentum / 50)

            candidates.append({
                "code": code, "name": name,
                "open": open_p, "high": high_p, "low": low_p, "close": close_p,
                "volume": int(vol),
                "turnover": int(turnover) if turnover else 0,
                "amplitude": round(amplitude, 2),
                "change": change,
                "change_pct": round(chg_pct, 2),
                "momentum": round(momentum, 1),
                "score": score,
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# ─────────────────────────────────────────
#  停損 / 停利計算
# ─────────────────────────────────────────

def calc_levels(stock):
    entry = stock["close"]
    low   = stock["low"]
    sl_low   = round(low  * 0.995, 2)
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
        "risk_pct": round(risk / entry * 100, 2),
        "reward_risk_1": rr1, "reward_risk_2": rr2,
    }


def build_reason(stock):
    parts = []
    vol_m = stock["volume"] / 1_000_000
    if vol_m >= 20:   parts.append(f"超大量 {vol_m:.0f}M 股")
    elif vol_m >= 10: parts.append(f"大量 {vol_m:.0f}M 股")
    else:             parts.append(f"量能 {vol_m:.1f}M 股")
    parts.append(f"振幅 {stock['amplitude']:.1f}%")
    if stock["momentum"] >= 75:   parts.append("強勢收高（近日高）")
    elif stock["momentum"] >= 50: parts.append("偏多走勢")
    else:                          parts.append("震盪量大")
    if stock["change_pct"] > 3:   parts.append(f"漲幅 +{stock['change_pct']:.1f}%")
    elif stock["change_pct"] < -2: parts.append(f"注意回調 {stock['change_pct']:.1f}%")
    return "  ｜  ".join(parts)


# ─────────────────────────────────────────
#  盤前：開盤確認條件
# ─────────────────────────────────────────

def calc_open_conditions(stock):
    """計算開盤後5分鐘量能確認條件"""
    # 昨日總量 / 54 個5分K = 每5分K平均量；開盤首5分達到1.5x算確認
    avg_5min = stock["volume"] / 54
    confirm_vol = int(avg_5min * 1.5)

    chg = stock["change_pct"]
    mom = stock["momentum"]

    if chg > 5:
        strategy = "強勢股，開盤若跳空 > 2% 建議等回測 5 日線再進場，避免追高"
        entry_tip = "等回測至昨收 ±1% 附近再進"
    elif chg > 0 and mom >= 70:
        strategy = "多方格局，開盤量能確認後直接跟進，設好停損"
        entry_tip = "開盤5分鐘量 > 確認量後進場"
    elif chg < -3:
        strategy = "注意反彈操作，量大跌深可觀察是否有止跌訊號"
        entry_tip = "等低點止穩 + 量縮再考慮進場"
    else:
        strategy = "量能充裕，開盤方向確認後順勢操作"
        entry_tip = "開盤5分鐘量 > 確認量後進場"

    return {
        "confirm_volume": confirm_vol,
        "confirm_volume_str": f"{confirm_vol // 1000:,} 張",
        "strategy": strategy,
        "entry_tip": entry_tip,
    }


# ─────────────────────────────────────────
#  盤後：績效評估
# ─────────────────────────────────────────

def assess_performance(stock, levels):
    """評估今日推薦是否觸及停損/停利"""
    high  = stock["high"]
    low   = stock["low"]
    tp1   = levels["take_profit_1"]
    tp2   = levels["take_profit_2"]
    sl    = levels["stop_loss"]
    entry = levels["entry"]

    if high >= tp2:
        result = "tp2"
        label  = "✅ 停利② 達成"
        color  = "green2"
        profit = round((tp2 - entry) / entry * 100, 2)
        note   = f"最高 {high:.2f} 超越停利② {tp2:.2f}，報酬約 +{profit}%"
    elif high >= tp1:
        result = "tp1"
        label  = "✅ 停利① 達成"
        color  = "green"
        profit = round((tp1 - entry) / entry * 100, 2)
        note   = f"最高 {high:.2f} 觸及停利① {tp1:.2f}，報酬約 +{profit}%"
    elif low <= sl:
        result = "sl"
        label  = "❌ 觸及停損"
        color  = "red"
        profit = round((sl - entry) / entry * 100, 2)
        note   = f"最低 {low:.2f} 跌破停損 {sl:.2f}，損失約 {profit}%"
    else:
        result = "none"
        label  = "⏳ 未觸發"
        color  = "neutral"
        profit = round((stock["close"] - entry) / entry * 100, 2)
        note   = f"收盤 {stock['close']:.2f}，未觸及任何條件，浮動 {'+' if profit >= 0 else ''}{profit}%"

    return {"result": result, "label": label, "color": color,
            "profit_pct": profit, "note": note}


def build_common_result(session_type, session_label):
    raw_rows, data_date = get_all_stocks()
    index_data          = get_market_index()
    result = {
        "status": session_type, "status_label": session_label,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": data_date, "market_index": index_data,
        "recommendations": [], "market_stats": {}, "error": None,
    }
    if not raw_rows:
        result["error"] = "無法取得市場數據。可能原因：今日為非交易日、TWSE API 暫時無回應。"
        return result, []
    up   = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("+"))
    down = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("-"))
    candidates = screen_stocks(raw_rows)
    result["market_stats"] = {
        "total": len(raw_rows), "up": up, "down": down,
        "filtered": len(candidates),
    }
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
    """盤前分析：附帶開盤確認條件"""
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)

    recs = []
    for stock in candidates[:5]:
        levels = calc_levels(stock)
        open_cond = calc_open_conditions(stock)
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({
            **stock, **levels,
            "direction": direction, "strength": strength,
            "reason": build_reason(stock),
            "open_conditions": open_cond,
        })
    result["recommendations"] = recs
    return jsonify(result)


@app.route("/api/intraday")
def api_intraday():
    """盤中即時：加入即時報價疊加"""
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)

    top10_codes = [s["code"] for s in candidates[:10]]
    realtime    = get_realtime_prices(top10_codes)

    recs = []
    for stock in candidates[:5]:
        levels  = calc_levels(stock)
        rt      = realtime.get(stock["code"], {})
        chg_pct = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({
            **stock, **levels,
            "direction": direction, "strength": strength,
            "reason": build_reason(stock),
            "realtime": rt if rt else None,
        })
    result["recommendations"] = recs
    return jsonify(result)


@app.route("/api/post")
def api_post():
    """盤後總結：績效評估 + 明日觀察清單"""
    session_type, session_label = market_session()
    result, candidates = build_common_result(session_type, session_label)
    if result["error"] or not candidates:
        return jsonify(result)

    recs = []
    for stock in candidates[:5]:
        levels     = calc_levels(stock)
        perf       = assess_performance(stock, levels)
        chg_pct    = stock["change_pct"]
        direction  = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength   = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({
            **stock, **levels,
            "direction": direction, "strength": strength,
            "reason": build_reason(stock),
            "performance": perf,
        })

    # 明日觀察清單：從候選股中取 6~10 名
    tomorrow = []
    for stock in candidates[5:10]:
        levels = calc_levels(stock)
        tomorrow.append({
            "code": stock["code"], "name": stock["name"],
            "close": stock["close"], "amplitude": stock["amplitude"],
            "volume_lots": stock["volume"] // 1000,
            "change_pct": stock["change_pct"],
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "take_profit_1": levels["take_profit_1"],
        })

    result["recommendations"]   = recs
    result["tomorrow_watchlist"] = tomorrow
    return jsonify(result)


@app.route("/api/analysis")
def api_analysis():
    """保留原有 API（向下相容）"""
    return api_intraday()


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("  台股當沖分析系統（三時段版）")
    print(f"  port={port}")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=port)
