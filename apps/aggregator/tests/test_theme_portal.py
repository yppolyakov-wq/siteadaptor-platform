"""T-8.14: тематический портал — охват портала одной точкой (`portal_scope`).

План — docs/t8-14-28-themed-portal-bot-plan-2026-10-20.md. Главный замок: листинг вне
темы не появляется НИ НА ОДНОЙ поверхности портала.
"""

import ast
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import override_settings
from django.utils import timezone

from apps.aggregator import llms, portal_scope, portal_views, views
from apps.aggregator.models import AggregatorListing, FollowSubscription, PortalUser
from apps.aggregator.tests.test_machine_readable import _get, _listing, _portal
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

THEME = {"theme_tags": ["vegan", "bio"]}


@pytest.fixture(autouse=True)
def _clear(isolated_ratelimit):
    cache.clear()
    yield
    cache.clear()


def _pair():
    """Одно предложение в теме (vegan), одно вне её (без признаков)."""
    inside = _listing(
        tenant_schema="veg",
        tenant_slug="veg",
        business_name="Grüne Küche",
        title={"de": "Vegane Bowl"},
        city_tags=["vegan"],
        detail_url="https://veg.siteadaptor.de/p/1/",
    )
    outside = _listing(
        tenant_schema="mett",
        tenant_slug="mett",
        business_name="Mett-Eck",
        title={"de": "Mettbrötchen"},
        city_tags=[],
        detail_url="https://mett.siteadaptor.de/p/1/",
    )
    return inside, outside


def _theme_portal(**kw):
    return _portal(kind="theme", **{**THEME, **kw})


# --- A1: одна точка входа ---------------------------------------------------------


def test_portal_scope_single_entry():
    """Охват портала больше не передаётся в `listings_for(...)` руками: только
    `portal_scope` знает, как портал сужает пул (иначе тема где-то протечёт)."""
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts or path.name == "portal_scope.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "listings_for"):
                continue
            for kw in node.keywords:
                src = ast.unparse(kw.value)
                if kw.arg in ("city", "business_type", "include_demo") and "portal" in src:
                    offenders.append(f"{path.name}:{node.lineno} {kw.arg}={src}")
    assert not offenders, offenders


def test_empty_theme_is_noop():
    inside, outside = _pair()
    portal = _portal()
    pks = set(portal_scope.pool(portal).values_list("pk", flat=True))
    assert pks == set(views.listings_for(city="Solingen").values_list("pk", flat=True))
    assert {inside.pk, outside.pk} <= pks


def test_theme_is_any_of_tags():
    inside, outside = _pair()
    bio = _listing(tenant_schema="bio", tenant_slug="bio", city_tags=["bio"])
    pks = set(portal_scope.pool(_theme_portal()).values_list("pk", flat=True))
    assert pks == {inside.pk, bio.pk}
    assert outside.pk not in pks


def test_theme_categories_and_tags_are_anded():
    inside, _outside = _pair()
    wrong_cat = _listing(
        tenant_schema="kl", tenant_slug="kl", city_tags=["vegan"], city_category="kleidung"
    )
    portal = _theme_portal(theme_categories=["lebensmittel-getraenke"])
    pks = set(portal_scope.pool(portal).values_list("pk", flat=True))
    assert inside.pk in pks and wrong_cat.pk not in pks


def test_theme_business_card_via_offer():
    """Карточка компании без признаков входит в тему, если у бизнеса есть предложение в теме."""
    _pair()
    veg_card = _listing(
        tenant_schema="veg", tenant_slug="veg", listing_kind="business", city_tags=[]
    )
    mett_card = _listing(
        tenant_schema="mett", tenant_slug="mett", listing_kind="business", city_tags=[]
    )
    pks = set(portal_scope.pool(_theme_portal()).values_list("pk", flat=True))
    assert veg_card.pk in pks and mett_card.pk not in pks


def test_theme_merkmal_intersects():
    """Явный `?merkmal=` вне темы даёт пустую выдачу, а не выход за тему."""
    _inside, outside = _pair()
    _listing(tenant_schema="hund", tenant_slug="hund", city_tags=["hundefreundlich"])
    pks = set(
        portal_scope.pool(_theme_portal(), city_tag="hundefreundlich").values_list("pk", flat=True)
    )
    assert pks == set()
    assert outside.pk not in pks


def test_clean_rejects_unknown_keys_and_normalizes():
    portal = _theme_portal()
    portal.theme_tags = ["vegan", "vegan", "quatsch"]
    with pytest.raises(ValidationError):
        portal.clean()
    portal.theme_tags = ["vegan", "vegan"]
    portal.theme_categories = ["gibts-nicht"]
    with pytest.raises(ValidationError):
        portal.clean()
    portal.theme_categories = ["lebensmittel-getraenke"]
    portal.clean()
    assert portal.theme_tags == ["vegan"]


def test_fingerprint_changes_with_theme():
    portal = _portal()
    before = portal_scope.fingerprint(portal)
    portal.theme_tags = ["vegan"]
    assert portal_scope.fingerprint(portal) != before


# --- главный замок: тема не протекает ни на одну поверхность ---------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_theme_portal_no_leak_on_html_surfaces():
    inside, outside = _pair()
    portal = _theme_portal()
    pages = {
        "home": portal_views.portal_home(_get("/", portal)),
        "list": portal_views.portal_home(_get("/?kind=alle", portal)),
    }
    for name, resp in pages.items():
        body = resp.content.decode()
        assert resp.status_code == 200, name
        assert "Vegane Bowl" in body, name
        assert "Mettbrötchen" not in body, name


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_theme_portal_no_leak_in_feed_llms_sitemap():
    _pair()
    portal = _theme_portal()
    feed = json.loads(portal_views.portal_feed_json(_get("/feed.json", portal)).content)
    titles = [it["title"] for it in feed["items"]]
    assert any("Vegane Bowl" in t for t in titles)
    assert not any("Mett" in t for t in titles)
    text = llms.build_portal(_get("/llms.txt", portal), portal)
    assert "Mett-Eck" not in text
    sitemap = portal_views.portal_sitemap_xml(_get("/sitemap.xml", portal)).content.decode()
    assert "/unternehmen/mett/" not in sitemap


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_theme_portal_offer_and_business_pages_404_outside():
    inside, outside = _pair()
    portal = _theme_portal()
    assert portal_scope.contains(inside, portal)
    assert not portal_scope.contains(outside, portal)
    with pytest.raises(Http404):
        views.offer_page(_get(f"/angebot/{outside.pk}/", portal), outside.pk)
    veg = TenantFactory(schema_name="veg", slug="veg", city="Solingen")
    mett = TenantFactory(schema_name="mett", slug="mett", city="Solingen")
    assert portal_scope.contains_tenant(veg, portal)
    assert not portal_scope.contains_tenant(mett, portal)


@override_settings(ROOT_URLCONF="config.urls_portal", MCP_ENABLED=True, MCP_PORTAL_HOSTS=[])
def test_theme_portal_no_leak_in_mcp():
    from apps.aggregator.tests.test_mcp_tools import _data

    _pair()
    data = _data(_theme_portal(), "search_offers", {})
    titles = [it["title"] for it in data["items"]]
    assert "Vegane Bowl" in titles and "Mettbrötchen" not in titles


def test_digest_subset_of_scope():
    """Сводка тематического портала ⊆ его выдачи (иначе «Alle anzeigen» показало бы
    меньше письма) — и раздел подписки не выходит за тему."""
    inside, outside = _pair()
    portal = _theme_portal()
    user = PortalUser.objects.create(email="a@example.com")
    sub = FollowSubscription.objects.create(
        user=user,
        portal=portal,
        city="Solingen",
        target_kind=FollowSubscription.TARGET_SECTION,
        target_key="lebensmittel-getraenke",
        confirmed_at=timezone.now(),
    )
    from apps.aggregator import follow

    since = timezone.now() - timedelta(days=1)
    pks = set(follow.items_for(sub, since=since).values_list("pk", flat=True))
    assert inside.pk in pks and outside.pk not in pks


def test_liveness_cache_key_per_theme():
    from apps.aggregator import district_liveness

    plain = _portal()
    themed = _portal(host="gesund.siteadaptor.de", **THEME)
    assert district_liveness._cache_key(plain) != district_liveness._cache_key(themed)


def test_theme_portal_has_home():
    from apps.aggregator import portal_home_blocks as home

    assert home.has_home(_theme_portal())
    assert AggregatorListing.KIND_BUSINESS == "business"


# --- A4: демо тематического портала ------------------------------------------------


def test_demo_theme_portal_not_empty():
    """Демо Золингена даёт теме «gesund» больше 10 предложений у больше чем 3 бизнесов
    (иначе превью-портал выглядел бы пустым)."""
    from apps.tenants.demo_city import solingen
    from apps.tenants.management.commands.seed_demo_tenants import THEME_PORTAL_TAGS

    theme = set(THEME_PORTAL_TAGS)
    offers, businesses = 0, set()
    for biz in solingen.BUSINESSES:
        for offer in biz.offers or ():
            if theme & set(offer.tags):
                offers += 1
                businesses.add(biz.key)
    assert offers > 10 and len(businesses) > 3


def test_ensure_theme_portal_is_idempotent(settings):
    from django.core.management.base import OutputWrapper

    from apps.aggregator.models import AggregatorPortal
    from apps.tenants.management.commands.seed_demo_tenants import Command
    from apps.tenants.models import Domain

    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    TenantFactory(schema_name="public", slug="public-x")
    cmd = Command()
    cmd.stdout = OutputWrapper(open("/dev/null", "w"))  # noqa: SIM115
    cmd._ensure_theme_portal("Solingen")
    cmd._ensure_theme_portal("Solingen")
    portal = AggregatorPortal.objects.get(host="gesund-solingen.siteadaptor.de")
    assert portal.kind == "theme" and portal.show_demo
    assert portal.theme_tags == ["vegan", "vegetarisch", "bio", "regional"]
    assert Domain.objects.filter(domain=portal.host).count() == 1


# --- правки ревью ------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_lists_only_theme_offers():
    """Компания с одним веганским предложением видна на тематическом портале, но её
    прочие предложения там не показываются (раньше страница выводила всё)."""
    from apps.aggregator import reviews_views

    _listing(
        tenant_schema="veg", tenant_slug="veg", title={"de": "Vegane Bowl"}, city_tags=["vegan"]
    )
    _listing(tenant_schema="veg", tenant_slug="veg", title={"de": "Schnitzel"}, city_tags=[])
    TenantFactory(schema_name="veg", slug="veg", city="Solingen")
    portal = _theme_portal()
    titles = [
        str(it.title_text)
        for it in reviews_views._business_listings(_get("/unternehmen/veg/", portal), "veg")
    ]
    assert "Vegane Bowl" in titles and "Schnitzel" not in titles


def test_business_card_survives_search_filter():
    """Карточка компании входит в тему по её предложениям, а не по совпадению с поиском."""
    _listing(
        tenant_schema="veg", tenant_slug="veg", title={"de": "Vegane Bowl"}, city_tags=["vegan"]
    )
    card = _listing(
        tenant_schema="veg",
        tenant_slug="veg",
        listing_kind="business",
        business_name="Grüne Küche",
        city_tags=[],
    )
    pks = set(portal_scope.pool(_theme_portal(), kinds=("business",)).values_list("pk", flat=True))
    assert card.pk in pks
    assert portal_scope.contains(card, _theme_portal(host="g2.siteadaptor.de"))


def test_non_theme_portal_pool_is_plain_listings_for():
    _pair()
    portal = _portal()
    got = set(portal_scope.pool(portal, kinds=("promotion",)).values_list("pk", flat=True))
    want = set(
        views.listings_for(city="Solingen", kinds=("promotion",), include_demo=False).values_list(
            "pk", flat=True
        )
    )
    assert got == want and len(got) == 2


def test_garbage_theme_values_do_not_crash():
    portal = _portal()
    portal.theme_tags = 5
    portal.theme_categories = "x"
    assert not portal_scope.has_theme(portal)
    assert list(portal_scope.pool(portal)) is not None


@pytest.mark.parametrize("slug", ["solingen", "gesund-solingen"])
def test_portal_subdomains_are_reserved(slug, settings):
    from apps.tenants import signup
    from apps.tenants.forms import BusinessSignupForm

    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    assert signup.slug_taken(slug)
    form = BusinessSignupForm(data={"slug": slug})
    form.is_valid()
    assert "slug" in form.errors
