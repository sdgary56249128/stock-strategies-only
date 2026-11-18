"""大盤趨勢策略改良（微台指波段用；研究用）

uv run --with tabulate python research/improve_index_trend.py

延續 backtest_index_futures.py，比較改良版本，並看每筆交易的波段特性。
防過度最佳化：參數只在 2000～2014 挑，2015～2026 當「沒看過的資料」驗證。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backtest_index_futures import COST, ma_filter, run, stats, yahoo  # noqa: E402


def hysteresis(c, n=60, band=0.01):
    """緩衝帶：站上均線 +band 才做多，跌破均線 −band 才出場（減少來回洗）"""
    ma = c.rolling(n).mean()
    pos, p = [], 0
    for x, m in zip(c, ma):
        if np.isnan(m):
            pos.append(0)
            continue
        if p == 0 and x > m * (1 + band):
            p = 1
        elif p == 1 and x < m * (1 - band):
            p = 0
        pos.append(p)
    return pd.Series(pos, index=c.index)


def confirm(c, n=60, days=2):
    """連續 days 天站上才做多、連續 days 天跌破才出場"""
    above = c > c.rolling(n).mean()
    up = above.rolling(days).sum() == days
    dn = (~above).rolling(days).sum() == days
    pos, p = [], 0
    for u, d in zip(up, dn):
        if p == 0 and u:
            p = 1
        elif p == 1 and d:
            p = 0
        pos.append(p)
    return pd.Series(pos, index=c.index)


def slope(c, n=60, lb=5):
    """站上均線而且均線往上（比 lb 天前高）才做多"""
    ma = c.rolling(n).mean()
    return ((c > ma) & (ma > ma.shift(lb))).astype(int)


def dual(c, fast=20, slow=60, half=True):
    """月線＋季線：兩條都站上 1 口；只站上季線 0.5 口（half=False 則 0）"""
    a = (c > c.rolling(slow).mean()).astype(float)
    b = (c > c.rolling(fast).mean()).astype(float)
    return a * b + (a * (1 - b) * 0.5 if half else 0)


def atr_proxy(c, n=14):
    # 只有收盤價：用收盤價變動的絕對值平均近似 ATR
    return c.diff().abs().rolling(n).mean()


def ma_entry_atr_exit(c, n=60, mult=3.0):
    """收盤站上均線進場；ATR×mult 移動停損或跌破均線出場（先到者）"""
    ma, atr = c.rolling(n).mean(), atr_proxy(c)
    pos, p, stop, peak = [], 0, 0.0, 0.0
    for x, m, a in zip(c, ma, atr):
        if np.isnan(m) or np.isnan(a):
            pos.append(0)
            continue
        if p == 1:
            peak = max(peak, x)
            stop = max(stop, peak - mult * a)
            if x < stop or x < m:
                p = 0
        elif x < m:                 # 跌回均線下 → 重設，等下一次站上
            stop = 0.0
        elif x > m and x > stop:    # 停損出場後（仍在均線上），要等重新站上停損價才再進場
            p, peak, stop = 1, x, x - mult * a
        pos.append(p)
    return pd.Series(pos, index=c.index)


def swing_ma(c, fast=10, slow=20):
    """短波段：10 日線 > 20 日線做多"""
    return (c.rolling(fast).mean() > c.rolling(slow).mean()).astype(int)


def trades(pos: pd.Series, c: pd.Series) -> pd.DataFrame:
    """把部位序列切成一筆一筆交易（只看做多 ≥0.5 口）"""
    rows, start = [], None
    p = (pos > 0).astype(int)
    for i in range(1, len(p)):
        if p.iloc[i] == 1 and p.iloc[i - 1] == 0:
            start = i
        elif p.iloc[i] == 0 and p.iloc[i - 1] == 1 and start is not None:
            rows.append((c.index[start], c.index[i], i - start, c.iloc[i] / c.iloc[start] - 1 - 2 * COST))
            start = None
    return pd.DataFrame(rows, columns=["進場", "出場", "天數", "報酬"])


def trade_stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return {}
    w, l = t[t["報酬"] > 0], t[t["報酬"] <= 0]
    return {"交易數": len(t), "勝率": f"{len(w) / len(t):.0%}", "平均持有": f"{t['天數'].mean():.0f} 天",
            "平均賺": f"{w['報酬'].mean():+.1%}" if len(w) else "—",
            "平均賠": f"{l['報酬'].mean():+.1%}" if len(l) else "—",
            "最大單筆虧": f"{t['報酬'].min():+.1%}", "最大單筆賺": f"{t['報酬'].max():+.1%}"}


def main():
    c = yahoo("^TWII")
    S = {
        "基準：站上季線做多": ma_filter(c, 60),
        "緩衝帶 季線±1%": hysteresis(c, 60, 0.01),
        "緩衝帶 季線±2%": hysteresis(c, 60, 0.02),
        "連 2 天確認 季線": confirm(c, 60, 2),
        "連 3 天確認 季線": confirm(c, 60, 3),
        "季線往上才做多": slope(c, 60, 5),
        "月線＋季線（半口）": dual(c, 20, 60, True),
        "月線＋季線（都站上才做）": dual(c, 20, 60, False),
        "季線進場＋ATR×3 停損": ma_entry_atr_exit(c, 60, 3),
        "季線進場＋ATR×4 停損": ma_entry_atr_exit(c, 60, 4),
        "短波段 10/20 日線": swing_ma(c, 10, 20),
        "短波段 月線緩衝 ±1%": hysteresis(c, 20, 0.01),
    }
    R = {k: run(c, p) for k, p in S.items()}
    print("# 大盤趨勢策略改良（微台指波段）\n")
    for title, a, b in [("訓練期 2000～2014（挑參數用）", "2000-01-01", "2014-12-31"),
                        ("驗證期 2015～2026（沒看過的資料）", "2015-01-01", "2030-01-01")]:
        rows = []
        for k in S:
            m = (R[k].index >= a) & (R[k].index <= b)
            rows.append({"策略": k, **stats(R[k][m], S[k][m])})
        print(f"## {title}\n")
        print(pd.DataFrame(rows).to_markdown(index=False))
        print()

    print("## 每筆交易（全期，只算做多波段）\n")
    print(pd.DataFrame([{"策略": k, **trade_stats(trades(S[k], c))} for k in S]).to_markdown(index=False))
    print()

    print("## 均線天數敏感度（只做多，夏普值）：數字平穩代表不是湊出來的\n")
    rows = []
    for n in [20, 40, 60, 80, 100, 120, 160, 200]:
        p = ma_filter(c, n)
        d = run(c, p)
        a = d[d.index < "2015-01-01"]
        b = d[d.index >= "2015-01-01"]
        rows.append({"均線": n, "訓練期夏普": f"{a.mean() / a.std() * np.sqrt(245):.2f}",
                     "驗證期夏普": f"{b.mean() / b.std() * np.sqrt(245):.2f}",
                     "驗證期最大回撤": stats(b, p[p.index >= '2015-01-01'])["最大回撤"]})
    print(pd.DataFrame(rows).to_markdown(index=False))
    print()
    print(f"## 目前部位（{c.index[-1]:%Y-%m-%d}）\n")
    print(pd.DataFrame([{"策略": k, "部位": f"{float(S[k].iloc[-1]):g} 口"} for k in S]).to_markdown(index=False))


if __name__ == "__main__":
    main()
