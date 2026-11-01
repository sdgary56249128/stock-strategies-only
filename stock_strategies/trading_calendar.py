"""台股交易日判斷（本 fork 自訂）

用 FinMind TaiwanStockTradingDate（官方交易日曆，含未來日期）判斷今天是否開盤。
查不到（API 失敗、該年日曆還沒公布）回傳 None，由呼叫端決定照跑。
設 FORCE_RUN=1 可略過判斷（手動測試用）。
"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def taipei_today() -> date:
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def is_trading_day(d: date | None = None) -> bool | None:
    d = d or taipei_today()
    if d.weekday() >= 5:
        return False
    try:
        r = requests.get(
            FINMIND_URL,
            params={
                "dataset": "TaiwanStockTradingDate",
                "start_date": f"{d.year}-01-01",
                "end_date": f"{d.year}-12-31",
            },
            headers={"Authorization": f"Bearer {os.environ.get('FINMIND_TOKEN', '')}"},
            timeout=20,
        )
        dates = {row["date"] for row in r.json().get("data", [])}
    except Exception:
        return None
    if not dates or max(dates) < d.isoformat():
        return None  # calendar for this period not published yet
    return d.isoformat() in dates


def should_skip() -> bool:
    """True = 今天休市、應該跳過。FORCE_RUN=1 時永遠 False。"""
    if os.environ.get("FORCE_RUN") == "1":
        return False
    result = is_trading_day()
    if result is None:
        print("⚠️ 查不到交易日曆，照常執行")
        return False
    return not result
