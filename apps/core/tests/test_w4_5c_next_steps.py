# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS W4-5c: карточки «Nächster Schritt» на главной (мастер v4).

Замки: не больше трёх, порядок — польза; модуль выключен → нет карточки; ссылка без права →
нет карточки; сломанная проверка → нет карточки (главная жива); «Später» прячет на 14 дней и
переживает Save конструктора; v3-главная — прежний чек-лист, без карточек.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import next_steps, sell_questions, views
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


@pytest.fixture
def v4(bakery):
    bakery.published_at = None  # неопубликованный сайт = мастер v4
    bakery.save()
    return bakery


def _keys(tenant):
    return [c["key"] for c in next_steps.cards(_req(tenant))]


def test_at_most_three_in_usefulness_order(v4):
    keys = _keys(v4)
    assert 1 <= len(keys) <= next_steps.LIMIT
    assert keys[0] == "publish"
    order = [c.key for c in next_steps.CARDS]
    assert keys == sorted(keys, key=order.index)


def test_verkauf_card_disappears_when_questions_answered(v4):
    assert "verkauf" in _keys(v4)
    for q in sell_questions.QUESTIONS:
        sell_questions._mark(v4, q.key, no=True)
    assert "verkauf" not in _keys(Tenant.objects.get(pk=v4.pk))


def test_module_off_hides_card(v4, monkeypatch):
    real = Tenant.is_module_active
    monkeypatch.setattr(Tenant, "is_module_active", lambda self, k: k != "orders" and real(self, k))
    assert "verkauf" not in _keys(v4)


def test_no_link_no_card(v4, monkeypatch):
    from apps.core import assistant

    monkeypatch.setattr(assistant, "link", lambda request, name, **kw: None)
    assert _keys(v4) == []


def test_broken_check_hides_only_that_card(v4, monkeypatch):
    broken = next_steps.Card("publish", "x", lambda t: 1 / 0, "setup", "x")
    monkeypatch.setattr(next_steps, "CARDS", (broken, *next_steps.CARDS[1:]))
    keys = _keys(v4)
    assert "publish" not in keys and keys


def test_later_hides_for_14_days_and_survives_builder_save(v4):
    assert next_steps.hide(v4, "verkauf")
    fresh = Tenant.objects.get(pk=v4.pk)
    assert "verkauf" not in _keys(fresh)
    assert siteconfig.normalize(fresh.site_config)["next_steps"]["hidden"]["verkauf"]
    later = timezone.now() + timedelta(days=15)
    assert not next_steps._is_hidden(fresh, "verkauf", later)
    assert not next_steps.hide(v4, "unbekannt")


def test_dashboard_v4_shows_cards_not_checklist(bakery):
    # опубликованный бизнес мастера v4 (неопубликованный уходит в мастер)
    cfg = dict(bakery.site_config or {})
    cfg["onboarding"] = {**(cfg.get("onboarding") or {}), "flow": "v4", "completed": True}
    bakery.site_config = cfg
    bakery.save()
    resp = views.dashboard(_req(bakery))
    html = resp.content.decode()
    assert resp.status_code == 200, resp.status_code
    assert "data-next-steps" in html and 'data-next-step="verkauf"' in html
    assert "Ihre Website ist zu" not in html


def test_dashboard_v3_keeps_checklist(bakery):
    cfg = dict(bakery.site_config or {})
    cfg.pop("onboarding", None)
    bakery.site_config = cfg
    bakery.save()
    assert bakery.published_at is not None
    html = views.dashboard(_req(bakery)).content.decode()
    assert "data-next-steps" not in html


def test_assistant_button_carries_a_rules_phrase(v4):
    cards = next_steps.cards(_req(v4), limit=10)
    with_q = [c for c in cards if c["assistant_url"]]
    assert all("?q=" in c["assistant_url"] for c in with_q)


def test_hide_endpoint(v4):
    resp = views.next_step_hide(_req(v4, "post", {"karte": "verkauf"}))
    assert resp.status_code == 302
    assert "verkauf" in Tenant.objects.get(pk=v4.pk).site_config["next_steps"]["hidden"]


def test_publish_card_cannot_be_hidden_by_direct_post(v4):
    assert not next_steps.hide(v4, "publish")
    views.next_step_hide(_req(v4, "post", {"karte": "publish"}))
    assert "publish" in _keys(Tenant.objects.get(pk=v4.pk))


def test_product_checks_cost_one_query(v4, django_assert_max_num_queries):
    from apps.core import directions

    request = _req(v4)
    directions.active(v4)  # направления/модули — свои запросы, не карточек
    with django_assert_max_num_queries(6):
        next_steps.cards(request, limit=10)


def test_photo_card_only_for_goods_direction(v4, monkeypatch):
    from apps.core import directions

    monkeypatch.setattr(directions, "active", lambda t: [])
    assert "photos" not in _keys(v4) and "design" not in [
        c["key"] for c in next_steps.cards(_req(v4), limit=10)
    ]
