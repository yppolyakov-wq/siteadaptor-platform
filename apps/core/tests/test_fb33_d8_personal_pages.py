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
TOKEN_PATH = re.compile(r"<[^>]*(code|token|signed|secret)[^>]*>")
#: все три urlconf: витрина бизнеса, платформа, городской портал (ревью §10.6 D8 №3)
URLCONFS = ("config.urls_tenant", "config.urls_public", "config.urls_portal")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _pp():
    from apps.core import personal_pages

    return personal_pages


def _routes(urlconf="config.urls_tenant"):
    """(имя, путь) каждого маршрута urlconf."""

    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield p.name, prefix + str(p.pattern)

    return list(walk(get_resolver(urlconf).url_patterns))


def _all_routes():
    return [route for urlconf in URLCONFS for route in _routes(urlconf)]


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
    names = {name for name, _path in _all_routes()}
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


# ── ревью D8 (security + django, 2026-11-24) ──────────────────────────────────────────────


def test_every_secret_route_in_all_urlconfs_is_classified():
    """№2–3: `<code>`, `<token>`, `<signed>`, `<secret>` — во всех трёх urlconf; исключения —
    настоящие имена маршрутов."""
    pp = _pp()
    routes = _all_routes()
    secret = {name for name, path in routes if TOKEN_PATH.search(path)}
    assert {"owner-confirm-email", "telegram-webhook", "business-signup-confirm"} <= secret
    assert secret - pp.PERSONAL_ROUTES - set(pp.NOT_PERSONAL) == set()
    names = {name for name, _path in routes}
    assert set(pp.NOT_PERSONAL) <= names, set(pp.NOT_PERSONAL) - names
    assert pp.PERSONAL_ROUTES <= names, pp.PERSONAL_ROUTES - names


def test_every_account_route_is_classified():
    """№1: ЛК клиента `/konto/…` (витрина и портал) — в реестре или в исключениях с причиной;
    вход по ссылке (`?t=` в query) — в реестре."""
    pp = _pp()
    konto = {name for name, path in _all_routes() if path.startswith("konto/")}
    assert {"account-home", "account-verify", "portal-login-verify"} <= konto
    assert konto - pp.PERSONAL_ROUTES - set(pp.NOT_PERSONAL) == set()
    assert {"account-verify", "portal-login-verify"} <= pp.PERSONAL_ROUTES


def test_trip_group_feed_is_personal():
    """№7: лента поездки (посты и имена участников) — личная."""
    pp = _pp()
    community = {n for n, _p in _routes() if (n or "").startswith("community-space")}
    assert community and community <= pp.PERSONAL_ROUTES


def test_middleware_imports_registry_at_module_level():
    """№7 LOW: импорт реестра — наверху модуля, не на каждый ответ."""
    import inspect

    from apps.core import middleware

    assert "personal_pages" in vars(middleware)
    src = inspect.getsource(middleware.PersonalPageHeadersMiddleware)
    assert "import personal_pages" not in src


# ── сквозные: настоящий стек middleware и urlconf (`django.test.Client`) ─────────────────────


@pytest.fixture
def client_for():
    from django.db import connections
    from django.test import Client

    from apps.tenants.tests.factories import DomainFactory

    made = []

    def make():
        tenant = TenantFactory(
            business_type="bakery",
            enabled_locales=["de", "en"],
            disabled_modules=[],
            slug=f"d8-{uuid.uuid4().hex[:10]}",
        )
        domain = DomainFactory(tenant=tenant, domain=f"{tenant.slug}.siteadaptor.de")
        made.append(tenant)
        return tenant, Client(HTTP_HOST=domain.domain)

    yield make
    connections["default"].set_schema_to_public()


def _get(client, path):
    from django.db import connections

    try:
        return client.get(path, secure=True)
    finally:
        connections["default"].set_schema_to_public()


@pytest.mark.parametrize(
    "path,status",
    [
        ("/bestellung/NOPE-D8/", 404),  # неизвестный код — 404 той же вьюхи
        pytest.param("/konto/", 302),  # ЛК без входа — редирект на вход
        pytest.param("/konto/verify/?t=x", 400),  # токен в query
    ],
)
def test_full_stack_headers(client_for, path, status):
    _tenant_, client = client_for()
    resp = _get(client, path)
    assert resp.status_code == status, (path, resp.status_code)
    assert resp["X-Robots-Tag"] == "noindex, nofollow"
    assert resp["Referrer-Policy"] == "same-origin"


def _deal_paths(tenant):
    """Настоящие личные страницы: заказ, запись, номер, резерв, смета."""
    import datetime

    from django.utils import timezone

    from apps.booking.models import Booking, Resource
    from apps.jobs.models import Job
    from apps.orders.models import Order
    from apps.promotions.models import Customer, Reservation
    from apps.promotions.tests.factories import PromotionFactory
    from apps.stays.models import StayBooking, StayUnit

    def code():
        return f"D8{uuid.uuid4().hex[:6].upper()}"

    c = Customer.objects.create(name="Erika", email="erika@example.com")
    start = timezone.now() + datetime.timedelta(days=3)
    day = timezone.localdate() + datetime.timedelta(days=3)
    order = Order.objects.create(customer=c, reference_code=code(), total=12)
    booking = Booking.objects.create(
        customer=c,
        resource=Resource.objects.create(name="Stuhl"),
        reference_code=code(),
        start=start,
        end=start + datetime.timedelta(hours=1),
    )
    stay = StayBooking.objects.create(
        customer=c,
        unit=StayUnit.objects.create(name="Zimmer 1"),
        reference_code=code(),
        arrival=day,
        departure=day + datetime.timedelta(days=2),
    )
    resv = Reservation.objects.create(
        customer=c, promotion=PromotionFactory(), reference_code=code()
    )
    job = Job.objects.create(customer=c, reference_code=code(), title="Fenster", status="quoted")
    return {
        "order": reverse("storefront-order", args=[order.reference_code]),
        "termin": reverse("storefront-termin-ok", args=[booking.reference_code]),
        "stay": reverse("storefront-stay-ok", args=[stay.reference_code]),
        "reservation": reverse("storefront-confirmation", args=[resv.reference_code]),
        "angebot": reverse("storefront-angebot", args=[job.public_token]),
    }


def test_real_personal_templates_have_one_robots_meta(client_for):
    """№5: настоящие шаблоны личных страниц (со своим `{% block robots %}` или без) —
    ровно одна мета `robots` (`noindex,nofollow`), без LD, с заголовком."""
    tenant, client = client_for()
    from django_tenants.utils import schema_context

    with schema_context(tenant.schema_name):
        paths = _deal_paths(tenant)
    for kind, path in paths.items():
        resp = _get(client, path)
        html = resp.content.decode()
        assert resp.status_code == 200, (kind, resp.status_code)
        assert len(ROBOTS.findall(html)) == 1 and META in html, kind
        assert LD not in html, kind
        assert resp["X-Robots-Tag"] == "noindex, nofollow", kind
