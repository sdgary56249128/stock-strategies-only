import pandas as pd

from stock_strategies.performance_atr import stats, track


def _px(closes):
    d = pd.bdate_range("2026-01-01", periods=len(closes)).strftime("%Y-%m-%d")
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"date": d, "open": c, "high": c + 1, "low": c - 1, "close": c})


def test_holding_then_exit():
    closes = [100.0] * 30 + [110, 120, 130, 140, 150] + [100, 99, 98]
    px = _px(closes)
    sig = px["date"].iloc[29]
    t = track(px, sig)
    assert t["entry_open"] == 110 and t["status"] == "已出場"
    assert t["exit_price"] == 99 and t["peak_close"] == 150
    t2 = track(px.iloc[:35], sig)
    assert t2["status"] == "持有中" and t2["last_close"] == 150


def test_not_entered_yet():
    px = _px([100.0] * 30)
    assert track(px, px["date"].iloc[-1]) is None


def test_stats():
    s = stats([{"status": "已出場", "ret_pct": 5}, {"status": "已出場", "ret_pct": -3}, {"status": "持有中", "ret_pct": 2}])
    assert s == {"total": 3, "open": 1, "closed": 2, "winrate": 50, "avg_closed": 1.0, "avg_open": 2.0}
