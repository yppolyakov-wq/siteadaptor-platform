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
    """Часть типов пока делит демо (online_shop/ритейл → shop); grocery — родной
    aktionsmarkt. Развод на dedicated-киты — по волнам плана demo-kits-per-type."""
    DomainFactory(domain="shop.siteadaptor.de", tenant=TenantFactory())
    DomainFactory(domain="aktionsmarkt.siteadaptor.de", tenant=TenantFactory(slug="am2"))
    cards = _cards()
    for bt in ("online_shop", "retail"):
        assert "shop.siteadaptor.de" in cards[bt]["demo_url"], bt
    assert "aktionsmarkt.siteadaptor.de" in cards["grocery"]["demo_url"]


def test_dedicated_demo_mapping_wave1():
    """Волна 1: у пекарни и мясной СВОИ демо (не общий рынок) — «чтоб лучше продать».
    Кит-поддомены: baeckerei (Backhaus Krume) и metzgerei (Metzgerei Bergmann)."""
    DomainFactory(domain="baeckerei.siteadaptor.de", tenant=TenantFactory())
    DomainFactory(domain="metzgerei.siteadaptor.de", tenant=TenantFactory(slug="mz2"))
    cards = _cards()
    assert "baeckerei.siteadaptor.de" in cards["bakery"]["demo_url"]
    assert "metzgerei.siteadaptor.de" in cards["butcher"]["demo_url"]
    # dedicated-киты зарегистрированы и совпадают с маппингом карточек
    from apps.tenants import demo_kits

    assert demo_kits.KITS["bakery"].subdomain == "baeckerei"
    assert demo_kits.KITS["butcher"].subdomain == "metzgerei"


def test_card_shape_has_demo_key():
    """Контракт карточки: у КАЖДОЙ карточки есть ключ demo_url (пусть и пустой)."""
    for c in onboarding.business_type_cards():
        assert "demo_url" in c


def test_dedicated_demo_mapping_wave2():
    """Волна 2: у кафе и моды свои демо — cafe (Café Morgenrot) и mode (Studio
    Nordwind); киты зарегистрированы и совпадают с маппингом карточек."""
    DomainFactory(domain="cafe.siteadaptor.de", tenant=TenantFactory())
    DomainFactory(domain="mode.siteadaptor.de", tenant=TenantFactory(slug="md2"))
    cards = _cards()
    assert "cafe.siteadaptor.de" in cards["cafe"]["demo_url"]
    assert "mode.siteadaptor.de" in cards["clothing"]["demo_url"]
    from apps.tenants import demo_kits

    assert demo_kits.KITS["cafe"].subdomain == "cafe"
    assert demo_kits.KITS["clothing"].subdomain == "mode"
