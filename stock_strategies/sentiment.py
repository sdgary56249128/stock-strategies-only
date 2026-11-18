"""市場情緒摘要（本 fork 自訂，放在 08:00 盤前快報，只顯示、不影響分數）

- VIX／VXN：Yahoo Finance
- 台指選擇權 P/C ratio（未平倉，一般交易時段）：FinMind TaiwanOptionDaily（TXO）
  台股解讀與美股相反：賣權賣方多為法人，P/C 高 → 大戶認為跌不深 → 偏多；以 1.0 為分界
- 大盤融資餘額：FinMind TaiwanStockTotalMarginPurchaseShortSale（MarginPurchaseMoney）
- 三大法人合計買賣超：FinMind TaiwanStockTotalInstitutionalInvestors（total）
"""

import os
from datetime import timedelta

import pandas as pd
import requests

from .trading_calendar import taipei_today
from .us_market import _yahoo

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _fm(dataset: str, days: int, data_id: str = "") -> pd.DataFrame:
    params = {"dataset": dataset, "start_date": (taipei_today() - timedelta(days=days)).isoformat()}
    if data_id:
        params["data_id"] = data_id
    r = requests.get(FINMIND_URL, params=params, timeout=60,
                     headers={"Authorization": f"Bearer {os.environ.get('FINMIND_TOKEN', '')}"})
    return pd.DataFrame(r.json().get("data", []) or [])


def vix_level(v: float) -> str:
    return "樂觀" if v < 15 else "正常" if v < 20 else "緊張" if v < 30 else "恐慌"


def vix_part(symbol: str, label: str) -> str | None:
    try:
        rows = sorted(_yahoo(symbol))
    except Exception:
        return None
    if len(rows) < 2:
        return None
    v, prev = rows[-1][1], rows[-2][1]
    arrow = "↑" if v > prev else "↓" if v < prev else "→"
    return f"{label} {v:.1f}（{arrow}{abs(v - prev):.1f}，{vix_level(v)}）"


def pc_ratio_series(df: pd.DataFrame) -> pd.Series:
    """TaiwanOptionDaily 原始列 → 各日 P/C ratio（未平倉，一般交易時段）"""
    if df.empty:
        return pd.Series(dtype=float)
    df = df[df.get("trading_session", "position") == "position"]
    g = df.groupby(["date", "call_put"])["open_interest"].sum().unstack()
    if "put" not in g or "call" not in g:
        return pd.Series(dtype=float)
    return (g["put"] / g["call"]).dropna().sort_index()


def pc_part() -> str | None:
    try:
        s = pc_ratio_series(_fm("TaiwanOptionDaily", 7, "TXO"))
    except Exception:
        return None
    if s.empty:
        return None
    v = float(s.iloc[-1])
    arrow = ""
    if len(s) >= 2:
        v, p = round(v, 2), round(float(s.iloc[-2]), 2)
        arrow = "↑" if v > p else "↓" if v < p else "→"
    view = "大戶偏多" if v >= 1.2 else "中性偏多" if v >= 1.0 else "中性偏空" if v >= 0.8 else "大戶偏空"
    return f"台指 P/C ratio {v:.2f}（{arrow}{view}）"


def margin_part() -> str | None:
    try:
        df = _fm("TaiwanStockTotalMarginPurchaseShortSale", 7)
        df = df[df["name"] == "MarginPurchaseMoney"].sort_values("date")
        last = df.iloc[-1]
    except Exception:
        return None
    bal = float(last["TodayBalance"]) / 1e8
    chg = (float(last["TodayBalance"]) - float(last["YesBalance"])) / 1e8
    return f"融資餘額 {bal:,.0f} 億（{chg:+,.0f} 億）"


def inst_part() -> str | None:
    try:
        df = _fm("TaiwanStockTotalInstitutionalInvestors", 7)
        df = df[df["name"] == "total"].sort_values("date")
        last = df.iloc[-1]
    except Exception:
        return None
    net = (float(last["buy"]) - float(last["sell"])) / 1e8
    return f"法人合計 {net:+,.0f} 億"


def sentiment_block() -> str | None:
    lines = []
    v = [p for p in (vix_part("^VIX", "VIX"), vix_part("^VXN", "VXN")) if p]
    if v:
        lines.append("｜".join(v))
    if (pc := pc_part()):
        lines.append(pc)
    m = [p for p in (margin_part(), inst_part()) if p]
    if m:
        lines.append("｜".join(m))
    if not lines:
        return None
    return "\n".join(["🌡️ *市場情緒*", *lines])
