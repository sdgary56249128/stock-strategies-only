from datetime import date

from stock_strategies import trading_calendar as tc


class _Resp:
    def __init__(self, dates):
        self._dates = dates

    def json(self):
        return {"data": [{"date": d} for d in self._dates]}


def _fake_get(dates):
    return lambda *a, **k: _Resp(dates)


def test_weekend_is_closed_without_api(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not call API on weekends")
    monkeypatch.setattr(tc.requests, "get", boom)
    assert tc.is_trading_day(date(2026, 11, 1)) is False


def test_holiday_and_trading_day(monkeypatch):
    monkeypatch.setattr(tc.requests, "get", _fake_get(["2026-10-08", "2026-10-12", "2026-12-31"]))
    assert tc.is_trading_day(date(2026, 10, 9)) is False
    assert tc.is_trading_day(date(2026, 10, 12)) is True


def test_unpublished_calendar_is_unknown(monkeypatch):
    monkeypatch.setattr(tc.requests, "get", _fake_get(["2026-12-31"]))
    assert tc.is_trading_day(date(2027, 6, 1)) is None


def test_api_error_does_not_skip(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(tc.requests, "get", boom)
    monkeypatch.setattr(tc, "taipei_today", lambda: date(2026, 11, 2))
    monkeypatch.delenv("FORCE_RUN", raising=False)
    assert tc.should_skip() is False


def test_force_run(monkeypatch):
    monkeypatch.setenv("FORCE_RUN", "1")
    monkeypatch.setattr(tc, "taipei_today", lambda: date(2026, 11, 1))
    assert tc.should_skip() is False
