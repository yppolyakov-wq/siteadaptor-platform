"""PH-13f/g: страница предложения по макету M8 — факты «нет данных → нет строки», карточка
«So finden Sie uns» из публичных полей бизнеса, на телефоне — закреплённая панель покупки
вместо нижнего меню. План — docs/ph13-portal-mobile-plan-2026-11-08.md §3."""

import re

import pytest
from django.test import override_settings

from apps.aggregator import offer_facts, views
from apps.aggregator.tests.test_offer_page import _get, _listing, _portal
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_facts_come_only_from_data():
    rich = _listing(action="reserve", remaining=3)
    labels = [f["value"] for f in offer_facts.facts(rich)]
    assert any("Zurücklegen" in v for v in labels)
    assert any("Vor Ort" in str(v) for v in labels)
    assert any("3" in str(v) for v in labels)
    bare = _listing(action="", remaining=None, tenant_schema="t9")
    assert offer_facts.facts(bare) == []


def test_buy_or_show_has_no_payment_fact():
    for action in ("buy", "show", "booking"):
        facts = offer_facts.facts(_listing(action=action, tenant_schema=f"x{action}"))
        assert not any(f["key"] == "payment" for f in facts), action


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_card_only_with_address_or_phone():
    portal = _portal()
    TenantFactory(schema_name="t1", slug="baeckerei", address="Hauptstr. 1, 42651 Solingen")
    html = views.offer_page(_get(portal=portal), _listing().pk).content.decode()
    card = re.search(r"<section[^>]*data-offer-business.*?</section>", html, re.S)
    assert card and "Hauptstr. 1" in card.group(0)
    TenantFactory(schema_name="t2", slug="leer")
    html = views.offer_page(
        _get(portal=portal), _listing(tenant_schema="t2", tenant_slug="leer").pk
    ).content.decode()
    assert "data-offer-business" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_one_cta_in_a_sticky_phone_bar_and_no_bottom_nav():
    portal = _portal()
    html = views.offer_page(_get(portal=portal), _listing().pk).content.decode()
    assert html.count("data-offer-cta") == 1
    bar = re.search(r"<div[^>]*data-offer-buybar[^>]*>", html).group(0)
    assert "max-md:fixed" in bar and "max-md:bottom-0" in bar
    assert "data-portal-bottom-nav" not in html  # панель покупки вместо меню
    assert "inkl. MwSt" not in html  # признака НДС у листинга нет — не выдумываем
