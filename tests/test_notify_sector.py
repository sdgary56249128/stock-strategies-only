from stock_strategies.notify_sector import format_sector_messages


def _s(sid, name, action, chg=1.0):
    return {"stock_id": sid, "name": name, "action": action, "signal_score": 40,
            "trend": {"chg_5d": chg}, "components": {}}


def test_all_skip_sectors_are_merged():
    wl = [{"stock_id": "1", "category": "金融"}, {"stock_id": "2", "category": "航運"},
          {"stock_id": "3", "category": "金融"}]
    msgs = format_sector_messages([_s("1", "甲", "SKIP"), _s("2", "乙", "SKIP", -2), _s("3", "丙", "SKIP")], wl)
    assert len(msgs) == 1
    assert "其他族群*（2 個" in msgs[0]
    assert "1甲(40), 3丙(40)" in msgs[0] and "2乙(40)" in msgs[0]
