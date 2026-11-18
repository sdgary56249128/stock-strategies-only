"""微台指大盤趨勢策略：每日部位與模擬損益（本 fork 自訂，紙上交易，不下單）

邏輯與 research/improve_index_trend.py 相同；研究結果見 research/strategies/index-trend-futures.md
每天收盤判斷，部位以收盤價成交；損益以微台指 1 點 = 10 元、1 口計算。
"""

import numpy as np
import pandas as pd

POINT_VALUE = 10        # 微台指 1 點 10 元
COST_RATE = 0.0003      # 每次換倉成本（名目價值 0.03%）
PAPER_START = "2026-11-19"


def ma_filter(c: pd.Series, n: int = 60) -> pd.Series:
    return (c > c.rolling(n).mean()).astype(float)


def dual_half(c: pd.Series, fast: int = 20, slow: int = 60) -> pd.Series:
    a = (c > c.rolling(slow).mean()).astype(float)
    b = (c > c.rolling(fast).mean()).astype(float)
    return a * b + a * (1 - b) * 0.5


def hysteresis(c: pd.Series, n: int = 60, band: float = 0.02) -> pd.Series:
    ma = c.rolling(n).mean()
    pos, p = [], 0.0
    for x, m in zip(c, ma):
        if not np.isnan(m):
            if p == 0 and x > m * (1 + band):
                p = 1.0
            elif p == 1 and x < m * (1 - band):
                p = 0.0
        pos.append(p)
    return pd.Series(pos, index=c.index)


def ma_atr(c: pd.Series, n: int = 60, mult: float = 4.0) -> tuple[pd.Series, pd.Series]:
    """回傳 (部位, 停損線)；ATR 以收盤價變動絕對值 14 日平均近似（與回測一致）"""
    ma, atr = c.rolling(n).mean(), c.diff().abs().rolling(14).mean()
    pos, stops, p, stop, peak = [], [], 0.0, 0.0, 0.0
    for x, m, a in zip(c, ma, atr):
        if not (np.isnan(m) or np.isnan(a)):
            if p == 1:
                peak = max(peak, x)
                stop = max(stop, peak - mult * a)
                if x < stop or x < m:
                    p = 0.0
            elif x < m:
                stop = 0.0
            elif x > stop:
                p, peak, stop = 1.0, x, x - mult * a
        pos.append(p)
        stops.append(stop if p == 1 else np.nan)
    return pd.Series(pos, index=c.index), pd.Series(stops, index=c.index)


STRATEGIES = {
    "季線基準": lambda c: ma_filter(c, 60),
    "月線＋季線（半口）": lambda c: dual_half(c, 20, 60),
    "季線＋ATR×4 停損": lambda c: ma_atr(c, 60, 4.0)[0],
    "季線緩衝 ±2%": lambda c: hysteresis(c, 60, 0.02),
}


def paper_pnl(c: pd.Series, pos: pd.Series, start: str = PAPER_START) -> float:
    """從 start 起的模擬損益（元，1 口微台指，已扣成本）。
    以 start 前最後一個交易日收盤的部位為起始部位（建倉成本計入）；start 之前沒有資料則從 start 當天收盤建倉。"""
    s = pd.Timestamp(start)
    if not (c.index >= s).any():
        return 0.0
    before = c.index[c.index < s]
    base = before.max() if len(before) else c.index[c.index >= s][0]
    cc = c[c.index >= base]
    pp = pos.reindex(cc.index)
    pnl = (cc.diff() * pp.shift(1)).fillna(0).sum() * POINT_VALUE
    cost = (pp.diff().abs().fillna(pp.abs()) * cc * POINT_VALUE * COST_RATE).sum()
    return float(pnl - cost)


def snapshot(c: pd.Series) -> dict:
    """最新一天各策略的部位、前一天部位、停損線"""
    out = {}
    for name, fn in STRATEGIES.items():
        pos = fn(c)
        item = {"pos": float(pos.iloc[-1]), "prev": float(pos.iloc[-2]) if len(pos) > 1 else 0.0,
                "pnl": paper_pnl(c, pos)}
        if "ATR" in name:
            st = ma_atr(c, 60, 4.0)[1].iloc[-1]
            item["stop"] = None if np.isnan(st) else float(st)
        out[name] = item
    return out


def _lots(p: float) -> str:
    return "空手" if p == 0 else "做多 1 口" if p == 1 else f"做多 {p:g} 口"


def format_message(c: pd.Series, snap: dict) -> str:
    d = c.index[-1]
    ma20, ma60 = c.rolling(20).mean().iloc[-1], c.rolling(60).mean().iloc[-1]
    lines = [f"📈 *微台指模擬交易* {d:%m/%d}（紙上交易，不下單）",
             f"加權 {c.iloc[-1]:,.0f}｜月線 {ma20:,.0f}｜季線 {ma60:,.0f}", ""]
    changes = []
    for name, s in snap.items():
        extra = f"（停損 {s['stop']:,.0f}）" if s.get("stop") else ""
        mark = " ⚡" if s["pos"] != s["prev"] else ""
        lines.append(f"• {name}：{_lots(s['pos'])}{extra}{mark}")
        if s["pos"] != s["prev"]:
            changes.append(f"{name} {_lots(s['prev'])} → {_lots(s['pos'])}")
    lines.append("")
    lines.append("⚡ 今日變動：" + ("；".join(changes) if changes else "無"))
    lines.append("")
    lines.append(f"💰 模擬損益（{PAPER_START[5:].replace('-', '/')} 起，每口，已扣成本）")
    lines.append("｜".join(f"{n.split('（')[0]} {s['pnl']:+,.0f} 元" for n, s in snap.items()))
    lines.append("")
    lines.append("_回測與說明：research/strategies/index-trend-futures.md_")
    return "\n".join(lines)
