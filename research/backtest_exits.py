"""出場方式回測：進場固定，比較不同出場規則（research/strategies/atr-trailing-exit.md）

uv run python research/backtest_exits.py

進場（近似現行系統的 BUY，見報告「限制」）：
  - 原作者 tech_score_at ≥ 60（= 原作者回測用的訊號門檻）
  - 大盤濾鏡：加權指數收盤 ≥ 20 日均線
  - 訊號日收盤產生，隔天開盤進場；同一檔持有中不重複進場
出場（全部用收盤判斷、隔天開盤出場；固定停利停損則盤中觸價成交）：
  A 現行：+10% 停利／-8% 停損，最多 20 天
  B ATR×3 移動停損   C ATR×2 移動停損
  D 跌破 20MA 連 3 天（XQ 版，無停損）   E D＋固定停損 -10%
成本：手續費 0.1425%×2＋交易稅 0.3% = 0.585%（一買一賣）
資料：FinMind 未還原股價；單日漲跌超過 ±11%（漲跌停外，多為除權息/減資）的交易剔除
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from stock_strategies.indicators import add_indicators, tech_score_at  # noqa: E402

DATA = ROOT / "data"
COST = 0.00585
MAX_HOLD = 250  # 移動停損類最長持有約一年

STRESS = {
    "2018/10 貿易戰": ("2018-10-01", "2018-10-31"),
    "2020/03 疫情崩跌": ("2020-02-20", "2020-03-31"),
    "2022 升息空頭": ("2022-01-01", "2022-10-31"),
    "2024/07-08 AI 修正": ("2024-07-12", "2024-08-09"),
    "2025/04 關稅衝擊": ("2025-03-26", "2025-04-30"),
}


def load_price(sid: str) -> pd.DataFrame:
    f = DATA / "TaiwanStockPrice" / f"{sid}.parquet"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_parquet(f)
    if df.empty:
        return df
    df = df.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[(df["close"] > 0) & (df["open"] > 0)]
    return df.sort_values("date").reset_index(drop=True)


def market_ok() -> pd.Series:
    ix = load_price("TAIEX")
    ix["ma20"] = ix["close"].rolling(20).mean()
    return pd.Series((ix["close"] >= ix["ma20"]).values, index=ix["date"])


# ---------- 出場規則：回傳 (出場 index, 出場價) ----------

def exit_fixed(df, i0, entry, target=0.10, stop=0.08, hold=20):
    for j in range(i0, min(i0 + hold, len(df))):
        lo, hi = df.at[j, "low"], df.at[j, "high"]
        if lo <= entry * (1 - stop):
            return j, min(df.at[j, "open"], entry * (1 - stop))
        if hi >= entry * (1 + target):
            return j, max(df.at[j, "open"], entry * (1 + target))
    j = min(i0 + hold - 1, len(df) - 1)
    return j, df.at[j, "close"]


def exit_atr(df, i0, entry, mult):
    atr0 = df.at[i0 - 1, "atr"]
    stop = entry - mult * atr0
    peak = entry
    for j in range(i0, min(i0 + MAX_HOLD, len(df) - 1)):
        c = df.at[j, "close"]
        if c < stop:
            return j + 1, df.at[j + 1, "open"]
        peak = max(peak, c)
        stop = max(stop, peak - mult * df.at[j, "atr"])
    j = min(i0 + MAX_HOLD, len(df) - 1)
    return j, df.at[j, "close"]


def exit_ma20(df, i0, entry, hard_stop=None):
    below = 0
    for j in range(i0, min(i0 + MAX_HOLD, len(df) - 1)):
        if hard_stop and df.at[j, "low"] <= entry * (1 - hard_stop):
            return j, min(df.at[j, "open"], entry * (1 - hard_stop))
        below = below + 1 if df.at[j, "close"] < df.at[j, "ma20"] else 0
        if below >= 3:
            return j + 1, df.at[j + 1, "open"]
    j = min(i0 + MAX_HOLD, len(df) - 1)
    return j, df.at[j, "close"]


RULES = {
    "A 現行 +10%/-8%/20天": lambda df, i, e: exit_fixed(df, i, e),
    "B ATR×3 移動停損": lambda df, i, e: exit_atr(df, i, e, 3),
    "C ATR×2 移動停損": lambda df, i, e: exit_atr(df, i, e, 2),
    "D 跌破20MA連3天": lambda df, i, e: exit_ma20(df, i, e),
    "E D＋停損-10%": lambda df, i, e: exit_ma20(df, i, e, 0.10),
}


def run_stock(sid: str, mkt: pd.Series) -> list[dict]:
    df = load_price(sid)
    if len(df) < 120:
        return []
    df = add_indicators(df)
    jump = (df["close"] / df["close"].shift() - 1).abs() > 0.11
    sig = np.zeros(len(df), dtype=bool)
    for i in range(60, len(df) - 2):
        if mkt.get(df.at[i, "date"], False) and tech_score_at(df.iloc[i])["score"] >= 60:
            sig[i] = True
    trades = []
    for rule, fn in RULES.items():
        i = 60
        while i < len(df) - 2:
            if not sig[i]:
                i += 1
                continue
            e_idx = i + 1
            entry = df.at[e_idx, "open"]
            x_idx, x_px = fn(df, e_idx, entry)
            x_idx = max(x_idx, e_idx)
            if not jump.iloc[e_idx:x_idx + 1].any():
                trades.append({"rule": rule, "stock_id": sid, "entry_date": df.at[e_idx, "date"],
                               "exit_date": df.at[x_idx, "date"], "days": x_idx - e_idx + 1,
                               "ret": x_px / entry - 1 - COST})
            i = x_idx + 1  # 出場後才可能再進場
    return trades


def summarize(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rule, g in t.groupby("rule", sort=False):
        r = g["ret"]
        wins, losses = r[r > 0], r[r <= 0]
        rows.append({
            "出場規則": rule, "交易數": len(g), "勝率": f"{(r > 0).mean():.0%}",
            "平均報酬": f"{r.mean():+.2%}", "中位數": f"{r.median():+.2%}",
            "平均賺": f"{wins.mean():+.1%}", "平均賠": f"{losses.mean():+.1%}",
            "獲利因子": f"{wins.sum() / -losses.sum():.2f}" if len(losses) else "—",
            "最大單筆虧損": f"{r.min():+.1%}", "最大單筆獲利": f"{r.max():+.1%}",
            "平均持有天數": f"{g['days'].mean():.0f}",
            "去掉最好1%平均": f"{r[r <= r.quantile(0.99)].mean():+.2%}",
            "每持有日報酬": f"{r.mean() / g['days'].mean():+.3%}",
        })
    return pd.DataFrame(rows)


def by_year(t: pd.DataFrame) -> pd.DataFrame:
    t = t.assign(year=pd.to_datetime(t["entry_date"]).dt.year)
    return t.pivot_table(index="year", columns="rule", values="ret", aggfunc="mean", sort=False) \
            .map(lambda x: f"{x:+.1%}")


def stress(t: pd.DataFrame) -> pd.DataFrame:
    """事件期間內『持有中』的交易：平均報酬與最差一筆"""
    rows = []
    for name, (a, b) in STRESS.items():
        g = t[(t["entry_date"] <= b) & (t["exit_date"] >= a)]
        row = {"事件": name}
        for rule, gg in g.groupby("rule", sort=False):
            row[rule] = f"{gg['ret'].mean():+.1%}（最差 {gg['ret'].min():+.0%}，{len(gg)} 筆）"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    sys.path.insert(0, str(ROOT))
    ids = sorted(p.stem for p in (DATA / "TaiwanStockPrice").glob("*.parquet") if p.stem != "TAIEX")
    mkt = market_ok()
    trades = []
    for k, sid in enumerate(ids, 1):
        trades += run_stock(sid, mkt)
        if k % 25 == 0:
            print(f"{k}/{len(ids)}", flush=True)
    t = pd.DataFrame(trades)
    t.to_parquet(DATA / "trades_exits.parquet")
    print(f"\n股票 {len(ids)} 檔，期間 {t['entry_date'].min()} ～ {t['exit_date'].max()}\n")
    for title, df in [("總表", summarize(t)), ("逐年平均報酬（依進場年）", by_year(t)), ("壓力測試", stress(t))]:
        print(f"## {title}\n")
        print(df.to_markdown(index=title == "逐年平均報酬（依進場年）"))
        print()


if __name__ == "__main__":
    main()
