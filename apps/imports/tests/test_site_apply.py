"""T-8.27c: «Prüfen & veröffentlichen» — применение в каталог, лимит, профиль, фото."""

import io
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Category, Product
from apps.core.ssrf import Fetched
from apps.imports.models import SiteImportItem, SiteImportRun
from apps.imports.site import apply, service
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = "https://laden.example"


def _run(**kw):
    kw.setdefault("verified_at", timezone.now())
    return SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
        status=SiteImportRun.STATUS_READY,
        **kw,
    )


def _item(run, name="Brot", price="4.90", kind="product", **data):
    payload = {
        "kind": kind,
        "name": name,
        "price": price,
        "description": "Lecker",
        "image_url": "",
        "page_url": ROOT + "/p/" + name,
        "sku": "",
        "gtin": "",
        "category_hint": "",
        "method": "structured",
        "identity": "url:" + name,
        **data,
    }
    return SiteImportItem.objects.create(
        run=run,
        kind=kind,
        data=payload,
        source_url=payload["page_url"],
        fingerprint=service.fingerprint(payload),
        identity_key=service.identity_key(payload["identity"]),
    )


def _tenant(**kw):
    kw.setdefault("subscription_status", "trial")
    return TenantFactory.build(schema_name="laden", **kw)


def _all(run, **edits):
    return {str(i.pk): dict(edits) for i in run.items.all()}


def test_apply_creates_product_without_list_price_or_badge():
    run = _run()
    _item(run, list_price="9.90", badge="sale")  # даже если кандидат что-то такое несёт
    result = apply.apply_items(run, _tenant(), _all(run))
    product = Product.objects.get()
    assert result.created == 1
    assert product.base_price == Decimal("4.90") and product.list_price is None
    assert product.badge == "" and product.primary_action == ""
    assert product.external_url == ROOT + "/p/Brot"
    assert product.metadata["import"]["method"] == "structured"
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_APPLIED


def test_item_without_price_becomes_on_request():
    run = _run()
    _item(run, price=None)
    apply.apply_items(run, _tenant(), _all(run))
    product = Product.objects.get()
    assert product.base_price == 0 and product.primary_action == "request"


def test_only_selected_items_applied_rest_skipped():
    run = _run()
    keep, drop = _item(run, "A"), _item(run, "B")
    apply.apply_items(run, _tenant(), {str(keep.pk): {}})
    drop.refresh_from_db()
    assert Product.objects.count() == 1 and drop.decision == "skipped"


def test_edits_applied_and_sanitized():
    run = _run()
    item = _item(run)
    edits = {"name": "<script>x</script>Roggenbrot", "price": "5,20", "description": "<b>neu</b>"}
    apply.apply_items(run, _tenant(), {str(item.pk): edits})
    product = Product.objects.get()
    assert product.name["de"] == "Roggenbrot" and product.base_price == Decimal("5.20")
    assert product.description["de"] == "neu"


def test_new_category_created_once_and_reused():
    run = _run()
    a, b = _item(run, "A"), _item(run, "B")
    choice = {"category": "new:Brot & Brötchen"}
    apply.apply_items(run, _tenant(), {str(a.pk): choice, str(b.pk): choice})
    assert Category.objects.count() == 1
    assert set(Product.objects.values_list("category__slug", flat=True)) == {
        Category.objects.get().slug
    }


def test_apply_respects_free_limit_server_side(settings):
    settings.IMPORT_FREE_ITEMS = 2
    run = _run()
    for name in "ABC":
        _item(run, name)
    result = apply.apply_items(run, _tenant(), _all(run))
    assert result.created == 2 and result.over_limit == 1
    assert Product.objects.count() == 2


def test_limit_counts_previous_imports_but_updates_are_free(settings):
    settings.IMPORT_FREE_ITEMS = 1
    first = _run()
    _item(first, "A")
    apply.apply_items(first, _tenant(), _all(first))
    second = _run()
    _item(second, "A", price="5.50")  # та же позиция — обновление, не новая
    _item(second, "B")
    result = apply.apply_items(second, _tenant(), _all(second))
    assert result.updated == 1 and result.created == 0 and result.over_limit == 1
    assert Product.objects.get().base_price == Decimal("5.50")


def test_paid_and_demo_tenants_have_no_limit(settings):
    settings.IMPORT_FREE_ITEMS = 1
    assert apply.free_limit(_tenant(subscription_status="active")) is None
    assert apply.free_limit(_tenant(is_demo=True)) is None
    assert apply.free_limit(_tenant()) == 1


def test_limit_race_takes_advisory_lock():
    """Две вкладки: лимит пересчитывается под pg_advisory_xact_lock схемы."""
    run = _run()
    _item(run)
    with mock.patch.object(apply, "_lock_schema", wraps=apply._lock_schema) as lock:
        apply.apply_items(run, _tenant(), _all(run))
    lock.assert_called_once()


def test_profile_fills_only_selected_fields():
    run = _run(
        profile={
            "phone": "+49 212 1",
            "address": "Markt 1, 42651 Solingen",
            "opening_hours_structured": {"0": ["07:00", "18:00"]},
        }
    )
    tenant = _tenant(contact_phone="alt", address="")
    with mock.patch.object(type(tenant), "save") as save:
        changed = apply.apply_profile(run, tenant, ["address", "opening_hours_structured"])
    assert tenant.contact_phone == "alt" and tenant.address == "Markt 1, 42651 Solingen"
    assert set(changed) == {"address", "opening_hours_structured"}
    save.assert_called_once()


def test_service_items_become_services_when_booking_active():
    from apps.booking.models import Service

    run = _run()
    _item(run, "Haarschnitt", price="32", kind="service", duration_min=45)
    with mock.patch("apps.core.modules.is_module_active", return_value=True):
        apply.apply_items(run, _tenant(), _all(run))
    service_obj = Service.objects.get()
    assert service_obj.price_cents == 3200 and service_obj.duration_minutes == 45
    assert service_obj.external_url.endswith("/p/Haarschnitt") and not Product.objects.exists()


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    return buf.getvalue()


def test_image_downloaded_via_safe_fetch_and_reencoded():
    run = _run()
    _item(run, image_url=ROOT + "/brot.png")
    apply.apply_items(run, _tenant(), _all(run))
    calls = []

    def fetch(url, **kw):
        calls.append((url, kw))
        return Fetched(url, 200, "image/png", _png())

    assert apply.fetch_images(run, fetch=fetch) == 1
    ((url, kw),) = calls
    assert url == ROOT + "/brot.png" and set(kw["accept"]) <= {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    image = Product.objects.get().images[0]
    assert image["mime_type"] == "image/webp" and image["is_primary"]


def test_broken_image_skipped_silently():
    run = _run()
    _item(run, image_url=ROOT + "/x.png")
    apply.apply_items(run, _tenant(), _all(run))
    fetch = lambda url, **kw: Fetched(url, 200, "image/png", b"not an image")  # noqa: E731
    assert apply.fetch_images(run, fetch=fetch) == 0
    assert Product.objects.get().images == []


def test_images_task_enqueued_after_commit(django_capture_on_commit_callbacks):
    run = _run()
    _item(run)
    with mock.patch.object(apply, "_enqueue_images") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            apply.apply_items(run, _tenant(), _all(run))
    enqueue.assert_called_once()
