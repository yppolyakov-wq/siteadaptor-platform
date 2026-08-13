"""MEN-12: отложенные предложения агрегатора + сравнение вариантов.

Запрос владельца: «для агрегатора нужно что-то наподобие избранного отложенного
или корзина, где потом можно сравнить варианты». v1 — сессия, без аккаунта.
"""

from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator import shortlist, views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _req(method="get", path="/entdecken/merkliste/", data=None, session=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    return request


def _listing(title, **kw):
    return AggregatorListing.objects.create(
        tenant_schema="public",
        listing_kind=AggregatorListing.KIND_MENU,
        source_ref=title,
        title={"de": title},
        business_name=kw.pop("business", "Grüne Tafel"),
        city=kw.pop("city", "Düsseldorf"),
        detail_url="https://example.de/kombi/1/",
        **kw,
    )


def test_toggle_adds_and_removes_without_account():
    a = _listing("Menü A")
    request = _req()
    assert shortlist.toggle(request, a.pk) is True
    assert shortlist.ids(request) == [a.pk] and shortlist.count(request) == 1
    assert shortlist.has(request, a.pk)
    assert shortlist.toggle(request, a.pk) is False
    assert shortlist.ids(request) == []


def test_garbage_and_cap_do_not_break():
    request = _req(session={"shortlist": ["nope", 7]})
    assert shortlist.ids(request) == [7]  # мусор молча выпал
    for i in range(20):
        shortlist.toggle(_req(session={"shortlist": shortlist.ids(request)}), i)
    request2 = _req()
    for i in range(20):
        shortlist.toggle(request2, i)
    assert len(shortlist.ids(request2)) == shortlist.SHORTLIST_MAX  # кап держит


def test_dead_listing_falls_out_of_comparison():
    """Предложение могло закончиться, пока гость сравнивал."""
    a, b = _listing("Menü A"), _listing("Menü B")
    request = _req(session={"shortlist": [a.pk, b.pk]})
    b.is_active = False
    b.save(update_fields=["is_active"])
    assert [x.pk for x in shortlist.listings(request)] == [a.pk]


def test_compare_rows_skip_empty_and_show_values():
    a = _listing(
        "Menü A",
        new_price=Decimal("45.00"),
        price_per_person=True,
        min_persons=20,
        event_types=["Hochzeit"],
        diets=["vegan"],
    )
    b = _listing("Menü B", business="Andere", new_price=Decimal("39.00"), city="Köln")
    rows = dict((label, values) for label, values in shortlist.compare_rows([a, b]))
    assert rows["Anbieter"] == ["Grüne Tafel", "Andere"]
    assert rows["Ort"] == ["Düsseldorf", "Köln"]
    assert rows["Preis"][0].startswith("ab 45,00") and "/ Gast" in rows["Preis"][0]
    assert rows["Preis"][1] == "ab 39,00 EUR"  # без per-person суффикса
    assert rows["Mindestbestellung"] == ["ab 20 Personen", ""]
    assert "Bewertung" not in rows  # ни у кого нет отзывов — ряд не рендерим


def test_compare_page_renders_table_and_empty_state():
    a = _listing("Menü A", new_price=Decimal("45.00"))
    body = views.shortlist_compare(_req(session={"shortlist": [a.pk]})).content.decode()
    assert "Menü A" in body and "Anbieter" in body

    empty = views.shortlist_compare(_req()).content.decode()
    assert "Noch nichts gemerkt" in empty


def test_toggle_view_redirects_back_and_rejects_foreign_next():
    a = _listing("Menü A")
    resp = views.shortlist_toggle(
        _req("post", "/entdecken/merkliste/toggle/", {"listing": str(a.pk), "next": "/entdecken/"})
    )
    assert resp.status_code == 302 and resp.url == "/entdecken/"
    evil = views.shortlist_toggle(
        _req(
            "post",
            "/entdecken/merkliste/toggle/",
            {"listing": str(a.pk), "next": "https://evil.de/"},
        )
    )
    assert evil.url == "/entdecken/"  # чужой хост в next не проходит


def test_no_session_does_not_break_pages():
    """Регресс: контекст-процессор падал на запросе БЕЗ сессии (кэш-прогрев,
    вьюх-тесты на RequestFactory) — страницы выдачи ложились с AttributeError."""
    from apps.aggregator import context

    bare = RequestFactory().get("/entdecken/Hilden/")  # без SessionMiddleware
    assert shortlist.ids(bare) == [] and shortlist.count(bare) == 0
    assert shortlist.toggle(bare, 1) is False
    ctx = context.shortlist(bare)
    assert ctx["shortlist_enabled"] is False and ctx["shortlist_count"] == 0


def test_context_processor_scoped_to_aggregator_paths():
    """Вне /entdecken/ процессор молчит — витрины тенантов не задеты."""
    from apps.aggregator import context

    assert context.shortlist(_req("get", "/sortiment/")) == {}
    assert "shortlist_enabled" in context.shortlist(_req("get", "/entdecken/"))
