"""WATCH 訊號績效追蹤（本 fork 自訂）

原本的 Performance 分頁只追蹤 BUY；大盤偏弱時 BUY 會全部降成 WATCH，
就永遠累積不到數據。這裡用同一套 update_performance 邏輯，
把每天的 WATCH 記到另一個分頁 WatchPerformance，不改變選股結果。
"""

import gspread

from .performance import summary, update_performance
from .sheet import PERFORMANCE_HEADERS, get_gsheet

SHEET = "WatchPerformance"


def read_watch_performance() -> list[dict]:
    try:
        return get_gsheet().worksheet(SHEET).get_all_records()
    except gspread.WorksheetNotFound:
        return []


def write_watch_performance(records: list[dict]):
    sh = get_gsheet()
    try:
        ws = sh.worksheet(SHEET)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET, rows=max(3000, len(records) + 500), cols=len(PERFORMANCE_HEADERS))
    rows = [PERFORMANCE_HEADERS] + [[r.get(h, "") for h in PERFORMANCE_HEADERS] for r in records]
    ws.update(range_name="A1", values=rows)


def update_watch_performance(signals: list[dict]) -> dict:
    """補齊舊 WATCH 的 T+N 表現並加入今日 WATCH；回傳 summary()。"""
    # update_performance only picks up action == "BUY", so relabel today's WATCH
    watches = [dict(s, action="BUY") for s in signals if s.get("action") == "WATCH"]
    records = update_performance(read_watch_performance(), watches)
    write_watch_performance(records)
    return summary(records)
