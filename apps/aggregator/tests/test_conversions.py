"""В5 V5-5a (план docs/v5-portal-analytics-plan-2026-10-17.md §18): обращения и сделки
из каталога города. Решения владельца (§13): канал едет скрытыми полями форм и в УЖЕ
необходимой сессии корзины — новых cookie нет; считается только тот же визит."""

import re
import time
import uuid
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.template import Context, Template
from django.test import RequestFactory

from apps.aggregator import conversions, portal_stats
from apps.aggregator.models import AggregatorListing, PortalStat
from apps.core import attribution
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


@pytest.fixture(autouse=True)
def _private_cache(monkeypatch, isolated_ratelimit):
    from django.core.cache.backends.locmem import LocMemCache

    store = LocMemCache(f"conv-test-{uuid.uuid4().hex}", {})
    isolated_ratelimit.clear()
    monkeypatch.setattr(portal_stats, "cache", store)
    return store


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, **kw):
    kw.setdefault("disabled_modules", [])
    return TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name=slug, **kw)


def _listing(schema, **kw):
    defaults = {
        "tenant_schema": schema,
        "tenant_slug": schema,
        "business_name": "Laden",
        "business_type": "shop",
        "city": "Solingen",
        "listing_kind": "product",
        "source_ref": "1",
        "title": {"de": "Brot"},
        "detail_url": f"https://{schema}.siteadaptor.de/x/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _req(method="get", path="/", data=None, tenant=None, ua=UA, session=None, **extra):
    rf = RequestFactory()
    request = getattr(rf, method)(path, data or {}, HTTP_USER_AGENT=ua, **extra)
    request.META["REMOTE_ADDR"] = f"10.55.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    if session:
        request.session.update(session)
    MessageMiddleware(lambda r: None).process_request(request)
    if tenant is not None:
        request.tenant = tenant
    return request


def _deals(**flt):
    return sum(PortalStat.objects.filter(**flt).values_list("count", flat=True))


# --- резолвер атрибуции -----------------------------------------------------------


def test_clean_channel_and_listing_reject_garbage():
    assert attribution.clean_channel("Instagram Story") == "instagram-story"
    assert attribution.clean_channel("<script>") == "script"
    assert attribution.clean_channel("") == ""
    # внутренние метки source_channel снаружи не принимаются (ревью V5-5a)
    for reserved in ("quote", "Promo", "manual", "offer"):
        assert attribution.clean_channel(reserved) == ""
    assert attribution.clean_listing("12") == 12
    for bad in ("0", "-1", "1e3", "12a", "12345678901", ""):
        assert attribution.clean_listing(bad) is None


def test_resolve_order_post_beats_get_beats_referer_beats_session():
    fresh = {attribution.SESSION_KEY: {"ch": "sess", "cl": "", "at": time.time()}}
    req = _req("post", "/?ch=get", {"ch": "post", "cl": "3"}, session=fresh)
    assert attribution.resolve(req) == attribution.Attribution("post", 3)
    req = _req("get", "/", {"ch": "get"}, session=fresh, HTTP_REFERER="http://testserver/?ch=ref")
    assert attribution.resolve(req).channel == "get"
    req = _req("get", "/", session=fresh, HTTP_REFERER="http://testserver/?ch=ref&cl=4")
    assert attribution.resolve(req) == attribution.Attribution("ref", 4)
    assert attribution.resolve(_req("get", "/", session=fresh)).channel == "sess"
    # легаси-формы до деплоя V5-5 слали `channel`
    assert attribution.resolve(_req("post", "/", {"channel": "flyer"})).channel == "flyer"


def test_referer_of_another_host_and_stale_session_are_ignored():
    req = _req("get", "/", HTTP_REFERER="https://evil.example/?ch=portal&cl=1")
    assert not attribution.resolve(req)
    stale = {attribution.SESSION_KEY: {"ch": "portal", "at": time.time() - 5 * 3600}}
    assert not attribution.resolve(_req("get", "/", session=stale))
    garbage = {attribution.SESSION_KEY: {"ch": "portal", "at": "nope"}}
    assert not attribution.resolve(_req("get", "/", session=garbage))


def test_tag_renders_only_clean_values_and_never_reads_referer():
    tpl = Template("{% load attribution %}{% portal_attribution_fields %}")
    req = _req("get", "/", {"ch": 'portal"><script>', "cl": "7x"})
    html = tpl.render(Context({"request": req}))
    assert "<script>" not in html and 'value="portal-script"' in html and 'name="cl"' not in html
    ref_only = _req("get", "/", HTTP_REFERER="http://testserver/?ch=portal&cl=7")
    assert tpl.render(Context({"request": ref_only})).strip() == ""
    from_ctx = tpl.render(Context({"attr": {"ch": "portal", "cl": 7}}))
    assert 'name="ch" value="portal"' in from_ctx and 'name="cl" value="7"' in from_ctx


def test_landing_with_channel_creates_no_session():
    """TTDSG §25: посадка с ?ch= не пишет в сессию (иначе кука каждому посетителю)."""
    from apps.promotions import public_views
    from apps.promotions.tests.factories import PromotionFactory

    promo = PromotionFactory(status="active", available_quantity=3)
    req = _req("get", f"/p/{promo.pk}/", {"ch": "portal", "cl": "5"}, tenant=_tenant("lnd"))
    resp = public_views.promotion_detail(req, pk=promo.pk)
    assert resp.status_code == 200
    assert not req.session.modified and attribution.SESSION_KEY not in req.session


def test_remember_writes_only_with_attribution():
    req = _req("post", "/", {"ch": "portal", "cl": "9"})
    attribution.remember(req)
    saved = req.session[attribution.SESSION_KEY]
    assert saved["ch"] == "portal" and saved["cl"] == 9
    # повторное добавление с той же атрибуцией из сессии окно визита не продлевает
    old = time.time() - 3600
    again = _req("post", "/", session={attribution.SESSION_KEY: {"ch": "portal", "at": old}})
    attribution.remember(again)
    assert again.session[attribution.SESSION_KEY]["at"] == old
    plain = _req("post", "/")
    attribution.remember(plain)
    assert attribution.SESSION_KEY not in plain.session


# --- ключ объекта ---------------------------------------------------------------


def test_object_key_maps_deals_to_listings():
    assert conversions.object_key("reservation", SimpleNamespace(promotion_id=4)) == (
        "promotion",
        "4",
    )
    assert conversions.object_key("promo_order", SimpleNamespace(pk=4)) == ("promotion", "4")
    assert conversions.object_key("booking", SimpleNamespace(service_id=None)) is None
    assert conversions.object_key("stay", SimpleNamespace(unit_id=2)) == ("stay", "2")
    toured = SimpleNamespace(event=SimpleNamespace(pk=8, tour_id=3, series_id=None))
    assert conversions.object_key("ticket", toured) == ("event", "tour:3")
    single = SimpleNamespace(event=SimpleNamespace(pk=8, tour_id=None, series_id=None))
    assert conversions.object_key("ticket", single) == ("event", "8")
    conv = SimpleNamespace(ref_kind="tour", ref_id="5")
    assert conversions.object_key("conversation", conv) == ("event", "tour:5")
    assert conversions.object_key("conversation", SimpleNamespace(ref_kind="", ref_id="")) is None


# --- сделки: заказ ---------------------------------------------------------------


def _checkout(tenant, data=None, session=None):
    from apps.orders import public_views

    req = _req(
        "post", "/warenkorb/bestellen/", {"name": "K", **(data or {})}, tenant, session=session
    )
    public_views.checkout(req)
    return req


def _cart(product, **attr):
    session = {"cart": {str(product.pk): 1}}
    if attr:
        session[attribution.SESSION_KEY] = {**attr, "at": time.time()}
    return session


def test_cart_add_remembers_attribution_in_cart_session():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views

    product = ProductFactory(base_price=Decimal("3.00"))
    req = _req(
        "post",
        "/warenkorb/add/",
        {"product": str(product.pk), "quantity": "1", "ch": "portal", "cl": "11"},
        tenant=_tenant("cartadd"),
    )
    public_views.cart_add(req)
    assert req.session["cart"] and req.session[attribution.SESSION_KEY]["ch"] == "portal"


def test_order_from_portal_counts_deal_on_cl_listing_and_forgets(
    django_capture_on_commit_callbacks,
):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order

    tenant = _tenant("ord")
    product = ProductFactory(base_price=Decimal("3.00"))
    listing = _listing(tenant.schema_name, source_ref="other")
    with django_capture_on_commit_callbacks(execute=True):
        req = _checkout(tenant, session=_cart(product, ch="portal", cl=listing.pk))
    order = Order.objects.get()
    assert order.source_channel == "portal"
    assert _deals(action="deal", channel="portal", listing_id=listing.pk) == 1
    assert attribution.SESSION_KEY not in req.session  # окно визита закрыто


def test_hidden_cl_listing_falls_back_to_own_object(django_capture_on_commit_callbacks):
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant("hid")
    product = ProductFactory(base_price=Decimal("3.00"))
    hidden = _listing(tenant.schema_name, source_ref="gone", is_active=False)
    mine = _listing(tenant.schema_name, source_ref=str(product.pk))
    with django_capture_on_commit_callbacks(execute=True):
        _checkout(tenant, session=_cart(product, ch="portal", cl=hidden.pk))
    assert _deals(listing_id=hidden.pk) == 0 and _deals(action="deal", listing_id=mine.pk) == 1


def test_foreign_tenant_cl_falls_back_to_own_object(django_capture_on_commit_callbacks):
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant("own")
    product = ProductFactory(base_price=Decimal("3.00"))
    foreign = _listing("t_foreign", source_ref=str(product.pk))
    mine = _listing(tenant.schema_name, source_ref=str(product.pk))
    with django_capture_on_commit_callbacks(execute=True):
        _checkout(tenant, session=_cart(product, ch="portal", cl=foreign.pk))
    assert _deals(listing_id=foreign.pk) == 0
    assert _deals(action="deal", listing_id=mine.pk) == 1


def test_order_without_listing_counts_business_row(django_capture_on_commit_callbacks):
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant("biz", is_demo=True)
    a, b = ProductFactory(base_price=Decimal("1")), ProductFactory(base_price=Decimal("2"))
    session = {
        "cart": {str(a.pk): 1, str(b.pk): 1},
        attribution.SESSION_KEY: {"ch": "entdecken", "at": time.time()},
    }
    with django_capture_on_commit_callbacks(execute=True):
        _checkout(tenant, session=session)
    row = PortalStat.objects.get(action="deal")
    assert (row.listing_kind, row.source_ref, row.listing_id) == ("business", "business", None)
    assert row.channel == "entdecken" and row.is_demo  # демо-бизнес помечен


@pytest.mark.parametrize("attr", [{}, {"ch": "flyer"}])
def test_no_row_without_city_channel(attr, django_capture_on_commit_callbacks):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order

    tenant = _tenant(f"noch-{len(attr)}")
    product = ProductFactory(base_price=Decimal("3.00"))
    _listing(tenant.schema_name, source_ref=str(product.pk))
    with django_capture_on_commit_callbacks(execute=True):
        _checkout(tenant, session=_cart(product, **attr))
    assert Order.objects.get().source_channel == attr.get("ch", "")
    assert not PortalStat.objects.exists()


def test_bot_post_is_not_counted(django_capture_on_commit_callbacks):
    tenant = _tenant("bot")
    listing = _listing(tenant.schema_name)
    req = _req("post", "/", {"ch": "portal", "cl": str(listing.pk)}, tenant, ua="")
    with django_capture_on_commit_callbacks(execute=True):
        conversions.count(req, "deal", "order", SimpleNamespace(pk=1, items=None))
    assert not PortalStat.objects.exists()


def test_same_object_counts_once_but_two_objects_twice(django_capture_on_commit_callbacks):
    tenant = _tenant("once")
    listing = _listing(tenant.schema_name)
    req = _req("post", "/", {"ch": "portal", "cl": str(listing.pk)}, tenant)
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(2):
            conversions.count(req, "deal", "order", SimpleNamespace(pk=1))
        conversions.count(req, "deal", "order", SimpleNamespace(pk=2))
        conversions.count(req, "deal", "promo_order", SimpleNamespace(pk=7), once_key="order:3")
        conversions.count(req, "deal", "promo_order", SimpleNamespace(pk=7), once_key="order:3")
    assert _deals(action="deal") == 3


def test_write_failure_never_breaks_the_deal(django_capture_on_commit_callbacks):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order

    tenant = _tenant("fail")
    product = ProductFactory(base_price=Decimal("3.00"))
    _listing(tenant.schema_name, source_ref=str(product.pk))
    with mock.patch.object(portal_stats, "_bump", side_effect=RuntimeError("db down")):
        with django_capture_on_commit_callbacks(execute=True):
            _checkout(tenant, session=_cart(product, ch="portal"))
    assert Order.objects.count() == 1 and not PortalStat.objects.exists()


# --- сделки по акции ---------------------------------------------------------------


def _promo(**kw):
    from apps.promotions.models import Promotion
    from apps.promotions.tests.factories import PromotionFactory

    kw.setdefault("status", "active")
    kw.setdefault("available_quantity", 5)
    kw.setdefault("promo_type", Promotion.DISCOUNT)
    return PromotionFactory(**kw)


def test_promo_reserve_counts_deal_on_promotion_listing(django_capture_on_commit_callbacks):
    from apps.promotions import public_views

    tenant = _tenant("rsv", disabled_modules=["orders"])
    promo = _promo()
    listing = _listing(tenant.schema_name, listing_kind="promotion", source_ref=str(promo.pk))
    data = {
        "name": "Anna",
        "phone": "0212 1",
        "quantity": "1",
        "form_token": uuid.uuid4().hex,
        "ch": "portal",
    }
    with django_capture_on_commit_callbacks(execute=True):
        resp = public_views.reservation_create(
            _req("post", f"/p/{promo.pk}/reserve/", data, tenant), pk=promo.pk
        )
    assert resp.status_code == 302
    assert _deals(action="deal", channel="portal", listing_id=listing.pk) == 1


def test_coupon_counts_only_when_created(django_capture_on_commit_callbacks):
    from datetime import timedelta

    from django.utils import timezone

    from apps.promotions import public_views

    tenant = _tenant("cpn", disabled_modules=["orders"])
    promo = _promo(metadata={"response": "coupon"}, ends_at=timezone.now() + timedelta(days=2))
    listing = _listing(tenant.schema_name, listing_kind="promotion", source_ref=str(promo.pk))
    with django_capture_on_commit_callbacks(execute=True):
        first = public_views.coupon_create(
            _req("post", f"/p/{promo.pk}/coupon/", {"ch": "portal"}, tenant), pk=promo.pk
        )
        cookie = first.cookies[public_views.COUPON_COOKIE].value
        again = _req("post", f"/p/{promo.pk}/coupon/", {"ch": "portal"}, tenant)
        again.COOKIES[public_views.COUPON_COOKIE] = cookie
        public_views.coupon_create(again, pk=promo.pk)
    assert _deals(action="deal", listing_id=listing.pk) == 1


# --- обращения ----------------------------------------------------------------------


def test_inbox_contact_counts_contact_and_honeypot_does_not(django_capture_on_commit_callbacks):
    from apps.inbox import public_views

    tenant = _tenant("inb")
    _listing(tenant.schema_name)
    base = {"name": "A", "email": "a@test.de", "body": "Hallo?", "ch": "portal"}
    with django_capture_on_commit_callbacks(execute=True):
        public_views.contact(_req("post", "/nachricht/", base, tenant))
        public_views.contact(_req("post", "/nachricht/", {**base, "website": "x"}, tenant))
    row = PortalStat.objects.get()
    assert row.action == "contact" and row.count == 1 and row.listing_kind == "business"


def test_anfrage_is_deal_and_rueckruf_is_contact(django_capture_on_commit_callbacks):
    from apps.jobs import public_views

    tenant = _tenant("job")
    data = {"title": "Torte", "name": "B", "email": "b@test.de", "phone": "1", "ch": "portal"}
    with django_capture_on_commit_callbacks(execute=True):
        public_views.anfrage(_req("post", "/anfrage/", data, tenant))
        public_views.rueckruf(_req("post", "/anfrage/rueckruf/", data, tenant))
    assert _deals(action="deal") == 1 and _deals(action="contact") == 1


# --- скан-замок ------------------------------------------------------------------------


def test_legacy_session_channel_key_is_not_written_anywhere():
    """Посадка больше не пишет `src_ch` в сессию — единственный писатель атрибуции
    в сессию — `attribution.remember` (корзина)."""
    root = Path(__file__).resolve().parents[3] / "apps"
    offenders = [
        str(p)
        for p in root.rglob("*.py")
        if "tests" not in p.parts and re.search(r"session\[[\"']src_ch[\"']\]\s*=", p.read_text())
    ]
    assert offenders == []


# --- V5-5b: запись по времени и проживание ----------------------------------------


def _bookable_service():
    from apps.booking.models import AvailabilityRule, Resource, Service

    service = Service.objects.create(
        name=f"Schnitt {uuid.uuid4().hex[:6]}", price_cents=2500, duration_minutes=60
    )
    resource = Resource.objects.create(name="Mia", capacity=1)
    for wd in range(7):
        AvailabilityRule.objects.create(
            resource=resource, weekday=wd, start_time="09:00", end_time="18:00", slot_minutes=60
        )
    return service


def _starts(*hours):
    from datetime import timedelta

    from django.utils import timezone

    day = timezone.localdate() + timedelta(days=5)
    return [
        timezone.make_aware(timezone.datetime(day.year, day.month, day.day, h, 0)).isoformat()
        for h in hours
    ]


def test_service_booking_group_is_one_deal_on_service_listing(django_capture_on_commit_callbacks):
    from apps.booking import public_views
    from apps.booking.models import Booking

    tenant = _tenant("svc")
    service = _bookable_service()
    listing = _listing(tenant.schema_name, listing_kind="service", source_ref=str(service.pk))
    data = {"start": _starts(10, 12), "name": "Gast", "email": "g@t.de", "ch": "portal"}
    with django_capture_on_commit_callbacks(execute=True):
        public_views.service_book(
            _req("post", f"/termin/{service.pk}/buchen/", data, tenant), pk=service.pk
        )
    assert Booking.objects.count() == 2
    assert {b.source_channel for b in Booking.objects.all()} == {"portal"}
    assert _deals(action="deal", listing_id=listing.pk) == 1  # группа = одна сделка


def test_service_slot_links_and_form_carry_attribution():
    from apps.booking import public_views

    tenant = _tenant("svclinks")
    service = _bookable_service()
    req = _req(
        "get",
        f"/termin/{service.pk}/",
        {"tag": _starts(10)[0][:10], "slot": _starts(10)[0], "ch": "portal", "cl": "5"},
        tenant,
    )
    req.user = SimpleNamespace(is_authenticated=False)
    body = public_views.service_slots(req, pk=service.pk).content.decode()
    assert "ch=portal&amp;cl=5" in body  # выбор другого времени/дня не теряет канал
    assert 'name="ch" value="portal"' in body and 'name="cl" value="5"' in body


def test_stay_booking_counts_deal_on_stay_listing(django_capture_on_commit_callbacks):
    from datetime import timedelta

    from apps.core.tests.dates import future_month_start
    from apps.stays import public_views
    from apps.stays.models import StayBooking, StayUnit

    tenant = _tenant("stay")
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)
    listing = _listing(tenant.schema_name, listing_kind="stay", source_ref=str(unit.pk))
    d0 = future_month_start()
    data = {
        "von": (d0 + timedelta(days=1)).isoformat(),
        "bis": (d0 + timedelta(days=3)).isoformat(),
        "erw": "2",
        "name": "Gast",
        "email": "g@t.de",
        "ch": "portal",
        "cl": str(listing.pk),
    }
    with django_capture_on_commit_callbacks(execute=True):
        public_views.unterkunft_book(
            _req("post", f"/unterkunft/{unit.pk}/buchen/", data, tenant), pk=unit.pk
        )
    assert StayBooking.objects.get().source_channel == "portal"
    assert _deals(action="deal", listing_id=listing.pk) == 1


def test_stay_date_form_carries_attribution():
    from apps.stays import public_views
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)
    req = _req("get", f"/unterkunft/{unit.pk}/", {"ch": "portal", "cl": "8"}, _tenant("staysel"))
    req.user = SimpleNamespace(is_authenticated=False)
    body = public_views.unterkunft_unit(req, pk=unit.pk).content.decode()
    assert 'name="ch" value="portal"' in body and 'name="cl" value="8"' in body


def test_error_redirects_keep_attribution():
    """Ревью V5-5b: после ошибки брони гость возвращается на выбор с тем же каналом."""
    from apps.booking import public_views as booking_views
    from apps.stays import public_views as stay_views
    from apps.stays.models import StayUnit

    tenant = _tenant("errback")
    service = _bookable_service()
    data = {"start": _starts(10), "name": "Gast", "email": "g@t.de", "ch": "portal", "cl": "4"}
    booking_views.service_book(_req("post", "/", data, tenant), pk=service.pk)
    taken = booking_views.service_book(_req("post", "/", data, tenant), pk=service.pk)
    assert taken.status_code == 302 and "ch=portal&cl=4" in taken.url

    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)
    bad = {"von": "2020-01-05", "bis": "2020-01-03", "erw": "2", "name": "G", "ch": "portal"}
    resp = stay_views.unterkunft_book(_req("post", "/", bad, tenant), pk=unit.pk)
    assert resp.status_code == 302 and "ch=portal" in resp.url


def test_deal_from_assistant_link_counts_under_mcp_channel(django_capture_on_commit_callbacks):
    """T-8.10f F-3: ссылка next_step несёт `ch=mcp&cl=<pk>` — сделка на витрине
    засчитывается каналу «Assistenten (KI)» и этому предложению."""
    tenant = _tenant("mcpdeal")
    listing = _listing(tenant.schema_name)
    req = _req("post", "/", {"ch": "mcp", "cl": str(listing.pk)}, tenant)
    with django_capture_on_commit_callbacks(execute=True):
        conversions.count(req, "deal", "order", SimpleNamespace(pk=1, items=None))
    row = PortalStat.objects.get()
    assert row.channel == "mcp" and row.action == "deal" and row.listing_id == listing.pk
