from datetime import date

from weekly_report import build_report


def _sig(d, sid, action, score, name="測試"):
    return {"date": d, "stock_id": sid, "name": name, "action": action, "signal_score": score}


WL = [{"stock_id": "2330", "category": "半導體"}, {"stock_id": "2317", "category": "AI伺服器"}]


def test_no_signals_this_week_returns_none():
    old = [_sig("2026-10-30", "2330", "WATCH", 70)]
    assert build_report(old, WL, [], date(2026, 11, 6)) is None


def test_report_counts_and_repeats():
    sigs = [
        _sig("2026-11-02", "2330", "WATCH", 70, "台積電"),
        _sig("2026-11-03", "2330", "BUY", 75, "台積電"),
        _sig("2026-11-03", "2317", "SKIP", 40, "鴻海"),
        _sig("2026-10-30", "2317", "WATCH", 60, "鴻海"),  # last week, ignored
    ]
    perf = [{"t5_ret": "2.5", "status": "追蹤中", "hit_stop": "", "hit_target": "Y"},
            {"t5_ret": "-1", "status": "追蹤中", "hit_stop": "Y", "hit_target": ""}]
    text = build_report(sigs, WL, perf, date(2026, 11, 6))
    assert "2 個交易日" in text
    assert "11/03（二）BUY 1 | WATCH 0 | SKIP 1" in text
    assert "2330 台積電（半導體）2/2 天｜70 ↗ 75，含 BUY" in text
    assert "半導體 2" in text
    assert "T+5：2 筆，上漲比例 50%" in text
    assert "觸及停利 1 次｜觸及停損 1 次" in text
