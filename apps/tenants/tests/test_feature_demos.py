"""Решение владельца 2026-08-01: на `/branchen/` — отдельный блок «примеры по
функциям» (демо подписаны видами бизнеса, и «сайт с акциями» по названию не
находился, хотя он есть).
"""

import pytest

from apps.tenants import feature_demos

pytestmark = pytest.mark.django_db


def test_cards_are_empty_without_seeded_demos(monkeypatch):
    """Демо не прогнаны → блок не рендерится (мёртвых ссылок не показываем)."""
    monkeypatch.setattr("apps.tenants.onboarding._seeded_demo_hosts", lambda: set())
    assert feature_demos.feature_demo_cards() == []


def test_cards_only_for_seeded_hosts(monkeypatch, settings):
    """Показываем ровно те функции, чьё демо реально засеяно."""
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    monkeypatch.setattr(
        "apps.tenants.onboarding._seeded_demo_hosts",
        lambda: {"aktionsmarkt.siteadaptor.de", "hotel.siteadaptor.de"},
    )
    cards = feature_demos.feature_demo_cards()
    assert {c["key"] for c in cards} == {"promotions", "stays"}
    promo = next(c for c in cards if c["key"] == "promotions")
    # Ссылка ведёт СРАЗУ на нужный экран демо, а не на главную.
    assert promo["url"] == "https://aktionsmarkt.siteadaptor.de/aktionen/"
    assert promo["title"] and promo["blurb"]


def test_every_entry_points_at_a_known_demo_kit():
    """Опечатка в поддомене = вечно скрытая карточка; сверяем с реестром демо."""
    from apps.tenants.demo_kits import KITS

    subdomains = {k.subdomain or f"{k.key}-demo" for k in KITS.values()}
    for item in feature_demos.FEATURE_DEMOS:
        assert item["host"] in subdomains, item["key"]
        assert item["path"].startswith("/") and item["path"].endswith("/")
