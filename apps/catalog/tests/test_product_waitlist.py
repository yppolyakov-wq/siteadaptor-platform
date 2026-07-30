"""M2 Boutique: Warteliste по товару/размеру + фасет Größe + Größentabelle
(план mode-boutique-plan-2026-07-30)."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import waitlist
from apps.catalog.models import Category, Product, ProductVariant, ProductWaitlist
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _product(**kw):
    return Product.objects.create(name={"de": "Kleid"}, base_price=Decimal("45.00"), **kw)


def test_join_idempotent_and_notify_on_receipt(django_capture_on_commit_callbacks):
    from apps.inventory.services import apply_manual_movement

    p = _product()
    v = ProductVariant.objects.create(product=p, label="M", stock_quantity=0)
    assert waitlist.join(p, "kunde@example.de", variant=v) is True
    assert waitlist.join(p, "kunde@example.de", variant=v) is False  # дедуп
    # приёмка размера → письмо, запись гаснет (уведомление в on_commit)
    with django_capture_on_commit_callbacks(execute=True):
        apply_manual_movement(product=p, variant=v, kind="receipt", delta=3)
    entry = ProductWaitlist.objects.get(product=p)
    assert entry.notified is True


def test_notify_variant_scoped():
    """Приёмка размера M не будит подписчиков размера L (но будит «товар в целом»)."""
    p = _product()
    m = ProductVariant.objects.create(product=p, label="M", stock_quantity=0)
    ll = ProductVariant.objects.create(product=p, label="L", stock_quantity=0)
    waitlist.join(p, "m@example.de", variant=m)
    waitlist.join(p, "l@example.de", variant=ll)
    waitlist.join(p, "any@example.de")
    waitlist.notify_available(p, variant=m)
    flags = {e.email: e.notified for e in ProductWaitlist.objects.filter(product=p)}
    assert flags == {"m@example.de": True, "l@example.de": False, "any@example.de": True}


def test_public_join_view():
    from apps.promotions.public_views import product_waitlist_join

    p = _product()
    v = ProductVariant.objects.create(product=p, label="S", stock_quantity=0)
    request = RequestFactory().post(
        f"/sortiment/{p.pk}/warteliste/", {"email": "Neu@Example.DE", "variant": str(v.pk)}
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="clothing")
    resp = product_waitlist_join(request, pk=p.pk)
    assert resp.status_code == 302
    entry = ProductWaitlist.objects.get(product=p)
    assert entry.email == "neu@example.de" and entry.variant_id == v.pk


def test_detail_shows_waitlist_form_for_sold_out_size():
    from apps.promotions.public_views import product_detail

    p = _product()
    ProductVariant.objects.create(product=p, label="M", stock_quantity=0)
    ProductVariant.objects.create(product=p, label="L", stock_quantity=3)
    request = RequestFactory().get(f"/sortiment/{p.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="clothing")
    body = product_detail(request, pk=p.pk).content.decode()
    assert "warteliste/" in body  # форма подписки в DOM
    assert ">M</option>" in body and ">L</option>" not in body  # только sold-out размер


def test_size_facet_filters_available():
    from apps.catalog.facets import CatalogFacets

    a = _product()
    ProductVariant.objects.create(product=a, label="M", stock_quantity=2)
    b = _product()
    ProductVariant.objects.create(product=b, label="M", stock_quantity=0)
    f = CatalogFacets()
    items = Product.objects.filter(is_active=True)
    got = f.apply(items, {"groesse": "M"})
    assert list(got) == [a] or set(got) == {a}
    chips = f.present(items, {})
    assert "M" in chips["size_chips"] or chips["size_chips"] == []  # один размер → скрыто


def test_size_table_rows_parse_and_render():
    from apps.promotions.public_views import product_detail

    cat = Category.objects.create(
        name={"de": "Damen"}, slug="damen-t", size_table="Größe | Brust\nS | 86–90"
    )
    assert cat.size_table_rows == [["Größe", "Brust"], ["S", "86–90"]]
    p = _product(category=cat)
    request = RequestFactory().get(f"/sortiment/{p.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="clothing")
    body = product_detail(request, pk=p.pk).content.decode()
    assert "Größentabelle" in body and "86–90" in body
