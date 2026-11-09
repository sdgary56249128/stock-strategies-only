"""籌碼資訊顯示（本 fork 自訂，第一階段只顯示、不影響分數）

- 個股三大法人買賣超：外資/投信/自營 最新一日（張）、外資連買/連賣天數、5 日合計
- 外資台指期淨未平倉口數（TX）與前一日變化

資料直接打 FinMind（不經快取，避免 Mac 上的舊快取）。失敗一律回 None，不擋主流程。
"""

import os
from datetime import timedelta

import requests

from .trading_calendar import taipei_today

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _get(dataset: str, data_id: str, days: int) -> list[dict]:
    start = (taipei_today() - timedelta(days=days)).isoformat()
    r = requests.get(
        FINMIND_URL,
        params={"dataset": dataset, "data_id": data_id, "start_date": start},
        headers={"Authorization": f"Bearer {os.environ.get('FINMIND_TOKEN', '')}"},
        timeout=20,
    )
    return r.json().get("data", []) or []


def summarize_stock_chips(rows: list[dict]) -> dict | None:
    """rows = TaiwanStockInstitutionalInvestorsBuySell 原始列 → 依日彙總（張）"""
    days: dict[str, dict] = {}
    for row in rows:
        n = str(row.get("name", ""))
        key = ("foreign" if n.startswith("Foreign") else "trust" if n.startswith("Investment_Trust")
               else "dealer" if n.startswith("Dealer") else None)
        if not key:
            continue
        d = days.setdefault(row["date"], {"foreign": 0.0, "trust": 0.0, "dealer": 0.0})
        d[key] += (float(row.get("buy") or 0) - float(row.get("sell") or 0)) / 1000
    if not days:
        return None
    dates = sorted(days)
    last = days[dates[-1]]
    streak = 0
    sign = 1 if last["foreign"] > 0 else -1 if last["foreign"] < 0 else 0
    if sign:
        for d in reversed(dates):
            if (days[d]["foreign"] > 0 and sign > 0) or (days[d]["foreign"] < 0 and sign < 0):
                streak += 1
            else:
                break
    total5 = sum(sum(days[d].values()) for d in dates[-5:])
    return {"date": dates[-1], **{k: round(v) for k, v in last.items()},
            "foreign_streak": streak * sign, "total_5d": round(total5)}


def stock_chips(stock_id: str) -> dict | None:
    try:
        return summarize_stock_chips(_get("TaiwanStockInstitutionalInvestorsBuySell", stock_id, 20))
    except Exception:
        return None


def chips_line(c: dict | None) -> str | None:
    if not c:
        return None
    st = c["foreign_streak"]
    streak = f"外資連買 {st} 天" if st > 0 else f"外資連賣 {-st} 天" if st < 0 else "外資持平"
    label = "法人" if c["date"] == taipei_today().isoformat() else f"前一日法人（{c['date'][5:].replace('-', '/')}）"
    return (f"🏦 {label}: 外資 {c['foreign']:+,} 投信 {c['trust']:+,} 自營 {c['dealer']:+,} 張"
            f"｜{streak}｜5日合計 {c['total_5d']:+,}")


def summarize_futures_oi(rows: list[dict]) -> dict | None:
    """rows = TaiwanFuturesInstitutionalInvestors(TX) 原始列 → 外資淨未平倉"""
    fx = sorted((r for r in rows if r.get("institutional_investors") == "外資"), key=lambda r: r["date"])
    if not fx:
        return None
    net = [(r["date"], int(r["long_open_interest_balance_volume"]) - int(r["short_open_interest_balance_volume"]))
           for r in fx]
    date, cur = net[-1]
    chg = cur - net[-2][1] if len(net) >= 2 else None
    return {"date": date, "net": cur, "chg": chg}


def futures_oi() -> dict | None:
    try:
        return summarize_futures_oi(_get("TaiwanFuturesInstitutionalInvestors", "TX", 14))
    except Exception:
        return None


def futures_line(f: dict | None) -> str | None:
    if not f:
        return None
    side = "淨多" if f["net"] > 0 else "淨空"
    chg = ""
    if f["chg"] is not None:
        chg = f"，較前日{'加多' if f['chg'] > 0 else '加空'} {abs(f['chg']):,} 口" if f["chg"] else "，與前日持平"
    return f"🌐 外資台指期{side} {abs(f['net']):,} 口{chg}（{f['date'][5:].replace('-', '/')}）"


def add_premarket_chips(text: str, fetch=stock_chips, fut=None) -> str:
    """在盤前快報加外資期貨一行，並在每檔昨日 BUY/WATCH 下面加法人一行。"""
    fut = futures_line(futures_oi()) if fut is None else fut
    if fut:
        text = text.replace("\n\n📋", f"\n{fut}\n\n📋", 1)
    out = []
    for line in text.split("\n"):
        out.append(line)
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("🟢", "🟡") and parts[1] in ("BUY", "WATCH"):
            cl = chips_line(fetch(parts[2]))
            if cl:
                out.append("    " + cl.replace("前一日法人", "法人"))
    return "\n".join(out)
