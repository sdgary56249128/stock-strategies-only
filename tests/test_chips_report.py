from datetime import date

from chips_report import build_report


def test_build_report_sorts_by_total_net():
    c = lambda f, t: {"date": "2026-11-09", "foreign": f, "trust": t, "dealer": 0, "foreign_streak": 1, "total_5d": 0}
    picks = [{"stock_id": "1", "name": "甲", "action": "WATCH", "score": 60, "category": "A", "chips": c(-5, 0)},
             {"stock_id": "2", "name": "乙", "action": "BUY", "score": 70, "category": "B", "chips": c(10, 2)},
             {"stock_id": "3", "name": "丙", "action": "WATCH", "score": 55, "category": "C", "chips": None}]
    text = build_report(date(2026, 11, 9), "🌐 外資", picks)
    assert "外資買超 1 檔｜賣超 1 檔" in text
    assert text.index("2 乙") < text.index("3 丙") < text.index("1 甲")
    assert "法人資料取不到" in text
