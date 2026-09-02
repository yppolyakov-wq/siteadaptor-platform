"""DL-16.3 — деталь акции: AD1 «Gilt für», AD2 «Bedingungen», AD3 «Weitere Aktionen»."""

from __future__ import annotations

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views, rules_text
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _get(pk, tenant):
    request = RequestFactory().get(f"/p/{pk}/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.promotion_detail(request, pk).content.decode()


def test_weekday_span_compresses_ranges():
    assert rules_text.weekday_span([0, 1, 2]) == "Mo–Mi"
    assert rules_text.weekday_span([0, 1, 2, 4]) == "Mo–Mi, Fr"
    assert rules_text.weekday_span([0, 1]) == "Mo, Di"
    assert rules_text.weekday_span([5, 6]) == "Sa, So"
    assert rules_text.weekday_span(list(range(7))) == "täglich"
    assert rules_text.weekday_span([]) == "" and rules_text.weekday_span("x") == ""


def test_conditions_only_promise_what_is_enforced():
    p = Promotion(
        promo_type="discount", target_rules={"weekdays": [0, 1, 2], "hour_from": 10, "hour_to": 14}
    )
    texts = [c["text"] for c in rules_text.conditions_for(p)]
    assert texts == ["Mo–Mi 10–14 Uhr"]
    # discount-акция: лимит на клиента на пути корзины не действует → не обещаем
    assert not [
        c
        for c in rules_text.conditions_for(Promotion(promo_type="discount", max_per_customer=2))
        if "Kunde" in c["text"]
    ]
    r = Promotion(promo_type="reservation", max_per_customer=2, reservation_ttl_hours=12)
    texts = [c["text"] for c in rules_text.conditions_for(r)]
    assert texts == ["max. 2 pro Kunde", "Reservierung 12 h gültig"]


def test_detail_shows_target_card_conditions_and_related_strip():
    tenant = TenantFactory(schema_name="public", slug="dl163a", name="A", disabled_modules=[])
    prod = ProductFactory(name={"de": "Orangensaft 1 L"}, base_price="2.49")
    main = Promotion.objects.create(
        title={"de": "OJ"},
        status="active",
        group="Wochenangebote",
        product=prod,
        discount_percent=20,
        target_rules={"weekdays": [0, 1, 2], "hour_from": 10, "hour_to": 14},
    )
    for i in range(3):
        Promotion.objects.create(title={"de": f"W{i}"}, status="active", group="Wochenangebote")
    Promotion.objects.create(title={"de": "R"}, status="active", group="Räumung")
    html = _get(main.pk, tenant)
    assert (
        "data-promo-target" in html
        and "Orangensaft 1 L" in html
        and prod.get_absolute_url() in html
    )
    assert "data-promo-conditions" in html and "Mo–Mi 10–14 Uhr" in html
    assert "data-promo-related" in html
    rel = html[html.index("data-promo-related") :]
    # маркер — заголовок карточки (голое "W2" ловил случайный CSRF-токен — класс MEN)
    assert sum(rel.count(f">W{i}</h3>") for i in range(3)) == 3 and ">R</h3>" not in rel
    assert "OJ</h3>" not in rel  # себя не показываем
    assert "data-sf-slider" in rel


def test_detail_related_fallback_and_mystery_hides_target():
    tenant = TenantFactory(schema_name="public", slug="dl163b", name="B", disabled_modules=[])
    prod = ProductFactory(name={"de": "Geheim"}, base_price="9.00")
    mys = Promotion.objects.create(
        title={"de": "Mystery"},
        status="active",
        group="Solo",
        product=prod,
        discount_style="mystery",
        discount_percent=50,
        compare_at_price="9.00",
    )
    Promotion.objects.create(title={"de": "Andere"}, status="active", group="Woche")
    Promotion.objects.create(title={"de": "Noch eine"}, status="active")
    html = _get(mys.pk, tenant)
    assert "data-promo-target" not in html and "Geheim" not in html
    rel = html[html.index("data-promo-related") :]
    assert "Andere" in rel and "Noch eine" in rel  # своей группы <2 → прочие активные
    lonely = Promotion.objects.create(title={"de": "Einzig"}, status="active")
    Promotion.objects.exclude(pk=lonely.pk).delete()
    assert "data-promo-related" not in _get(lonely.pk, tenant)
