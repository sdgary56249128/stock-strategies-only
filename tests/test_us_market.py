from stock_strategies.us_market import adr_premium, format_us_block


def test_adr_premium():
    assert round(adr_premium(398.73, 32.939, 2350), 1) == 11.8


def test_format_us_block():
    q = lambda d, p: {"date": d, "close": 1, "pct": p}
    text = format_us_block([("費半", q("2026-11-13", -3.43)), ("標普", None)], q("2026-11-13", -1.67), 11.8,
                           [("NVDA", q("2026-11-13", -2.01)), ("MU", None)])
    assert text.splitlines() == ["🇺🇸 *昨晚美股*（11/13 收盤）", "費半 -3.4%", "台積電 ADR -1.7%（ADR 溢價 +11.8%）", "NVDA -2.0%"]
    assert format_us_block([("費半", None)], None, None, []) is None
