"""大盤趨勢策略回測（給微台指用；研究用，不影響每天選股）

uv run --with tabulate python research/backtest_index_futures.py

假設：
- 用加權指數（Yahoo ^TWII，2000 年起）近似台指期／微台指的每日漲跌
- 每天收盤（13:30 現貨收盤後、13:45 期貨收盤前）判斷訊號，用收盤價調整部位；持有到隔天收盤
- 部位：+1 做多、0 空手、-1 做空（1 口，不加碼）
- 成本：每次部位變動 0.03%（微台指手續費＋期交稅＋滑價 1 點的保守估計；多翻空算 2 次）
- 未計：轉倉價差、保證金利息、夜盤；加權指數是價格指數，期貨會反映除息（夏季逆價差），兩者大致抵銷
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
MKT = ROOT / "data" / "market"
COST = 0.0003

STRESS = {
    "2000-01 網路泡沫": ("2000-02-18", "2001-09-26"),
    "2008 金融海嘯": ("2008-05-20", "2008-11-21"),
    "2015 股災": ("2015-04-28", "2015-08-24"),
    "2018/10 貿易戰": ("2018-10-01", "2018-10-31"),
    "2020/03 疫情": ("2020-02-20", "2020-03-19"),
    "2022 升息空頭": ("2022-01-05", "2022-10-25"),
    "2024/07 AI 修正": ("2024-07-11", "2024-08-05"),
    "2025/04 關稅": ("2025-03-26", "2025-04-09"),
    "2026/11 這次": ("2026-11-11", "2026-11-17"),
}


def yahoo(sym: str) -> pd.Series:
    f = MKT / f"long_{sym.strip('^')}.parquet"
    if not f.exists() or time.time() - f.stat().st_mtime > 6 * 3600:
        j = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                         params={"period1": 946684800, "period2": int(time.time()), "interval": "1d"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=60).json()
        r = j["chart"]["result"][0]
        tz = r["meta"].get("gmtoffset", 0)
        df = pd.DataFrame({"date": [datetime.fromtimestamp(t + tz, timezone.utc).strftime("%Y-%m-%d")
                                    for t in r["timestamp"]],
                           "close": r["indicators"]["quote"][0]["close"]}).dropna()
        MKT.mkdir(parents=True, exist_ok=True)
        df.to_parquet(f)
    df = pd.read_parquet(f).drop_duplicates("date", keep="last")
    return pd.Series(df["close"].values, index=pd.to_datetime(df["date"])).sort_index()


# ---------- 策略：回傳每天收盤後的目標部位（-1/0/+1）----------

def ma_filter(c, n, short=False):
    up = c > c.rolling(n).mean()
    return up.astype(int) - ((~up).astype(int) if short else 0)


def ma_cross(c, fast, slow, short=False):
    up = c.rolling(fast).mean() > c.rolling(slow).mean()
    return up.astype(int) - ((~up).astype(int) if short else 0)


def donchian(c, entry=55, exit_=20, short=False):
    hi_e, lo_e = c.rolling(entry).max().shift(1), c.rolling(entry).min().shift(1)
    hi_x, lo_x = c.rolling(exit_).max().shift(1), c.rolling(exit_).min().shift(1)
    pos, p = [], 0
    for i in range(len(c)):
        x = c.iloc[i]
        if p == 1 and x < lo_x.iloc[i]:
            p = 0
        elif p == -1 and x > hi_x.iloc[i]:
            p = 0
        if p == 0:
            if x > hi_e.iloc[i]:
                p = 1
            elif short and x < lo_e.iloc[i]:
                p = -1
        pos.append(p)
    return pd.Series(pos, index=c.index)


def vix_overlay(pos, vix, level=30):
    v = vix.reindex(pos.index).ffill()
    return pos.where(~(v > level), 0)


def run(c: pd.Series, pos: pd.Series) -> pd.Series:
    r = c.pct_change().fillna(0)
    held = pos.shift(1).fillna(0)                 # 昨天收盤決定的部位，賺今天的漲跌
    trade = pos.diff().abs().fillna(pos.abs())    # 今天收盤調整部位的成本
    return held * r - trade * COST


def stats(daily: pd.Series, pos: pd.Series) -> dict:
    eq = (1 + daily).cumprod()
    yrs = len(daily) / 245
    mdd = (eq / eq.cummax() - 1).min()
    sharpe = daily.mean() / daily.std() * np.sqrt(245) if daily.std() > 0 else 0
    return {"年化報酬": f"{eq.iloc[-1] ** (1 / yrs) - 1:+.1%}", "最大回撤": f"{mdd:.1%}",
            "夏普值": f"{sharpe:.2f}", "持倉時間": f"{(pos != 0).mean():.0%}",
            "做空時間": f"{(pos < 0).mean():.0%}",
            "每年換手": f"{pos.diff().abs().sum() / yrs:.0f} 次",
            "總報酬": f"{eq.iloc[-1] - 1:+.0%}"}


def main():
    c = yahoo("^TWII")
    vix = yahoo("^VIX")
    vix.index = vix.index + pd.Timedelta(days=1)  # 美股 t 日 → 台股 t+1 日才知道
    vix = vix.reindex(c.index, method="ffill")

    strategies = {
        "買進持有（一直做多）": pd.Series(1, index=c.index),
        "站上月線做多 MA20": ma_filter(c, 20),
        "站上季線做多 MA60": ma_filter(c, 60),
        "站上半年線做多 MA120": ma_filter(c, 120),
        "站上年線做多 MA200": ma_filter(c, 200),
        "季線多空 MA60": ma_filter(c, 60, True),
        "半年線多空 MA120": ma_filter(c, 120, True),
        "年線多空 MA200": ma_filter(c, 200, True),
        "均線交叉 20/60 做多": ma_cross(c, 20, 60),
        "均線交叉 20/60 多空": ma_cross(c, 20, 60, True),
        "通道突破 55/20 做多": donchian(c),
        "通道突破 55/20 多空": donchian(c, short=True),
    }
    strategies["季線做多＋VIX>30 空手"] = vix_overlay(strategies["站上季線做多 MA60"], vix)
    strategies["半年線做多＋VIX>30 空手"] = vix_overlay(strategies["站上半年線做多 MA120"], vix)

    results = {k: run(c, p) for k, p in strategies.items()}
    print(f"# 大盤趨勢策略回測（微台指用，{datetime.now():%Y-%m-%d}）\n")
    print(f"加權指數 {c.index.min():%Y-%m-%d} ～ {c.index.max():%Y-%m-%d}，成本每次換倉 {COST:.2%}\n")
    for title, start in [("2000～2026 全期", "2000-01-01"), ("2015～2026 近 10 年", "2015-01-01")]:
        rows = []
        for k, d in results.items():
            m = d.index >= start
            rows.append({"策略": k, **stats(d[m], strategies[k][m])})
        print(f"## {title}\n")
        print(pd.DataFrame(rows).to_markdown(index=False))
        print()

    pick = ["買進持有（一直做多）", "站上季線做多 MA60", "半年線多空 MA120", "通道突破 55/20 多空",
            "季線做多＋VIX>30 空手"]
    yearly = pd.DataFrame({k: (1 + results[k]).groupby(results[k].index.year).prod() - 1 for k in pick})
    print("## 逐年報酬\n")
    print(yearly.map(lambda x: f"{x:+.0%}").to_markdown())
    print()
    rows = []
    for name, (a, b) in STRESS.items():
        row = {"事件": name}
        for k in pick:
            d = results[k][(results[k].index >= a) & (results[k].index <= b)]
            row[k] = f"{(1 + d).prod() - 1:+.0%}"
        rows.append(row)
    print("## 壓力測試（事件期間報酬）\n")
    print(pd.DataFrame(rows).to_markdown(index=False))
    print()
    last = {k: int(strategies[k].iloc[-1]) for k in pick}
    print(f"## 目前（{c.index[-1]:%Y-%m-%d} 收盤）各策略部位\n")
    print(pd.DataFrame([{"策略": k, "部位": {1: "做多", 0: "空手", -1: "做空"}[v]} for k, v in last.items()])
          .to_markdown(index=False))


if __name__ == "__main__":
    main()
