"""#3/#5 (фидбэк владельца): кнопки «Demo ansehen» на карточках типов бизнеса →
живая демо-витрина архетипа. demo_url заполняется ТОЛЬКО для засеянных демо (есть
Domain) — чтобы не показывать мёртвые ссылки, если seed_demo_tenants не прогнан."""

import pytest

from apps.tenants import onboarding
from apps.tenants.tests.factories import DomainFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _cards():
    return {c["value"]: c for c in onboarding.business_type_cards()}


def test_no_demo_url_when_not_seeded():
    """Без засеянного демо-поддомена — demo_url пуст (нет мёртвых ссылок)."""
    assert _cards()["friseur"]["demo_url"] == ""


def test_demo_url_when_seeded():
    """Есть Domain friseur.<base> → карточка friseur получает ссылку на демо-витрину;
    незасеянный тип (hotel) — пусто."""
    DomainFactory(domain="friseur.siteadaptor.de", tenant=TenantFactory())
    cards = _cards()
    assert "friseur.siteadaptor.de" in cards["friseur"]["demo_url"]
    assert cards["friseur"]["demo_url"].startswith(("http://", "https://"))
    assert cards["friseur"]["demo_url"].endswith("/")
    assert cards["hotel"]["demo_url"] == ""  # демо hotel не засеян


def test_shared_demo_mapping():
    """Несколько типов делят один демо (пекарня/мясная/продукты → рынок aktionsmarkt)."""
    DomainFactory(domain="aktionsmarkt.siteadaptor.de", tenant=TenantFactory())
    cards = _cards()
    for bt in ("bakery", "butcher", "grocery"):
        assert "aktionsmarkt.siteadaptor.de" in cards[bt]["demo_url"], bt


def test_card_shape_has_demo_key():
    """Контракт карточки: у КАЖДОЙ карточки есть ключ demo_url (пусть и пустой)."""
    for c in onboarding.business_type_cards():
        assert "demo_url" in c
