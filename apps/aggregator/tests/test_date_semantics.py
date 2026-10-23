"""Дата из фразы и кнопка даты не выбрасывают товары и заведения («Pizza morgen»).

Пересмотр Р-О1 (2026-10-23): события и акции — окном, товары/услуги/меню/бизнес — по
часам работы (открыт хотя бы в один день окна), номера — без фильтра. План —
docs/t8-34-date-semantics-plan-2026-10-23.md.
"""

from datetime import datetime
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import follow_query, search, views
from apps.aggregator.models import AggregatorListing
from apps.tenants import openinghours
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Среда, 21.10.2026, 12:00 по Берлину. «morgen» = четверг (weekday 3).
NOW = timezone.make_aware(datetime(2026, 10, 21, 12, 0))
ALL_WEEK = {str(d): ["09:00", "18:00"] for d in range(7)}
_n = iter(range(100_000))


@pytest.fixture(autouse=True)
def _frozen():
    cache.clear()
    with mock.patch("django.utils.timezone.now", return_value=NOW):
        yield
    cache.clear()


def _biz(hours):
    i = next(_n)
    return TenantFactory(schema_name=f"ds_{i}", slug=f"ds-{i}", opening_hours_structured=hours)


def _listing(title, *, kind, schema, **kw):
    i = next(_n)
    return AggregatorListing.objects.create(
        tenant_schema=schema,
        tenant_slug=f"x{i}",
        city="Solingen",
        listing_kind=kind,
        source_ref=f"s{i}",
        title={"de": title},
        business_name=f"Laden {i}",
        detail_url="https://x.siteadaptor.de/",
        **kw,
    )


def _found(q, **params):
    filters = search.SearchFilters(**params)
    q_eff, eff, _chips, _hints = search.resolve_intent(q, filters, city="Solingen")
    out = search.execute(views.listings_for(city="Solingen"), q_eff, eff, surface="test")
    return [x.title["de"] for x in out.qs]


def test_pizza_morgen_finds_product_when_open_tomorrow():
    biz = _biz(ALL_WEEK)
    _listing("Pizza Verdure", kind="product", schema=biz.schema_name)
    assert _found("Pizza morgen") == ["Pizza Verdure"]


def test_pizza_morgen_drops_product_when_closed_tomorrow_but_keeps_event():
    closed_thursday = {k: v for k, v in ALL_WEEK.items() if k != "3"}
    biz = _biz(closed_thursday)
    _listing("Pizza Verdure", kind="product", schema=biz.schema_name)
    tomorrow = timezone.make_aware(datetime(2026, 10, 22, 19, 0))
    _listing("Pizza-Abend", kind="event", schema=biz.schema_name, starts_at=tomorrow)
    assert _found("Pizza morgen") == ["Pizza-Abend"]


def test_unknown_hours_keep_product():
    biz = _biz({})
    _listing("Pizza Verdure", kind="product", schema=biz.schema_name)
    assert _found("Pizza morgen") == ["Pizza Verdure"]


@pytest.mark.parametrize(("hour", "found"), [(10, True), (22, False)])
def test_heute_after_closing_drops(hour, found):
    biz = _biz(ALL_WEEK)
    _listing("Brot", kind="product", schema=biz.schema_name)
    at = timezone.make_aware(datetime(2026, 10, 21, hour, 0))
    with mock.patch("django.utils.timezone.now", return_value=at):
        assert (_found("Brot heute") == ["Brot"]) is found


def test_wochenende_needs_saturday_or_sunday():
    sunday_only = {"6": ["10:00", "14:00"]}
    open_biz, closed_biz = _biz(sunday_only), _biz({"0": ["09:00", "18:00"]})
    _listing("Kuchen Sonntag", kind="product", schema=open_biz.schema_name)
    _listing("Kuchen Werktag", kind="product", schema=closed_biz.schema_name)
    assert _found("Kuchen am Wochenende") == ["Kuchen Sonntag"]


def test_stay_is_not_filtered_by_date():
    biz = _biz({"0": ["09:00", "10:00"]})
    _listing("Zimmer Seeblick", kind="stay", schema=biz.schema_name)
    assert _found("", date="heute") == ["Zimmer Seeblick"]


def test_dated_kinds_still_need_the_window():
    biz = _biz(ALL_WEEK)
    later = timezone.make_aware(datetime(2026, 11, 20, 19, 0))
    _listing("Konzert später", kind="event", schema=biz.schema_name, starts_at=later)
    assert _found("Konzert heute") == []


def test_phrase_date_equals_explicit_date():
    biz = _biz(ALL_WEEK)
    _listing("Pizza Verdure", kind="product", schema=biz.schema_name)
    assert _found("Pizza morgen") == _found("Pizza", date="2026-10-22")


def test_subscription_set_never_gets_the_date():
    from django.http import QueryDict

    assert follow_query.canonical(QueryDict("q=Pizza+morgen"), city="Solingen") == (("q", "Pizza"),)


def test_open_on_helper():
    thursday = datetime(2026, 10, 22).date()
    assert openinghours.open_on({}, thursday) is None
    assert openinghours.open_on({"3": ["09:00", "18:00"]}, thursday) is True
    assert openinghours.open_on({"2": ["09:00", "18:00"]}, thursday) is False
    late = datetime(2026, 10, 22, 19, 0).time()
    assert openinghours.open_on({"3": ["09:00", "18:00"]}, thursday, after=late) is False


def test_date_adds_one_query(django_assert_max_num_queries):
    for _ in range(5):
        biz = _biz(ALL_WEEK)
        _listing("Pizza", kind="product", schema=biz.schema_name)
    base = views.listings_for(city="Solingen")
    list(base)  # прогрев: сколько стоит пул без даты
    # Дата добавляет ровно один запрос к Tenant (часы), а не по запросу на бизнес.
    with django_assert_max_num_queries(3):
        list(search.apply_filters(base, search.SearchFilters(date="heute")))


def test_every_listing_kind_has_a_date_rule():
    """Новый вид листинга не должен молча пропадать при дате."""
    kinds = {k for k, _ in AggregatorListing.KINDS}
    assert kinds == set(search.DATED_KINDS) | set(search.HOURS_GATED_KINDS) | set(
        search.UNGATED_KINDS
    )


def test_past_date_drops_products():
    biz = _biz(ALL_WEEK)
    _listing("Pizza Verdure", kind="product", schema=biz.schema_name)
    assert _found("Pizza", date="2026-10-01") == []


@pytest.mark.parametrize(
    ("q", "lang"),
    [
        ("пиццу завтра", "ru"),
        ("піцу завтра", "uk"),
        ("pizza tomorrow", "en"),
        ("yarın pizza", "tr"),
    ],
)
def test_date_word_is_understood_in_the_visitors_language(q, lang):
    """Фидбэк владельца: «пиццу завтра» на русском портале — 0 результатов: «завтра»
    оставалось словом поиска, а его нет ни в одном предложении."""
    from django.utils import translation

    biz = _biz(ALL_WEEK)
    AggregatorListing.objects.create(
        tenant_schema=biz.schema_name,
        tenant_slug="pz",
        city="Solingen",
        listing_kind="product",
        source_ref="pz",
        title={
            "de": "Pizza Verdure",
            "ru": "Пицца с овощами",
            "uk": "Піца з овочами",
            "en": "Pizza with vegetables",
            "tr": "Sebzeli pizza",
        },
        business_name="Trattoria",
        detail_url="https://x.siteadaptor.de/",
    )
    filters = search.SearchFilters()
    q_eff, eff, _chips, _hints = search.resolve_intent(q, filters, city="Solingen")
    assert eff.date == "2026-10-22"
    with translation.override(lang):
        out = search.execute(
            views.listings_for(city="Solingen"), q_eff, eff, surface="test", lang=lang
        )
    assert [x.title["de"] for x in out.qs] == ["Pizza Verdure"]
