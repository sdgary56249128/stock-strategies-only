"""ATR×3 移動停損平行追蹤（本 fork 自訂，research/strategies/atr-trailing-exit.md）

對 Signals 分頁裡每一筆 BUY，假設「隔天開盤買、ATR×3 移動停損出場」，
每天從頭重算一次（無狀態，資料修正也會自動反映），寫到 ATRPerformance 分頁。
不影響選股；跟 Performance 分頁（現行 +10%/-8%）對照用。

規則同 research/backtest_exits.py 的 B：
  初始停損 = 進場價 − 3×ATR(14)（訊號日）
  之後停損 = max(停損, 進場後最高收盤 − 3×當日 ATR)，只上移
  收盤跌破停損 → 隔天開盤賣出；成本 0.585% 計入報酬
"""

import gspread
import pandas as pd

from .indicators import add_indicators
from .sheet import get_gsheet

SHEET = "ATRPerformance"
MULT = 3
COST = 0.00585
HEADERS = ["signal_date", "stock_id", "name", "entry_date", "entry_open", "peak_close", "stop",
           "last_date", "last_close", "status", "exit_date", "exit_price", "ret_pct", "days"]


def track(px: pd.DataFrame, signal_date: str, mult: float = MULT) -> dict | None:
    """px：含 date/open/high/low/close 的日線（date 為字串或 Timestamp）。回傳追蹤狀態；還沒進場回 None。"""
    df = add_indicators(px.copy())
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.reset_index(drop=True)
    sig = df.index[df["d"] == signal_date]
    if not len(sig) or sig[0] + 1 >= len(df):
        return None
    i0 = sig[0] + 1
    entry = float(df.at[i0, "open"])
    stop = entry - mult * float(df.at[sig[0], "atr"])
    peak = entry
    out = {"entry_date": df.at[i0, "d"], "entry_open": round(entry, 2)}
    for j in range(i0, len(df)):
        c = float(df.at[j, "close"])
        if c < stop:
            if j + 1 < len(df):
                px_out = float(df.at[j + 1, "open"])
                return {**out, "peak_close": round(peak, 2), "stop": round(stop, 2),
                        "last_date": df.at[j + 1, "d"], "last_close": round(float(df.at[j + 1, "close"]), 2),
                        "status": "已出場", "exit_date": df.at[j + 1, "d"], "exit_price": round(px_out, 2),
                        "ret_pct": round((px_out / entry - 1 - COST) * 100, 2), "days": j + 2 - i0}
            return {**out, "peak_close": round(peak, 2), "stop": round(stop, 2),
                    "last_date": df.at[j, "d"], "last_close": round(c, 2), "status": "明日開盤出場",
                    "exit_date": "", "exit_price": "",
                    "ret_pct": round((c / entry - 1 - COST) * 100, 2), "days": j + 1 - i0}
        peak = max(peak, c)
        stop = max(stop, peak - mult * float(df.at[j, "atr"]))
    last = df.iloc[-1]
    return {**out, "peak_close": round(peak, 2), "stop": round(stop, 2),
            "last_date": last["d"], "last_close": round(float(last["close"]), 2), "status": "持有中",
            "exit_date": "", "exit_price": "",
            "ret_pct": round((float(last["close"]) / entry - 1 - COST) * 100, 2), "days": len(df) - i0}


def read_atr_performance() -> list[dict]:
    try:
        return get_gsheet().worksheet(SHEET).get_all_records()
    except gspread.WorksheetNotFound:
        return []


def update_atr_performance() -> dict:
    """依 Signals 分頁全部 BUY 重算 ATR×3 追蹤並整張重寫；回傳統計。"""
    from .data import get_price_history

    sh = get_gsheet()
    buys = {}
    for r in sh.worksheet("Signals").get_all_records():
        if str(r.get("action")).upper() == "BUY":
            buys[(str(r["date"]), str(r["stock_id"]))] = r.get("name", "")
    records, px_cache = [], {}
    for (d, sid), name in sorted(buys.items()):
        if sid not in px_cache:
            px_cache[sid] = get_price_history(sid, 2)
        t = track(px_cache[sid], d) if not px_cache[sid].empty else None
        rec = {"signal_date": d, "stock_id": sid, "name": name, "status": "等待進場"}
        records.append({**rec, **(t or {})})
    try:
        ws = sh.worksheet(SHEET)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET, rows=max(2000, len(records) + 500), cols=len(HEADERS))
    ws.update(range_name="A1", values=[HEADERS] + [[r.get(h, "") for h in HEADERS] for r in records])
    return stats(records)


def stats(records: list[dict]) -> dict:
    closed = [float(r["ret_pct"]) for r in records if r.get("status") == "已出場" and r.get("ret_pct") != ""]
    opened = [float(r["ret_pct"]) for r in records if r.get("status") in ("持有中", "明日開盤出場") and r.get("ret_pct") != ""]
    return {
        "total": len(records), "open": len(opened), "closed": len(closed),
        "winrate": round(sum(x > 0 for x in closed) / len(closed) * 100) if closed else None,
        "avg_closed": round(sum(closed) / len(closed), 2) if closed else None,
        "avg_open": round(sum(opened) / len(opened), 2) if opened else None,
    }
