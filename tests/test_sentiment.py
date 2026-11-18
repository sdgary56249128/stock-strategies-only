import pandas as pd

from stock_strategies.sentiment import pc_ratio_series, vix_level


def test_vix_level():
    assert [vix_level(x) for x in (12, 18, 25, 35)] == ["樂觀", "正常", "緊張", "恐慌"]


def test_pc_ratio_uses_regular_session_open_interest():
    rows = [("2026-11-17", "put", 50, "position"), ("2026-11-17", "call", 100, "position"),
            ("2026-11-17", "put", 999, "after_market")]
    df = pd.DataFrame(rows, columns=["date", "call_put", "open_interest", "trading_session"])
    assert pc_ratio_series(df).to_dict() == {"2026-11-17": 0.5}
