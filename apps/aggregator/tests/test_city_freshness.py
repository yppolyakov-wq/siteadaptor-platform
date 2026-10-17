"""Г3: «срок свежести» товаров и услуг в каталоге города.

План — docs/g3-g4-freshness-digest-plan-2026-10-17.md §2, §6. Позиция без явного
подтверждения владельца N дней уходит из каталога города; продажи и фоновые записи
срок не продлевают; демо не протухает; «Alles noch aktuell» возвращает всё сразу.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import owner_views, tasks
from apps.aggregator.models import AggregatorListing
from apps.booking.models import Service
from apps.catalog.models import Product
from apps.core import freshness

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db):
    from apps.tenants.tests.factories import TenantFactory

    return TenantFactory(
        schema_name="public", slug="laden", in_city_catalog=True, email_pending=False
    )


def _product(days_ago=0, **kw):
    p = Product.objects.create(
        name={"de": kw.pop("name", "Brot")},
        base_price=Decimal("3.10"),
        images=[{"url": "/media/brot.webp", "is_primary": True}],
        **kw,
    )
    Product.objects.filter(pk=p.pk).update(confirmed_at=timezone.now() - timedelta(days=days_ago))
    p.refresh_from_db()
    return p


def _service(days_ago=0):
    s = Service.objects.create(name="Haarschnitt", price_cents=3000, duration_minutes=30)
    Service.objects.filter(pk=s.pk).update(confirmed_at=timezone.now() - timedelta(days=days_ago))
    return s


def _sync(product):
    with (
        mock.patch.object(tasks, "_withheld", return_value=False),
        mock.patch.object(tasks, "_image_ok", return_value=True),
    ):
        return tasks.sync_product_listing("public", product.pk)


def _sync_service(service):
    with (
        mock.patch.object(tasks, "_withheld", return_value=False),
        mock.patch.object(tasks, "_image_ok", return_value=True),
        mock.patch("apps.tenants.models.Tenant.is_module_active", return_value=True, create=True),
    ):
        return tasks.sync_service_listing("public", service.pk)


def _listed(obj):
    return AggregatorListing.objects.filter(source_ref=str(obj.pk)).exists()


def test_stale_product_leaves_the_catalog(tenant, settings):
    settings.CITY_FRESHNESS_DAYS = 60
    assert _sync(_product(days_ago=59)) == "upserted"
    old = _product(days_ago=61, name="Alt")
    assert _sync(old) == "removed" and not _listed(old)


def test_stale_service_leaves_the_catalog(tenant, settings):
    settings.CITY_FRESHNESS_DAYS = 60
    assert _sync_service(_service(days_ago=10)) == "upserted"
    assert _sync_service(_service(days_ago=61)) == "removed"


def test_sale_and_background_writes_do_not_confirm(tenant):
    p = _product(days_ago=61, stock_quantity=5)
    before = p.confirmed_at
    p.stock_quantity = 4
    p.save(update_fields=["stock_quantity", "updated_at"])  # продажа
    p.images = [{"url": "/media/neu.webp", "is_primary": True}]
    p.save(update_fields=["images", "updated_at"])  # фоновая подгрузка фото
    Product.objects.filter(pk=p.pk).update(stock_quantity=10)  # возврат стока массово
    p.refresh_from_db()
    assert p.confirmed_at == before
    assert _sync(p) == "removed"


def test_confirm_brings_the_position_back(tenant):
    p = _product(days_ago=61)
    assert _sync(p) == "removed"
    freshness.confirm(p)
    p.refresh_from_db()
    assert timezone.now() - p.confirmed_at < timedelta(minutes=1)
    assert _sync(p) == "upserted"


def test_product_form_save_confirms(tenant, django_user_model):
    from apps.catalog import views as catalog_views

    p = _product(days_ago=61)
    user = django_user_model.objects.create_user(username="chef", password="x")
    request = RequestFactory().post(
        f"/catalog/products/{p.pk}/edit/",
        {
            "name_de": "Brot",
            "name_en": "",
            "description_de": "",
            "description_en": "",
            "base_price": "3.10",
            "currency": "EUR",
            "sku": "",
            "is_active": "on",
        },
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    assert catalog_views.product_edit(request, pk=p.pk).status_code == 302
    p.refresh_from_db()
    assert timezone.now() - p.confirmed_at < timedelta(minutes=1)


def test_service_update_confirms(tenant, django_user_model):
    from apps.booking import views as booking_views

    s = _service(days_ago=61)
    user = django_user_model.objects.create_user(username="chef2", password="x")
    request = RequestFactory().post(
        "/dashboard/booking/services/",
        {"action": "update", "service": str(s.pk), "duration": "30", "price_eur": "30"},
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user, request.tenant = user, tenant
    booking_views.services_view(request)
    s.refresh_from_db()
    assert timezone.now() - s.confirmed_at < timedelta(minutes=1)


def test_import_unchanged_confirm_stamps_the_target(tenant):
    from apps.imports.models import SiteImportItem, SiteImportRun
    from apps.imports.site import apply

    p = _product(days_ago=61)
    run = SiteImportRun.objects.create(
        start_url="https://laden.example/", host="laden.example",
        consent_at=timezone.now(), consent_version="x",
    )  # fmt: skip
    item = SiteImportItem.objects.create(
        run=run, kind="product", diff=SiteImportItem.DIFF_UNCHANGED, data={"name": "Brot"},
        fingerprint="f" * 64, identity_key="i" * 64, target_kind="product",
        target_id=str(p.pk),
    )  # fmt: skip
    apply._confirm(item, deactivate=False)
    p.refresh_from_db()
    assert timezone.now() - p.confirmed_at < timedelta(minutes=1)


def test_confirm_all_stamps_everything_and_queues_reconcile(tenant):
    p, s = _product(days_ago=61), _service(days_ago=61)
    hidden = _product(days_ago=61, name="Versteckt", hide_in_city=True)
    with (
        mock.patch("apps.aggregator.tasks.reconcile_city_catalog.delay") as delay,
        mock.patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        n = freshness.confirm_all("public")
    assert n == 2
    delay.assert_called_once()
    for obj in (p, s):
        obj.refresh_from_db()
        assert timezone.now() - obj.confirmed_at < timedelta(minutes=1)
    hidden.refresh_from_db()
    assert hidden.confirmed_at < timezone.now() - timedelta(days=60)


def test_demo_never_goes_stale(tenant):
    tenant.is_demo = True
    tenant.save(update_fields=["is_demo"])
    assert _sync(_product(days_ago=400)) == "upserted"
    assert freshness.expiring(tenant) == {"soon": 0, "gone": 0, "first_expiry": None}


def test_zero_days_switches_it_off(tenant, settings):
    settings.CITY_FRESHNESS_DAYS = 0
    assert _sync(_product(days_ago=400)) == "upserted"


def test_new_rows_and_migrated_rows_start_fresh(tenant):
    p = Product.objects.create(name={"de": "Neu"}, base_price=Decimal("1.00"))
    assert timezone.now() - p.confirmed_at < timedelta(minutes=1)
    field = Product._meta.get_field("confirmed_at")
    assert field.null is False and field.default is timezone.now


def test_expiring_counts_soon_and_gone(tenant, settings):
    settings.CITY_FRESHNESS_DAYS, settings.CITY_FRESHNESS_WARN_DAYS = 60, 7
    _product(days_ago=55, name="Bald")
    _product(days_ago=70, name="Weg")
    _product(days_ago=10, name="Frisch")
    info = freshness.expiring(tenant)
    assert info["soon"] == 1 and info["gone"] == 1
    assert info["first_expiry"] == timezone.localdate() + timedelta(days=5)


def _post_confirm(user, tenant, nxt):
    request = RequestFactory().post("/dashboard/stadtkatalog-aktuell/", {"next": nxt})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user, request.tenant = user, tenant
    with mock.patch.object(freshness, "confirm_all", return_value=3):
        return owner_views.freshness_confirm(request)


def test_confirm_endpoint_post_only_and_safe_next(tenant, django_user_model):
    from django.contrib.auth.models import AnonymousUser

    user = django_user_model.objects.create_user(username="staff", password="x")
    assert _post_confirm(user, tenant, "//evil.example/x")["Location"] == "/dashboard/"
    assert _post_confirm(user, tenant, "https://evil.example/")["Location"] == "/dashboard/"
    for bad in (
        "/\t/evil.example",
        "/\n/evil.example",
        "///evil.example",
        "/\\evil.example",
        "javascript:alert(1)",
        "https:evil.example",
        "/catalog/",
    ):
        assert _post_confirm(user, tenant, bad)["Location"] == "/dashboard/", bad
    assert _post_confirm(user, tenant, "/dashboard/stadtportal/")["Location"] == (
        "/dashboard/stadtportal/"
    )
    get = RequestFactory().get("/dashboard/stadtkatalog-aktuell/")
    get.user, get.tenant = user, tenant
    assert owner_views.freshness_confirm(get).status_code == 405
    anon = RequestFactory().post("/dashboard/stadtkatalog-aktuell/")
    anon.user, anon.tenant = AnonymousUser(), tenant
    assert owner_views.freshness_confirm(anon).status_code == 302  # на вход


def test_banner_only_for_listable_business(tenant):
    _product(days_ago=55)
    assert freshness.banner(tenant)["soon"] == 1
    tenant.in_city_catalog = False
    assert freshness.banner(tenant) is None


def test_warning_mail_weekly_dedupe_and_language(tenant, settings):
    from apps.core import tasks as core_tasks
    from apps.notifications.models import Notification

    settings.CITY_FRESHNESS_DAYS, settings.CITY_FRESHNESS_WARN_DAYS = 60, 7
    tenant.owner_email = "chef@laden.example"
    tenant.save(update_fields=["owner_email"])
    _product(days_ago=58)
    assert core_tasks.warn_freshness_for_tenant(tenant) is True
    assert core_tasks.warn_freshness_for_tenant(tenant) is False  # та же ISO-неделя
    body = Notification.objects.get(type="city_freshness").payload["body"]
    assert "/dashboard/" in body


def test_no_warning_for_demo_or_without_soon(tenant):
    from apps.core import tasks as core_tasks

    tenant.owner_email = "chef@laden.example"
    _product(days_ago=1)
    assert core_tasks.warn_freshness_for_tenant(tenant) is False
    tenant.is_demo = True
    _product(days_ago=58, name="Bald")
    assert core_tasks.warn_freshness_for_tenant(tenant) is False


def test_neu_badge_fades_without_confirmation(tenant):
    p = _product(days_ago=31, badge="neu")
    Product.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=100))
    with mock.patch.object(tasks, "_image_ok", return_value=True):
        assert tasks._product_snapshot(p.pk)["is_new"] is False
        Product.objects.filter(pk=p.pk).update(confirmed_at=timezone.now())
        assert tasks._product_snapshot(p.pk)["is_new"] is True
        Product.objects.filter(pk=p.pk).update(
            badge="", created_at=timezone.now() - timedelta(days=5),
            confirmed_at=timezone.now() - timedelta(days=50),
        )  # fmt: skip
        assert tasks._product_snapshot(p.pk)["is_new"] is True  # новинка по дате


def test_no_banner_for_aktionen_only_business(tenant):
    _product(days_ago=55)
    tenant.site_config = {"profile": "aktionen"}
    assert freshness.banner(tenant) is None


def test_freshness_line_alone_does_not_send_a_digest(tenant):
    from apps.core import digest

    tenant.disabled_modules = ["finance", "booking", "stays", "events", "orders", "jobs", "inbox"]
    _product(days_ago=55)
    assert digest.collect_digest(tenant) is None
