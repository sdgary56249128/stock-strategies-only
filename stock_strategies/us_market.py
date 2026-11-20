"""昨晚美股摘要（本 fork 自訂，放在 08:00 盤前快報，只顯示、不影響分數）

資料：FinMind USStockPrice 為主，Yahoo Finance chart API 備援，取兩者中日期較新的。
台積電 ADR 溢價 = TSM 收盤 × 美元匯率 ÷ 5（1 ADR = 5 股）÷ 2330 收盤 − 1
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from .trading_calendar import taipei_today

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"

INDICES = [("^SOX", "費半"), ("^IXIC", "那斯達克"), ("^GSPC", "標普")]
STOCKS = ["NVDA", "AMD", "AVGO", "MU", "AAPL", "TSLA", "SPCX"]


def _finmind(symbol: str) -> list[tuple[str, float]]:
    start = (taipei_today() - timedelta(days=10)).isoformat()
    r = requests.get(
        FINMIND_URL,
        params={"dataset": "USStockPrice", "data_id": symbol, "start_date": start},
        headers={"Authorization": f"Bearer {os.environ.get('FINMIND_TOKEN', '')}"},
        timeout=20,
    )
    return [(row["date"], float(row["Close"])) for row in r.json().get("data", []) if row.get("Close")]


def _yahoo(symbol: str) -> list[tuple[str, float]]:
    j = requests.get(YAHOO_URL.format(symbol), params={"range": "10d", "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()
    res = j["chart"]["result"][0]
    tz = res.get("meta", {}).get("gmtoffset", 0)
    closes = res["indicators"]["quote"][0]["close"]
    return [(datetime.fromtimestamp(t + tz, timezone.utc).strftime("%Y-%m-%d"), float(c))
            for t, c in zip(res["timestamp"], closes) if c is not None]


def quote(symbol: str) -> dict | None:
    """回傳最新一日 {date, close, pct}；兩個來源都失敗回 None。"""
    best = []
    for src in (_finmind, _yahoo):
        try:
            rows = sorted(src(symbol))
        except Exception:
            continue
        if len(rows) >= 2 and (not best or rows[-1][0] > best[-1][0]):
            best = rows
    if len(best) < 2:
        return None
    (d, c), (_, prev) = best[-1], best[-2]
    return {"date": d, "close": c, "pct": (c / prev - 1) * 100}


def _usd_twd() -> float | None:
    try:
        rows = _yahoo("TWD=X")
        return rows[-1][1] if rows else None
    except Exception:
        return None


def _tw_close(stock_id: str = "2330") -> float | None:
    try:
        rows = _yahoo(f"{stock_id}.TW")
        return rows[-1][1] if rows else None
    except Exception:
        return None


def adr_premium(tsm_close: float, usd_twd: float, tw_close: float) -> float:
    return (tsm_close * usd_twd / 5 / tw_close - 1) * 100


def format_us_block(idx: list[tuple[str, dict | None]], tsm: dict | None, premium: float | None,
                    stocks: list[tuple[str, dict | None]]) -> str | None:
    if not any(q for _, q in idx + stocks) and not tsm:
        return None
    dates = [q["date"] for _, q in idx + stocks if q] + ([tsm["date"]] if tsm else [])
    d = max(dates)
    lines = [f"🇺🇸 *昨晚美股*（{d[5:].replace('-', '/')} 收盤）"]
    parts = [f"{name} {q['pct']:+.1f}%" for name, q in idx if q]
    if parts:
        lines.append("｜".join(parts))
    if tsm:
        prem = f"（ADR 溢價 {premium:+.1f}%）" if premium is not None else ""
        lines.append(f"台積電 ADR {tsm['pct']:+.1f}%{prem}")
    parts = [f"{sym} {q['pct']:+.1f}%" for sym, q in stocks if q]
    if parts:
        lines.append("｜".join(parts))
    return "\n".join(lines)


def us_block() -> str | None:
    try:
        idx = [(name, quote(sym)) for sym, name in INDICES]
        tsm = quote("TSM")
        premium = None
        if tsm:
            fx, tw = _usd_twd(), _tw_close()
            if fx and tw:
                premium = adr_premium(tsm["close"], fx, tw)
        stocks = [(sym, quote(sym)) for sym in STOCKS]
        return format_us_block(idx, tsm, premium, stocks)
    except Exception:
        return None
