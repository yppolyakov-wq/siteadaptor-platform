"""Замок помощника `future_month_start`: дата ВСЕГДА в будущем, переход через год и
февраль без особых случаев (иначе бомба просто переехала бы на другую дату)."""

from datetime import date

import pytest

from apps.core.tests import dates


@pytest.mark.parametrize(
    "today,months,expected",
    [
        (date(2026, 10, 2), 2, date(2026, 12, 1)),
        (date(2026, 11, 30), 2, date(2027, 1, 1)),  # через год
        (date(2026, 12, 31), 3, date(2027, 3, 1)),
        (date(2027, 1, 31), 1, date(2027, 2, 1)),  # февраль: 1-е число есть всегда
    ],
)
def test_future_month_start_crosses_year_and_february(monkeypatch, today, months, expected):
    class _Frozen(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(dates, "date", _Frozen)
    got = dates.future_month_start(months)
    assert got == expected and got > today
