"""微台指模擬交易通知（本 fork 自訂；紙上交易，不下單）

週一到週五 14:30 收盤選股跑完後由 mac/run.zsh 接著執行；也可手動：uv run python index_trend_report.py
- 抓加權指數（FinMind TAIEX，直接打 API 不經快取），等今天收盤資料出來
- 計算 4 種趨勢策略的部位、停損線、模擬損益 → Telegram
- 每天一列寫進 Google Sheet「IndexPaper」分頁
"""

import os
import sys
import time
from datetime import timedelta

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from stock_strategies.index_trend import STRATEGIES, format_message, snapshot
from stock_strategies.notify import send_telegram
from stock_strategies.trading_calendar import should_skip, taipei_today

SHEET = "IndexPaper"


def taiex() -> pd.Series:
    start = (taipei_today() - timedelta(days=600)).isoformat()
    j = requests.get("https://api.finmindtrade.com/api/v4/data", timeout=60,
                     params={"dataset": "TaiwanStockPrice", "data_id": "TAIEX", "start_date": start},
                     headers={"Authorization": f"Bearer {os.environ['FINMIND_TOKEN']}"}).json()
    df = pd.DataFrame(j.get("data", []))
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    return pd.Series(df["close"].astype(float).values, index=df["date"])


def write_sheet(c: pd.Series, snap: dict):
    import gspread
    from stock_strategies.sheet import get_gsheet
    headers = ["date", "close", "ma20", "ma60", *[f"{n}_部位" for n in STRATEGIES], *[f"{n}_損益" for n in STRATEGIES]]
    row = [c.index[-1].strftime("%Y-%m-%d"), round(c.iloc[-1], 2), round(c.rolling(20).mean().iloc[-1], 2),
           round(c.rolling(60).mean().iloc[-1], 2), *[snap[n]["pos"] for n in STRATEGIES],
           *[round(snap[n]["pnl"]) for n in STRATEGIES]]
    sh = get_gsheet()
    try:
        ws = sh.worksheet(SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET, rows=2000, cols=len(headers))
        ws.append_row(headers)
    dates = ws.col_values(1)
    if row[0] in dates:  # 同一天重跑 → 覆寫
        ws.update(range_name=f"A{dates.index(row[0]) + 1}", values=[row])
    else:
        ws.append_row(row)


def main():
    if should_skip():
        print("📅 今天台股休市，不發微台指模擬")
        return
    today = pd.Timestamp(taipei_today())
    for i in range(7):  # 最多等 30 分鐘
        c = taiex()
        if c.index[-1] >= today:
            break
        print("  → 加權指數今日收盤還沒更新，5 分鐘後再試")
        time.sleep(300)
    else:
        print("⚠️ 等不到今日收盤，用最新資料", file=sys.stderr)
    snap = snapshot(c)
    send_telegram(format_message(c, snap))
    write_sheet(c, snap)
    print("✅ 微台指模擬已發送：" + "、".join(f"{n} {s['pos']:g}" for n, s in snap.items()))


if __name__ == "__main__":
    main()
