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
    """Ритейл смотрит на фермерский магазин, grocery — на рынок акций. Интернет-
    магазин с 2026-09-03 получил СВОЁ демо (см. следующий замок)."""
    DomainFactory(domain="shop.siteadaptor.de", tenant=TenantFactory())
    DomainFactory(domain="aktionsmarkt.siteadaptor.de", tenant=TenantFactory(slug="am2"))
    cards = _cards()
    assert "shop.siteadaptor.de" in cards["retail"]["demo_url"]
    assert "aktionsmarkt.siteadaptor.de" in cards["grocery"]["demo_url"]


def test_dedicated_online_shop_demo():
    """Волна online_shop: тип больше не делит витрину с лавкой — у него свой
    поддомен onlineshop (кит «Weitwerk»)."""
    DomainFactory(domain="onlineshop.siteadaptor.de", tenant=TenantFactory())
    cards = _cards()
    assert "onlineshop.siteadaptor.de" in cards["online_shop"]["demo_url"]


def test_outlet_is_the_second_online_shop_demo():
    """O-3/O-6: у типа ДВА демо разного жанра — бутик «Weitwerk» и аутлет
    «Zweitgut Outlet». Кнопка типа одна, поэтому её держит бутик, а аутлет
    доступен своим поддоменом и через реестр «функция → живое демо»
    (фильтры и B-Ware/UVP). Замок держит именно это разделение ролей."""
    from apps.tenants import demo_kits, feature_demos

    assert demo_kits.KITS["outlet"].subdomain == "outlet"
    assert demo_kits.KITS["outlet"].business_type == "online_shop"
    hosts = {item["host"] for item in feature_demos.FEATURE_DEMOS}
    assert "outlet" in hosts, "аутлет обязан быть достижим хотя бы из feature_demos"


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


def test_dedicated_demo_mapping_wave3():
    """Волна 3: у tour_operator своё демо (touren, Stadtgold) — не retreat."""
    DomainFactory(domain="touren.siteadaptor.de", tenant=TenantFactory())
    cards = _cards()
    assert "touren.siteadaptor.de" in cards["tour_operator"]["demo_url"]
    from apps.tenants import demo_kits

    assert demo_kits.KITS["tours"].subdomain == "touren"
