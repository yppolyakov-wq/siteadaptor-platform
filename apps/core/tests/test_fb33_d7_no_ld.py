"""FB-33 D7: без JSON-LD на выдаче поиска `?q=` листингов и на превью подтверждения.

План — `docs/fb33-stack13-plan-2026-11-24.md` §1 D7, §2 D7, §4 D7. Признак один —
`storefront_search_noindex` (M5a-2, `core/context.py`); второго не заводим. Запросы — с настоящим
`resolver_match` (как `test_fb33_m5a2_cache_search.py`), превью — с настоящим членством команды,
без подмены `_may_preview` (roadmap «FB-33 — отложено», 8.3).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.core.context import SEARCH_NOINDEX_ROUTES
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

rf = RequestFactory()
LD = '<script type="application/ld+json">'


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("business_type", "bakery")
    kw.setdefault("enabled_locales", ["de", "en"])
    return TenantFactory(disabled_modules=[], **kw)


def _req(tenant, path, *, data=None, user=None):
    req = rf.get(path, data or {}, HTTP_HOST=f"{uuid.uuid4().hex}.test")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or AnonymousUser()
    req.portal = None
    req.tenant = tenant
    req.LANGUAGE_CODE = "de"
    return req


def _get(tenant, path, data=None, *, user=None):
    req = _req(tenant, path, data=data, user=user)
    match = resolve(path)
    req.resolver_match = match
    resp = match.func(req, *match.args, **match.kwargs)
    if hasattr(resp, "render"):
        resp = resp.render()
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.content.decode()


def _path(route):
    if route != "storefront-category":
        return reverse(route)
    from apps.catalog.tests.factories import CategoryFactory

    slug = f"kat{uuid.uuid4().hex[:6]}"
    CategoryFactory(slug=slug, name={"de": "Kategorie D7"})
    return reverse(route, kwargs={"slug": slug})


@pytest.mark.parametrize("route", sorted(SEARCH_NOINDEX_ROUTES))
def test_no_ld_on_search(route):
    """№5: выдача `?q=` (вне индекса) не несёт LocalBusiness и BreadcrumbList."""
    html = _get(_tenant(), _path(route), {"q": "brot"})
    assert '<meta name="robots" content="noindex,follow">' in html  # признак сработал
    assert LD not in html


@pytest.mark.parametrize("route", sorted(SEARCH_NOINDEX_ROUTES))
@pytest.mark.parametrize(
    "params", [{}, {"q": " "}, {"sort": "name"}], ids=["plain", "space", "sort"]
)
def test_ld_kept_without_q(route, params):
    """Охранный: без поиска LocalBusiness на месте (вывод прежний)."""
    html = _get(_tenant(), _path(route), params)
    assert LD + '{"@context":"https://schema.org","@type":"Bakery"' in html


def test_category_breadcrumb_ld_kept_without_q():
    html = _get(_tenant(), _path("storefront-category"))
    assert '"BreadcrumbList"' in html


def test_category_breadcrumb_ld_dropped_on_search():
    html = _get(_tenant(), _path("storefront-category"), {"q": "brot"})
    assert "BreadcrumbList" not in html


def _member(tenant):
    from apps.core.models import Membership

    user = get_user_model().objects.create_user(
        username=f"d7-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


def test_confirmation_preview_has_no_ld():
    """Превью подтверждения (только команде, `noindex,nofollow`) — без LocalBusiness."""
    tenant = _tenant()
    html = _get(tenant, reverse("storefront-bestaetigung-vorschau"), user=_member(tenant))
    assert "data-confirm-sample" in html  # настоящий доступ команды, не 404
    assert LD not in html


def test_detail_ld_untouched():
    """Негативный контроль: деталь товара не листинг — `?q=` не снимает её LD."""
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant()
    product = ProductFactory()
    path = reverse("storefront-product", kwargs={"pk": product.pk})
    plain = _get(tenant, path)
    searched = _get(tenant, path, {"q": "brot"})
    assert plain.count(LD) >= 2  # LocalBusiness + сущность
    assert searched.count(LD) == plain.count(LD)
