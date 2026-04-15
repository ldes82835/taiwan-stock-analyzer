"""
台股當沖分析系統 - Flask Backend
整合 TWSE 官方 API，篩選當沖標的並計算停損/停利點位
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
import urllib3
from datetime import datetime

# TWSE 憑證缺少 Subject Key Identifier，關閉驗證並壓制警告
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
#  資料取得
# ─────────────────────────────────────────

def safe_float(s: str):
    """安全解析數字字串（含千分位、正負號）"""
    if not s or s.strip() in ("--", "N/A", ""):
        return None
    try:
        return float(s.replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def get_all_stocks():
    """從 TWSE 取得當日全部上市股票資料"""
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        r.raise_for_status()
        body = r.json()
        if body.get("stat") == "OK":
            return body.get("data", []), body.get("date", "")
    except Exception as e:
        print(f"[TWSE STOCK_DAY_ALL ERROR] {e}")
    return [], ""


def get_market_index():
    """取得加權指數即時行情"""
    url = (
        "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        "?ex_ch=tse_t00.tw&json=1&delay=0"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        items = r.json().get("msgArray", [])
        if items:
            it = items[0]
            # z = 成交價, y = 昨收, o = 開盤, h = 最高, l = 最低
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
        print(f"[INDEX API ERROR] {e}")
    return None


# ─────────────────────────────────────────
#  盤況狀態
# ─────────────────────────────────────────

def market_session():
    """判斷目前盤況（盤前 / 盤中 / 盤後）"""
    now = datetime.now()
    t = now.hour * 60 + now.minute
    if t < 8 * 60 + 30:
        return "pre",      "盤前（尚未開盤）"
    if t < 9 * 60:
        return "pre",      "盤前（08:30 撮合準備中）"
    if t < 13 * 60 + 30:
        return "intraday", "盤中（09:00–13:30 交易中）"
    if t < 14 * 60 + 30:
        return "post",     "盤後（13:30 已收盤）"
    return "post",         "盤後（次日盤前準備）"


# ─────────────────────────────────────────
#  選股篩選
# ─────────────────────────────────────────

# TWSE STOCK_DAY_ALL 欄位索引
# 0=代號 1=名稱 2=成交股數 3=成交金額 4=開盤 5=最高 6=最低 7=收盤 8=漲跌 9=筆數

def screen_stocks(rows: list) -> list:
    """
    當沖篩選邏輯：
      1. 四位數純數字代號（排除 ETF、權證）
      2. 股價 20–300 元
      3. 成交股數 ≥ 3,000,000（3,000 張）
      4. 振幅 ≥ 3%
      5. 漲跌幅 > -8%（排除接近跌停）
    評分 = sqrt(量能M) × 振幅 × (動能位置/50)
    """
    candidates = []
    for row in rows:
        try:
            if len(row) < 9:
                continue
            code = row[0].strip()
            name = row[1].strip()

            # 只要主板四碼純數字股票
            if not (code.isdigit() and len(code) == 4):
                continue

            vol     = safe_float(row[2])
            turnover= safe_float(row[3])
            open_p  = safe_float(row[4])
            high_p  = safe_float(row[5])
            low_p   = safe_float(row[6])
            close_p = safe_float(row[7])
            chg_str = row[8].strip() if len(row) > 8 else "0"

            # 基本資料完整性
            if not all([vol, open_p, high_p, low_p, close_p]):
                continue
            if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                continue

            # 條件 1：股價區間
            if not (20 <= open_p <= 300):
                continue

            # 條件 2：量能（張數 = 股數 / 1000）
            if vol < 3_000_000:
                continue

            # 條件 3：振幅
            amplitude = (high_p - low_p) / open_p * 100
            if amplitude < 3.0:
                continue

            # 漲跌與漲跌幅
            change    = safe_float(chg_str) or 0.0
            prev_close = close_p - change
            chg_pct   = (change / prev_close * 100) if prev_close > 0 else 0.0

            # 條件 4：排除近跌停
            if chg_pct < -8.0:
                continue

            # 動能位置（收盤在當日高低區間的百分位）
            day_range = high_p - low_p
            momentum  = (close_p - low_p) / day_range * 100 if day_range > 0 else 50.0

            # 綜合評分
            vol_m = vol / 1_000_000
            score = (vol_m ** 0.5) * amplitude * (momentum / 50)

            candidates.append({
                "code":       code,
                "name":       name,
                "open":       open_p,
                "high":       high_p,
                "low":        low_p,
                "close":      close_p,
                "volume":     int(vol),
                "turnover":   int(turnover) if turnover else 0,
                "amplitude":  round(amplitude, 2),
                "change":     change,
                "change_pct": round(chg_pct, 2),
                "momentum":   round(momentum, 1),
                "score":      score,
            })

        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# ─────────────────────────────────────────
#  停損 / 停利計算
# ─────────────────────────────────────────

def calc_levels(stock: dict) -> dict:
    """
    進場：收盤價（當沖以近收盤進場為基準）
    停損：max(今日低點 × 0.995, 進場 × 0.985)  → 不超過 1.5%
    停利①：以停損距離 1.5R 計算，最低 +2%
    停利②：以停損距離 2.5R 計算，最低 +3.5%
    """
    entry = stock["close"]
    low   = stock["low"]

    # 停損：取今日低點緩衝 vs 固定 1.5%，取較高者（較保守）
    sl_low   = round(low  * 0.995, 2)
    sl_fixed = round(entry * 0.985, 2)
    stop_loss = max(sl_low, sl_fixed)

    risk    = entry - stop_loss
    risk_pct = risk / entry * 100

    # 停利（R 倍數 vs 固定百分比，取較小者避免過於樂觀）
    tp1_r     = round(entry + risk * 1.5, 2)
    tp1_fixed = round(entry * 1.020,      2)
    tp1       = min(tp1_r, tp1_fixed)

    tp2_r     = round(entry + risk * 2.5, 2)
    tp2_fixed = round(entry * 1.035,      2)
    tp2       = max(tp2_r, tp2_fixed)

    rr1 = round((tp1 - entry) / risk, 2) if risk > 0 else 0
    rr2 = round((tp2 - entry) / risk, 2) if risk > 0 else 0

    return {
        "entry":         entry,
        "stop_loss":     stop_loss,
        "take_profit_1": round(tp1, 2),
        "take_profit_2": round(tp2, 2),
        "risk_pct":      round(risk_pct, 2),
        "reward_risk_1": rr1,
        "reward_risk_2": rr2,
    }


def build_reason(stock: dict) -> str:
    """產生推薦理由說明文字"""
    parts = []
    vol_m = stock["volume"] / 1_000_000
    if vol_m >= 20:
        parts.append(f"超大量 {vol_m:.0f}M 股")
    elif vol_m >= 10:
        parts.append(f"大量 {vol_m:.0f}M 股")
    else:
        parts.append(f"量能 {vol_m:.1f}M 股")

    parts.append(f"振幅 {stock['amplitude']:.1f}%")

    if stock["momentum"] >= 75:
        parts.append("強勢收高（近日高）")
    elif stock["momentum"] >= 50:
        parts.append("偏多走勢")
    else:
        parts.append("震盪量大")

    if stock["change_pct"] > 3:
        parts.append(f"漲幅 +{stock['change_pct']:.1f}%")
    elif stock["change_pct"] < -2:
        parts.append(f"注意回調 {stock['change_pct']:.1f}%")

    return "  ｜  ".join(parts)


# ─────────────────────────────────────────
#  Flask 路由
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analysis")
def api_analysis():
    session_type, session_label = market_session()

    raw_rows, data_date = get_all_stocks()
    index_data          = get_market_index()

    result = {
        "status":        session_type,
        "status_label":  session_label,
        "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date":     data_date,
        "market_index":  index_data,
        "recommendations": [],
        "market_stats":  {},
        "error":         None,
    }

    if not raw_rows:
        result["error"] = (
            "無法取得市場數據。可能原因：今日為非交易日、"
            "TWSE API 暫時無回應，或網路連線問題。"
        )
        return jsonify(result)

    # 計算市場統計
    up_count   = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("+"))
    down_count = sum(1 for r in raw_rows if len(r) > 8 and r[8].strip().startswith("-"))
    result["market_stats"] = {
        "total":    len(raw_rows),
        "up":       up_count,
        "down":     down_count,
        "filtered": 0,
    }

    # 篩選候選股
    candidates = screen_stocks(raw_rows)
    result["market_stats"]["filtered"] = len(candidates)

    if not candidates:
        result["error"] = (
            "今日無符合當沖篩選條件的標的"
            "（振幅 ≥3%、成交量 ≥3000張、股價 20–300元）。"
            "若為盤前時段，數據可能尚未更新。"
        )
        return jsonify(result)

    # 組合前 5 推薦
    recs = []
    for stock in candidates[:5]:
        levels    = calc_levels(stock)
        chg_pct   = stock["change_pct"]
        direction = "long" if chg_pct > 0 else ("short" if chg_pct < -2 else "neutral")
        strength  = "strong" if stock["score"] > 60 else ("medium" if stock["score"] > 25 else "weak")
        recs.append({
            **stock,
            **levels,
            "direction": direction,
            "strength":  strength,
            "reason":    build_reason(stock),
        })

    result["recommendations"] = recs
    return jsonify(result)


# ─────────────────────────────────────────
#  啟動
# ─────────────────────────────────────────

@app.route("/health")
def health():
    """Render.com 健康檢查"""
    return "OK", 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print("=" * 55)
    print("  台股當沖分析系統")
    print("  Taiwan Stock Intraday Trading Analyzer")
    print()
    print(f"  伺服器啟動中... port={port}")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=port)
