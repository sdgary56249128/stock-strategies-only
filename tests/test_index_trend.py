import pandas as pd

from stock_strategies.index_trend import dual_half, format_message, ma_atr, paper_pnl, snapshot


def _c(vals, start="2026-08-01"):
    return pd.Series(vals, index=pd.bdate_range(start, periods=len(vals)), dtype=float)


def test_dual_half_levels():
    c = _c([100.0] * 60 + [110] * 5)
    assert dual_half(c).iloc[-1] == 1.0
    c2 = _c(list(range(100, 160)) + [150])  # 跌破月線、仍在季線上
    assert dual_half(c2).iloc[-1] == 0.5


def test_ma_atr_exits_on_drop():
    c = _c([100.0] * 60 + [101, 103, 106, 110, 115, 120, 90])
    pos, stop = ma_atr(c)
    assert pos.iloc[-2] == 1 and pos.iloc[-1] == 0


def test_paper_pnl_points_to_ntd():
    c = _c([100.0, 100, 110, 120], start="2026-11-17")
    pos = pd.Series([1.0, 1, 1, 1], index=c.index)
    # 基準日 11/18（11/19 前最後一天）收盤 100 建倉，賺 20 點 = 200 元，扣建倉成本 100×10×0.0003
    assert round(paper_pnl(c, pos, "2026-11-19"), 2) == round(200 - 0.3, 2)


def test_format_message_marks_change():
    c = _c([100.0] * 60 + [120])
    text = format_message(c, snapshot(c))
    assert "⚡ 今日變動：" in text and "→ 做多 1 口" in text
