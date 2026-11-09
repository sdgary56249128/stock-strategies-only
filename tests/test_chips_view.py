from stock_strategies.chips_view import (chips_line, futures_line, summarize_futures_oi,
                                         summarize_stock_chips)


def _r(d, name, buy, sell):
    return {"date": d, "name": name, "buy": buy, "sell": sell}


def test_stock_chips_streak_and_units():
    rows = [_r("2026-11-03", "Foreign_Investor", 0, 5000),
            _r("2026-11-04", "Foreign_Investor", 3000, 1000),
            _r("2026-11-05", "Foreign_Investor", 4000, 1000),
            _r("2026-11-05", "Investment_Trust", 2000, 0),
            _r("2026-11-05", "Dealer_self", 0, 1000),
            _r("2026-11-05", "Dealer_Hedging", 0, 500)]
    c = summarize_stock_chips(rows)
    assert c["foreign"] == 3 and c["trust"] == 2 and c["dealer"] == -2
    assert c["foreign_streak"] == 2
    assert "外資連買 2 天" in chips_line(c)


def test_futures_oi_change():
    rows = [{"date": "2026-11-05", "institutional_investors": "外資",
             "long_open_interest_balance_volume": 13388, "short_open_interest_balance_volume": 109039},
            {"date": "2026-11-06", "institutional_investors": "外資",
             "long_open_interest_balance_volume": 15873, "short_open_interest_balance_volume": 115803},
            {"date": "2026-11-06", "institutional_investors": "投信",
             "long_open_interest_balance_volume": 1, "short_open_interest_balance_volume": 0}]
    f = summarize_futures_oi(rows)
    assert f == {"date": "2026-11-06", "net": -99930, "chg": -4279}
    assert futures_line(f) == "🌐 外資台指期淨空 99,930 口，較前日加空 4,279 口（11/06）"


def test_add_premarket_chips():
    from stock_strategies.chips_view import add_premarket_chips
    text = "🌙 快報\n夜盤\n\n📋 *昨日訊號*\n🟡 WATCH 2330 台積電 73分 · 順風\n↳ 說明"
    c = {"date": "2026-11-06", "foreign": -1, "trust": 2, "dealer": 0, "foreign_streak": -1, "total_5d": 1}
    out = add_premarket_chips(text, fetch=lambda sid: c if sid == "2330" else None, fut="🌐 外資")
    assert "夜盤\n🌐 外資\n\n📋" in out
    assert "台積電 73分 · 順風\n    🏦 法人（11/06）: 外資 -1" in out
