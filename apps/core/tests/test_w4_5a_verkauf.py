# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS W4-5a «Verkauf öffnen»: вопросы пишут УЗКИМИ писателями (план
docs/ais-w4-5-verkauf-oeffnen-plan-2026-11-06.md + правки architect).

Замки: ответ о доставке не трогает зоны/сборы/точки самовывоза; ответ о Vorkasse не трогает
банк; без IBAN — ссылка, а не переключатель; «нет» хранится отметкой и переживает Save
конструктора и устаревший тенант; отметка не делает готовым; права; экран без JS.
"""

import pytest
from django.urls import reverse

from apps.core import readiness, sell_questions, views
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _clean,
    _req,
    _urlconf,
    _user,
    bakery,
)
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

ZONES = [{"plz": "40721", "fee_cents": 350, "free_cents": 0, "min_cents": 0}]
PICKUP = [{"name": "Markt", "address": "Hauptstr. 1"}]


@pytest.fixture
def shop(bakery):
    bakery.delivery_zones = ZONES
    bakery.delivery_fee_cents = 290
    bakery.pickup_locations = PICKUP
    bakery.delivery_restrict_to_zones = True
    bakery.bank_holder, bakery.bank_iban, bakery.bank_bic = (
        "Laden",
        "DE89370400440532013000",
        "COBADEFF",
    )
    bakery.save()
    return bakery


def _answer(tenant, key, choice, user=None):
    request = _req(tenant, "post", {"frage": key, "antwort": choice}, user=user)
    return views.verkauf_oeffnen(request)


def test_delivery_answer_keeps_zones_fees_and_pickup(shop):
    _answer(shop, "waren.delivery", "ja")
    fresh = Tenant.objects.get(pk=shop.pk)
    assert fresh.delivery_enabled is True
    assert fresh.delivery_zones == ZONES and fresh.pickup_locations == PICKUP
    assert fresh.delivery_fee_cents == 290 and fresh.delivery_restrict_to_zones is True


def test_vorkasse_answer_keeps_bank(shop):
    _answer(shop, "waren.vorkasse", "ja")
    fresh = Tenant.objects.get(pk=shop.pk)
    assert fresh.vorkasse_enabled is True
    assert (fresh.bank_holder, fresh.bank_iban, fresh.bank_bic) == (
        "Laden",
        "DE89370400440532013000",
        "COBADEFF",
    )


def test_vorkasse_without_iban_is_a_link_not_a_switch(bakery):
    rows = {r["key"]: r for r in sell_questions.questions_for(_req(bakery))}
    assert rows["waren.vorkasse"]["blocked"]
    _answer(bakery, "waren.vorkasse", "ja")
    assert Tenant.objects.get(pk=bakery.pk).vorkasse_enabled is False


def test_no_is_a_mark_and_data_stays_the_truth(shop):
    _answer(shop, "waren.delivery", "nein")
    fresh = Tenant.objects.get(pk=shop.pk)
    assert fresh.delivery_enabled is False
    assert fresh.site_config["verkauf"] == {"no": ["waren.delivery"]}
    assert sell_questions.state(fresh, sell_questions.BY_KEY["waren.delivery"]) == "nein"
    fresh.delivery_enabled = True  # включили на экране оплаты — данные сильнее отметки
    assert sell_questions.state(fresh, sell_questions.BY_KEY["waren.delivery"]) == "ja"
    _answer(shop, "waren.delivery", "ja")
    assert "verkauf" not in Tenant.objects.get(pk=shop.pk).site_config


def test_mark_survives_builder_save_and_stale_tenant(shop):
    stale = Tenant.objects.get(pk=shop.pk)
    _answer(shop, "waren.delivery", "nein")
    assert siteconfig.normalize(Tenant.objects.get(pk=shop.pk).site_config)["verkauf"]
    stale_cfg = dict(stale.site_config or {})
    sell_questions._mark(stale, "waren.vorkasse", no=True)  # пишет из ЗАБЛОКИРОВАННОЙ строки
    marks = Tenant.objects.get(pk=shop.pk).site_config["verkauf"]["no"]
    assert set(marks) == {"waren.delivery", "waren.vorkasse"} and "verkauf" not in stale_cfg


def test_mark_never_makes_readiness_done(shop):
    shop.delivery_enabled = True
    shop.save()
    sell_questions._mark(shop, "waren.vorkasse", no=True)
    readiness.invalidate(shop)
    row = next(r for r in readiness.items_for(shop) if r["key"] == "waren.prepay")
    assert row["done"] is False


def test_without_edit_right_nothing_is_written(shop, monkeypatch):
    from apps.core import permissions

    monkeypatch.setattr(permissions, "has_perm", lambda user, key: key != sell_questions.PERM)
    _answer(shop, "waren.delivery", "ja")
    assert Tenant.objects.get(pk=shop.pk).delivery_enabled is False


def test_unknown_question_writes_nothing(shop):
    before = Tenant.objects.get(pk=shop.pk).site_config
    _answer(shop, "waren.nope", "ja")
    _answer(shop, "waren.delivery", "vielleicht")
    assert Tenant.objects.get(pk=shop.pk).site_config == before


def test_screen_renders_without_js_and_has_nav_entry(shop):
    resp = views.verkauf_oeffnen(_req(shop))
    html = resp.content.decode()
    assert 'data-verkauf-question="waren.delivery"' in html
    assert 'name="antwort" value="ja"' in html  # обычная форма — работает без JS
    from apps.core import nav_registry

    assert any(e.url_name == "verkauf-oeffnen" for e in nav_registry.ENTRIES)
    assert reverse("verkauf-oeffnen") == "/dashboard/verkauf-oeffnen/"


def test_post_redirects_to_question(shop):
    resp = _answer(shop, "waren.delivery", "ja")
    assert resp.status_code == 302 and resp["Location"].endswith("#q-waren-delivery")


def test_blocked_question_can_still_be_answered_no(bakery):
    _answer(bakery, "waren.vorkasse", "nein")
    assert Tenant.objects.get(pk=bakery.pk).site_config["verkauf"]["no"] == ["waren.vorkasse"]


def test_free_delivery_warning_covers_zones_without_restriction(shop):
    shop.delivery_enabled, shop.delivery_fee_cents = True, 0
    shop.delivery_restrict_to_zones = False  # зоны есть, но вне них — бесплатно
    assert sell_questions._delivery_note(shop)
    shop.delivery_restrict_to_zones = True
    assert not sell_questions._delivery_note(shop)


def test_broken_question_is_shown_not_hidden(shop, monkeypatch):
    broken = sell_questions.BY_KEY["waren.delivery"]
    monkeypatch.setattr(
        sell_questions,
        "QUESTIONS",
        (sell_questions.Question(**{**broken.__dict__, "applies": lambda t: 1 / 0}),),
    )
    html = views.verkauf_oeffnen(_req(shop)).content.decode()
    assert "data-verkauf-failed" in html and "Alle Fragen sind beantwortet" not in html


def test_mark_failure_rolls_back_the_switch(shop, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("lock")

    monkeypatch.setattr(sell_questions, "_mark", boom)
    with pytest.raises(RuntimeError):
        sell_questions.answer(_req(shop, "post", user=_user()), "waren.delivery", "ja")
    assert Tenant.objects.get(pk=shop.pk).delivery_enabled is False


def test_unknown_key_redirects_without_fragment(shop):
    resp = _answer(shop, "x\nevil", "ja")
    assert resp["Location"] == reverse("verkauf-oeffnen")


# ── W4-5b: остальные направления — подтверждения, настройки не трогаются ──


def test_confirm_questions_only_mark_and_never_touch_settings(shop, monkeypatch):
    from apps.core import directions

    monkeypatch.setattr(
        directions, "active", lambda t: [directions.get(k) for k in ("termine", "zimmer")]
    )
    keys = {r["key"] for r in sell_questions.questions_for(_req(shop))}
    assert {"termine.cancel", "zimmer.cancel", "zimmer.kurtaxe"} <= keys
    assert "tickets.refund" not in keys
    before = {
        f: getattr(Tenant.objects.get(pk=shop.pk), f)
        for f in ("delivery_enabled", "vorkasse_enabled", "delivery_zones")
    }
    _answer(shop, "zimmer.cancel", "ja")
    fresh = Tenant.objects.get(pk=shop.pk)
    assert fresh.site_config["verkauf"] == {"ok": ["zimmer.cancel"]}
    assert {f: getattr(fresh, f) for f in before} == before
    assert sell_questions.state(fresh, sell_questions.BY_KEY["zimmer.cancel"]) == "ja"
    html = views.verkauf_oeffnen(_req(fresh)).content.decode()
    block = html.split('data-verkauf-question="zimmer.kurtaxe"')[1].split("</li>")[0]
    assert 'value="nein"' not in block  # у подтверждения нет «нет»


def test_confirm_links_go_through_rights(shop, monkeypatch):
    from apps.core import assistant, directions

    monkeypatch.setattr(directions, "active", lambda t: [directions.get("tickets")])
    monkeypatch.setattr(assistant, "link", lambda request, name, **kw: None)
    row = next(r for r in sell_questions.questions_for(_req(shop)) if r["key"] == "tickets.refund")
    assert row["more"] is None
