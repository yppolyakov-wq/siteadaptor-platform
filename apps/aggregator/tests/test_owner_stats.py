"""В5 V5-3 (план docs/v5-portal-analytics-plan-2026-10-17.md §16): экран владельца
«Besuche aus dem Stadtportal». Замки написаны ДО кода."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.aggregator import owner_stats
from apps.aggregator.models import AggregatorListing, PortalStat
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    o = uuid4().hex[:8]
    kw.setdefault("slug", f"t{o}")
    kw.setdefault("name", "Bäckerei")
    kw.setdefault("schema_name", f"t_{o}")
    return TenantFactory(**kw)


def _stat(tenant, action="view", n=1, day=TODAY, kind="promotion", ref="p1", listing_id=None):
    schema = tenant if isinstance(tenant, str) else tenant.schema_name
    return PortalStat.objects.create(
        day=day,
        tenant_schema=schema,
        listing_kind=kind,
        source_ref=ref,
        listing_id=listing_id,
        action=action,
        channel="portal",
        count=n,
    )


def _listing(tenant, **kw):
    defaults = {
        "tenant_schema": tenant.schema_name,
        "tenant_slug": tenant.slug,
        "business_name": tenant.name,
        "business_type": "bakery",
        "city": "Solingen",
        "listing_kind": "promotion",
        "source_ref": "p1",
        "title": {"de": "Brotkorb"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _req(tenant, user=True, **params):
    req = RequestFactory().get("/dashboard/stadtportal/", params)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    if user:
        from apps.core.models import Membership

        o = uuid4().hex[:8]
        req.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        Membership.objects.create(user=req.user, role=Membership.ROLE_OWNER)
    else:
        req.user = AnonymousUser()
    req.tenant = tenant
    return req


def _page(tenant, **params):
    from apps.aggregator.owner_views import portal_stats

    return portal_stats(_req(tenant, **params)).content.decode()


def _funnel(summary):
    return {f["code"]: f for f in summary["funnel"]}


# --- 14: только своя схема ---------------------------------------------------------


def test_only_own_schema_is_counted(monkeypatch):
    monkeypatch.setattr(owner_stats.timezone, "localdate", lambda: TODAY)
    t = _tenant()
    _stat(t, n=3)
    _stat("other_schema", n=100)
    assert _funnel(owner_stats.summary(t, 30, today=TODAY))["view"]["value"] == 3
    html = _page(t, schema="other_schema")
    assert ">100<" not in html and "data-funnel-view" in html


def test_public_schema_tenant_gets_empty():
    t = _tenant(schema_name="public")
    _stat("public", n=5)
    s = owner_stats.summary(t, 30, today=TODAY)
    assert s["has_data"] is False and _funnel(s)["view"]["value"] == 0


# --- 15: доступ -----------------------------------------------------------------


def test_anonymous_redirects_to_login():
    from apps.aggregator.owner_views import portal_stats

    resp = portal_stats(_req(_tenant(), user=False))
    assert resp.status_code == 302 and "login" in resp["Location"]


# --- 16: воронка, период, график, топ, featured ------------------------------------


def test_funnel_values_and_honesty_texts(monkeypatch):
    monkeypatch.setattr(owner_stats.timezone, "localdate", lambda: TODAY)
    t = _tenant()
    _stat(t, "impression", 9)
    _stat(t, "view", 5)
    _stat(t, "click", 2)
    _stat(t, "contact", 1)
    s = owner_stats.summary(t, 30, today=TODAY)
    assert [f["code"] for f in s["funnel"]] == list(PortalStat.ACTIONS_CODES)
    f = _funnel(s)
    assert f["view"]["value"] == 5 and f["click"]["value"] == 2
    # V5-4: показы считаются (осознанная переписка замка V5-3)
    assert f["impression"]["tracked"] is True and f["impression"]["value"] == 9
    # V5-5b: обращения и сделки считаются (осознанная переписка замка V5-4)
    assert f["contact"]["tracked"] is True and f["contact"]["value"] == 1
    assert f["deal"]["tracked"] is True and f["deal"]["value"] == 0
    html = _page(t)
    assert "Ein Klick ist kein Verkauf." in html
    assert "Besuche von Suchmaschinen und Bots zählen wir nicht." in html
    assert "im selben Besuch" in html
    assert "Wird bald gezählt" not in html and "data-untracked" not in html
    assert "jede Anfrage und Bestellung zählt einzeln" in html
    assert "mindestens 1 Sekunde zur Hälfte zu sehen" in html  # определение показа


def test_period_whitelist():
    assert owner_stats.parse_period("90") == 90
    for raw in ("8", "abc", None, "-30", "999999999999", ""):
        assert owner_stats.parse_period(raw) == 30
    html = _page(_tenant(), tage="7")
    assert 'href="?tage=7" aria-current="page"' in html


def test_period_window_and_comparison():
    t = _tenant()
    _stat(t, n=10, day=date(2026, 10, 11))  # текущий период (7 дней)
    _stat(t, n=5, day=date(2026, 10, 10))  # предыдущий
    _stat(t, n=99, day=date(2026, 10, 3))  # вне обоих
    f = _funnel(owner_stats.summary(t, 7, today=TODAY))
    assert f["view"]["value"] == 10
    assert f["view"]["hint"].startswith("▲ 100")
    t2 = _tenant()
    _stat(t2, n=3)
    assert _funnel(owner_stats.summary(t2, 7, today=TODAY))["view"]["hint"] == "neu vs. Vorperiode"
    assert _funnel(owner_stats.summary(t2, 7, today=TODAY))["click"]["hint"] == ""


def test_sparkline_points():
    t = _tenant()
    _stat(t, n=2)
    assert len(owner_stats.summary(t, 7, today=TODAY)["sparkline"].split()) == 7
    _stat(t, n=1, day=TODAY - timedelta(days=6))
    spark = owner_stats.summary(t, 365, today=TODAY)["sparkline"].split()
    assert len(spark) == 52  # недели от сегодня назад, без обрубка
    assert spark[-1].split(",")[1] == "2.0"  # последняя неделя — максимум (3 визита), не пусто


def test_top_offers_titles_and_fallback():
    t = _tenant()
    _listing(t, source_ref="p1", title={"de": "Brot"})
    _stat(t, "view", 4, ref="p1", listing_id=999)  # старый pk: заголовок — по ключу
    _stat(t, "view", 1, ref="gone")
    _stat(t, "view", 2, kind="business", ref="business")
    top = owner_stats.summary(t, 30, today=TODAY)["top"]
    titles = [row["title"] for row in top]
    assert titles[0] == "Brot"
    assert "(nicht mehr im Stadtportal)" in titles
    assert "Ihr Unternehmensprofil" in titles
    assert top[0]["values"]["view"] == 4
    for i in range(12):
        _stat(t, "view", 1, ref=f"x{i}")
    assert len(owner_stats.summary(t, 30, today=TODAY)["top"]) == 10


def test_featured_row_separate():
    t = _tenant()
    _listing(t, featured_impressions=7, featured_clicks=2)
    s = owner_stats.summary(t, 30, today=TODAY)
    assert s["featured"] == (7, 2)
    assert _funnel(s)["view"]["value"] == 0
    html = _page(t)
    assert "7 · 2" in html and "seit Beginn der Anzeige" in html
    assert owner_stats.summary(_tenant(), 30, today=TODAY)["featured"] is None


def test_query_budget(django_assert_max_num_queries):
    t = _tenant()
    for i in range(10):
        _listing(t, source_ref=f"p{i}")
        _stat(t, "view", i + 1, ref=f"p{i}")
    with django_assert_max_num_queries(4):
        owner_stats.summary(t, 30, today=TODAY)


# --- 17: пустые состояния и демо --------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "needle"),
    [
        ({"in_city_catalog": False}, "Ihr Angebot ist nicht im Stadtkatalog"),
        ({"email_pending": True}, "data-email-pending"),
        ({"is_active": False}, "derzeit nicht im Stadtportal sichtbar"),
        ({"is_internal": True}, "derzeit nicht im Stadtportal sichtbar"),
        ({}, "Noch keine Besuche"),
    ],
)
def test_empty_states(fields, needle):
    html = _page(_tenant(**fields))
    assert needle in html
    if fields.get("in_city_catalog") is False:
        assert f'href="{reverse("settings")}#sec-kontakt"' in html


def test_demo_plate():
    assert "Demo-Daten" in _page(_tenant(is_demo=True))
    assert "Demo-Daten" not in _page(_tenant())


# --- 18: навигация -------------------------------------------------------------


def test_nav_entry_under_marketing_after_reviews():
    from apps.core import nav_registry

    entry = nav_registry.entry_for("marketing", "portal-stats")
    assert entry is not None and entry.module_key is None and not entry.palette_only
    assert nav_registry.anchor_for("portal-stats") == nav_registry.anchor_for("reviews")
    anchor = next(a for a in nav_registry.ANCHORS if "marketing" in a.hubs)
    names = [e.url_name for e in nav_registry.sidebar_children(anchor)]
    assert names.index("portal-stats") == names.index("reviews:list") + 1
    assert any(p.get("url_name") == "portal-stats" for p in nav_registry.palette_entries())


def test_top_ordering_ignores_impression_only_rows_and_merges_business():
    """Ревью V5-3: строка «только показы» не обгоняет открытые предложения (NULL на
    DESC в Postgres — первый); профиль компании и «бизнес целиком» — одна строка."""
    t = _tenant()
    _stat(t, "impression", 500, ref="seen-only")
    _listing(t, source_ref="opened", title={"de": "Geöffnet"})
    _stat(t, "view", 1, ref="opened")
    _stat(t, "view", 2, kind="business", ref="business")
    _stat(t, "view", 1, kind="", ref="")
    top = owner_stats.summary(t, 30, today=TODAY)["top"]
    titles = [row["title"] for row in top]
    assert titles[0] == "Ihr Unternehmensprofil" and top[0]["values"]["view"] == 3
    assert titles.count("Ihr Unternehmensprofil") == 1
    assert titles[1] == "Geöffnet"  # открытое раньше «только показов»
    assert titles[2] == "(nicht mehr im Stadtportal)"


# --- решения владельца после V5-3: только владельцу + вход с экрана «Fertig» -----


def _member(role):
    from apps.core.models import Membership

    o = uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"m-{o}@t.de", email=f"m-{o}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def test_screen_is_owner_only():

    from apps.core.models import Membership
    from apps.core.tests.gates import ok, open_as

    t = _tenant()
    for role, status in ((Membership.ROLE_STAFF, 403), (Membership.ROLE_OWNER, 200)):
        req = _req(t)
        req.user = _member(role)
        assert open_as(req, ok).status_code == status, role
    from apps.core import nav_registry

    staff = _member(Membership.ROLE_STAFF)  # E6.7e: скрытие из прав (stadtportal.view)
    assert "portal-stats" in nav_registry.hidden_for(staff)


def test_marketing_metric_only_for_owner():
    from apps.core import marketing_home as mh

    t = _tenant()
    from django.utils import timezone

    _stat(t, "view", 2, day=timezone.localdate())
    labels = [str(m["label"]) for m in mh.results_panel(t, owner=True)]
    assert any("Stadtportal" in lbl for lbl in labels)
    labels = [str(m["label"]) for m in mh.results_panel(t, owner=False)]
    assert not any("Stadtportal" in lbl for lbl in labels)


def test_quick_done_links_portal_stats_for_owner_only():
    from apps.core.models import Membership
    from apps.promotions.models import Promotion
    from apps.promotions.views import promotion_quick_done

    t = _tenant()
    promo = Promotion.objects.create(status="active", title={"de": "Brot"})
    for role, shown in ((Membership.ROLE_OWNER, True), (Membership.ROLE_STAFF, False)):
        req = _req(t)
        req.user = _member(role)
        html = promotion_quick_done(req, promo.pk).content.decode()
        assert ('href="/dashboard/stadtportal/"' in html) is shown, role


def test_view_itself_refuses_non_owner():
    """Ревью V5-4: защита в глубину — вьюха сама отказывает не-владельцу, даже мимо middleware."""
    from apps.aggregator.owner_views import portal_stats
    from apps.core.models import Membership

    t = _tenant()
    for role, status in (
        (Membership.ROLE_ADMIN, 403),
        (Membership.ROLE_STAFF, 403),
        (Membership.ROLE_OWNER, 200),
    ):
        req = _req(t)
        req.user = _member(role)
        assert portal_stats(req).status_code == status, role
