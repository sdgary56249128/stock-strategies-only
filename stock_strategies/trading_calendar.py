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


def price_ready(d: date | None = None, probe: str = "2330") -> bool:
    """FinMind 是否已經有 d 這天的收盤價（用台積電當探針）。"""
    d = d or taipei_today()
    try:
        r = requests.get(
            FINMIND_URL,
            params={"dataset": "TaiwanStockPrice", "data_id": probe,
                    "start_date": d.isoformat(), "end_date": d.isoformat()},
            headers={"Authorization": f"Bearer {os.environ.get('FINMIND_TOKEN', '')}"},
            timeout=20,
        )
        return any(row.get("date") == d.isoformat() for row in r.json().get("data", []))
    except Exception:
        return False


def wait_for_today_prices(max_minutes: int = 180, every_minutes: int = 5) -> bool:
    """等 FinMind 更新今天的收盤價；等到回 True，逾時回 False。"""
    import time
    for i in range(max_minutes // every_minutes + 1):
        if price_ready():
            if i:
                print(f"  → 今日收盤價已更新（等了約 {i * every_minutes} 分鐘）")
            return True
        if i == 0:
            print(f"  → FinMind 還沒有今日收盤價，每 {every_minutes} 分鐘檢查一次，最多等 {max_minutes} 分鐘")
        time.sleep(every_minutes * 60)
    return False


def should_skip() -> bool:
    """True = 今天休市、應該跳過。FORCE_RUN=1 時永遠 False。"""
    if os.environ.get("FORCE_RUN") == "1":
        return False
    result = is_trading_day()
    if result is None:
        print("⚠️ 查不到交易日曆，照常執行")
        return False
    return not result
