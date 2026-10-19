"""T-8.10d D-0: отчёт по журналу поиска — только агрегаты, без персональных данных."""

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.aggregator import search_report
from apps.aggregator.models import SearchQueryLog

pytestmark = pytest.mark.django_db


def _row(
    query,
    *,
    searches=1,
    zero=0,
    trigram=0,
    last=5,
    filters=None,
    lang="de",
    surface="portal",
    days_ago=0,
):
    return SearchQueryLog.objects.create(
        day=timezone.localdate() - timedelta(days=days_ago),
        surface=surface,
        city="Solingen",
        lang=lang,
        query_norm=query,
        filters_key=json.dumps(filters or {}, sort_keys=True),
        filters=filters or {},
        searches=searches,
        zero_results=zero,
        trigram_hits=trigram,
        last_results=last,
    )


@pytest.fixture
def rows():
    _row("brot", searches=10, last=12)
    _row("frische tomaten ohligs", searches=4, zero=4, last=0)
    _row("vegane torte geburtstag", searches=2, zero=0, last=2)
    _row("tomatn", searches=3, trigram=3, last=4)
    _row("", searches=5, filters={"kat": ["obst-gemuese"]}, last=7)
    _row("brot", searches=2, filters={"auto": "preis"}, last=3)
    _row("max mustermann hauptstr", searches=1, zero=1, last=0)  # одиночный — не в топ
    _row("alt", searches=50, days_ago=40)  # вне окна


def test_report_shares_are_aggregates(rows):
    r = search_report.build(days=30)
    total = 10 + 4 + 2 + 3 + 5 + 2 + 1
    assert r["searches"] == total
    assert r["zero_share"] == pytest.approx(5 / total)
    assert r["trigram_share"] == pytest.approx(3 / total)
    assert r["filters_only_share"] == pytest.approx(5 / total)
    assert r["auto_share"] == pytest.approx(2 / total)
    assert r["auto_keys"] == {"preis": 2}
    # многословные: «frische tomaten ohligs», «vegane torte geburtstag», «max mustermann hauptstr»
    assert r["multiword_share"] == pytest.approx(7 / total)
    # многословные с пустой/малой (≤3) выдачей — все три
    assert r["multiword_low_share"] == pytest.approx(7 / total)


def test_top_lists_hide_single_searches(rows):
    r = search_report.build(days=30)
    zero = [t["query"] for t in r["top_zero"]]
    assert "frische tomaten ohligs" in zero
    assert "max mustermann hauptstr" not in zero  # searches=1 → может быть именем
    low = [t["query"] for t in r["top_multiword_low"]]
    assert "vegane torte geburtstag" in low and "max mustermann hauptstr" not in low


def test_d2_recommendation_threshold(rows):
    r = search_report.build(days=30)
    assert r["d2_recommended"] is False  # < 500 поисков
    _row("rote paprika bio markt", searches=600, zero=600, last=0)
    assert search_report.build(days=30)["d2_recommended"] is True


def test_report_has_no_personal_fields(rows):
    r = search_report.build(days=30)
    assert set(r) == search_report.REPORT_KEYS
    for item in r["top_zero"] + r["top_multiword_low"]:
        assert set(item) == {"query", "searches", "lang"}


def test_report_counts_follow_kinds(rows):
    from apps.aggregator.models import FollowSubscription, PortalUser

    user = PortalUser.objects.create(email="leser@example.com")
    FollowSubscription.objects.create(
        user=user,
        target_kind="district",
        target_key="ohligs",
        city="Solingen",
        token="t-1",
        confirmed_at=timezone.now(),
    )
    assert search_report.build(days=30)["follow_kinds"] == {"district": 1}


def test_command_is_readonly_and_prints_json(rows, capsys):
    before = SearchQueryLog.objects.count()
    call_command("search_log_report", "--format", "json", "--days", "30")
    out = json.loads(capsys.readouterr().out)
    assert out["searches"] > 0
    assert SearchQueryLog.objects.count() == before


def test_surface_filter(rows):
    _row("mcp frage hier", searches=4, surface="mcp")
    assert search_report.build(days=30, surface="mcp")["searches"] == 4
