"""FB-33 D8: личные страницы витрины вне индекса (решение владельца 2026-11-24).

План — `docs/fb33-stack13-plan-2026-11-24.md` §10.6 и строка D8 §3. Один реестр маршрутов
`apps/core/personal_pages.py`; middleware ставит `X-Robots-Tag: noindex, nofollow` и
`Referrer-Policy: same-origin` (и не-HTML); `_base.html` — мета `noindex,nofollow` и без
LocalBusiness. Обычные страницы — без изменений.
"""

import re
import uuid
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import URLPattern, URLResolver, get_resolver, resolve, reverse

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


rf = RequestFactory()
LD = '<script type="application/ld+json">'
META = '<meta name="robots" content="noindex,nofollow">'
ROBOTS = re.compile(r'<meta name="robots"')
TOKEN_PATH = re.compile(r"<[^>]*(code|token)[^>]*>")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pp():
    from apps.core import personal_pages

    return personal_pages


def _routes():
    """(имя, путь) каждого маршрута `config/urls_tenant.py`."""

    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield p.name, prefix + str(p.pattern)

    return list(walk(get_resolver("config.urls_tenant").url_patterns))


def _tenant():
    return TenantFactory(business_type="bakery", enabled_locales=["de", "en"], disabled_modules=[])


def _req(tenant, path, *, url_name=None):
    req = rf.get(path, HTTP_HOST=f"{uuid.uuid4().hex}.test")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = AnonymousUser()
    req.portal = None
    req.tenant = tenant
    req.LANGUAGE_CODE = "de"
    req.resolver_match = (
        SimpleNamespace(url_name=url_name, kwargs={}, args=(), namespace="", app_name="")
        if url_name
        else resolve(path)
    )
    return req


def _middleware(request, response):
    from apps.core.middleware import PersonalPageHeadersMiddleware

    return PersonalPageHeadersMiddleware(lambda r: response)(request)


def test_every_token_route_is_classified():
    """Замок покрытия: маршрут с `<code>`/`<token>` в пути — в реестре или в исключениях."""
    pp = _pp()
    token_routes = {name for name, path in _routes() if TOKEN_PATH.search(path)}
    assert len(token_routes) > 30  # обход не пуст
    assert token_routes - pp.PERSONAL_ROUTES - set(pp.NOT_PERSONAL) == set()
    assert not pp.PERSONAL_ROUTES & set(pp.NOT_PERSONAL)
    assert all(reason.strip() for reason in pp.NOT_PERSONAL.values())
    names = {name for name, _path in _routes()}
    assert pp.PERSONAL_ROUTES <= names, pp.PERSONAL_ROUTES - names  # без опечаток


def test_middleware_registered_after_security():
    stack = list(dj_settings.MIDDLEWARE)
    mine = "apps.core.middleware.PersonalPageHeadersMiddleware"
    assert mine in stack
    # ответ идёт снизу вверх: наш Referrer-Policy раньше `setdefault` SecurityMiddleware
    assert stack.index(mine) > stack.index("django.middleware.security.SecurityMiddleware")


PERSONAL = sorted(
    {
        "storefront-order",
        "storefront-termin-ok",
        "storefront-stay-ok",
        "storefront-ticket-ok",
        "storefront-confirmation",
        "storefront-angebot",
        "storefront-offer",
        "storefront-ticket-participants",
        "storefront-ticket-qr",
        "storefront-ticket-memo",
        "storefront-stay-ical",
        "storefront-unsubscribe",
    }
)


@pytest.mark.parametrize(
    "content_type", ["text/html; charset=utf-8", "image/svg+xml", "application/pdf"]
)
def test_headers_on_every_personal_route(content_type):
    pp = _pp()
    assert set(PERSONAL) <= pp.PERSONAL_ROUTES
    tenant = _tenant()
    for name in sorted(pp.PERSONAL_ROUTES):
        out = _middleware(_req(tenant, "/", url_name=name), HttpResponse(content_type=content_type))
        assert out["X-Robots-Tag"] == "noindex, nofollow", name
        assert out["Referrer-Policy"] == "same-origin", name


def test_base_meta_and_no_ld_on_every_personal_route():
    tenant = _tenant()
    for name in sorted(_pp().PERSONAL_ROUTES):
        html = render_to_string(
            "storefront/_base.html", {}, request=_req(tenant, "/", url_name=name)
        )
        assert html.count(META) == 1 and len(ROBOTS.findall(html)) == 1, name
        assert LD not in html, name


def test_real_reservation_confirmation_page():
    """Сквозной: настоящая страница резерва `/r/<code>/` — заголовки, мета, без LD."""
    from apps.promotions import public_views
    from apps.promotions.models import Customer, Reservation
    from apps.promotions.tests.factories import PromotionFactory

    tenant = _tenant()
    code = f"R{uuid.uuid4().hex[:6].upper()}"
    Reservation.objects.create(
        customer=Customer.objects.create(name="Erika", email="erika@example.com"),
        promotion=PromotionFactory(),
        reference_code=code,
    )
    path = reverse("storefront-confirmation", args=[code])
    req = _req(tenant, path)
    out = _middleware(req, public_views.reservation_confirmation(req, code=code))
    html = out.content.decode()
    assert out.status_code == 200 and code in html
    assert out["X-Robots-Tag"] == "noindex, nofollow"
    assert html.count(META) == 1 and LD not in html


def _home_and_product(tenant):
    from apps.catalog.tests.factories import ProductFactory

    product = ProductFactory()
    for path in ("/", reverse("storefront-product", kwargs={"pk": product.pk})):
        req = _req(tenant, path)
        match = req.resolver_match
        resp = match.func(req, *match.args, **match.kwargs)
        if hasattr(resp, "render"):
            resp = resp.render()
        yield path, req, resp


def test_regular_pages_unchanged():
    """Охранный: главная и деталь товара — без noindex и с LocalBusiness (как раньше)."""
    tenant = _tenant()
    for path, _unused, resp in _home_and_product(tenant):
        html = resp.content.decode()
        assert resp.status_code == 200, path
        assert "nofollow" not in html and LD in html, path


def test_middleware_leaves_regular_pages_alone():
    tenant = _tenant()
    for path, req, resp in _home_and_product(tenant):
        before = dict(resp.items())
        out = _middleware(req, resp)
        assert dict(out.items()) == before, path
        assert "X-Robots-Tag" not in out, path


def test_not_personal_routes_get_no_headers():
    tenant = _tenant()
    for name in _pp().NOT_PERSONAL:
        out = _middleware(_req(tenant, "/", url_name=name), HttpResponse())
        assert "X-Robots-Tag" not in out, name
