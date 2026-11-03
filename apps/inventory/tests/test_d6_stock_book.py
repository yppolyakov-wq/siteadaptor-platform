"""UX-D D6.2a: «Buchen» шторкой вместо трёх раскрытых форм над таблицей склада."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.core.models import Membership
from apps.inventory import book_views, views
from apps.inventory.models import StockLocation, StockMovement
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
URL = "/dashboard/stock/buchen/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, drawer=True, path=URL):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(business_type="shop", disabled_modules=[])
    return req


def _post(data, drawer=True):
    return book_views.stock_book(_req("post", data, drawer=drawer))


def test_fragment_is_marked_has_no_scripts_and_prefills_the_entity():
    p = ProductFactory(stock_quantity=3)
    resp = book_views.stock_book(_req(data={"entity": f"p{p.pk}", "art": "stocktake"}))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert re.search(rf'<option value="p{p.pk}" selected', html)
    assert 'name="counted"' in html and 'name="art" value="stocktake"' in html


def test_unknown_entity_is_not_selected_silently():
    ProductFactory()
    html = book_views.stock_book(_req(data={"entity": f"p{uuid.uuid4()}"})).content.decode()
    assert " selected" not in html.split('id="sb-entity"', 1)[1].split("</select>", 1)[0]


def test_receipt_books_movement_and_returns_drawer_json():
    p = ProductFactory(stock_quantity=3)
    resp = _post({"art": "receipt", "entity": f"p{p.pk}", "qty": "5", "next": "/dashboard/stock/"})
    p.refresh_from_db()
    assert p.stock_quantity == 8
    data = json.loads(resp.content)
    assert data["ok"] is True and not data.get("navigate")


@pytest.mark.parametrize(
    "art, field, raw",
    [
        ("receipt", "qty", "abc"),
        ("receipt", "qty", "²"),
        ("receipt", "qty", "0"),
        ("receipt", "qty", "-3"),
        ("adjustment", "delta", "abc"),
        ("adjustment", "delta", "0"),
        ("stocktake", "counted", "-1"),
        ("stocktake", "counted", "٣"),
    ],
)
def test_garbage_numbers_are_an_error_at_the_field_without_movement(art, field, raw):
    p = ProductFactory(stock_quantity=3)
    resp = _post({"art": art, "entity": f"p{p.pk}", field: raw})
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert f'id="sb-{field}-err"' in html
    assert not StockMovement.objects.filter(product=p).exclude(kind="opening").exists()
    p.refresh_from_db()
    assert p.stock_quantity == 3


def test_adjustment_keeps_reason_in_note():
    p = ProductFactory(stock_quantity=3)
    _post(
        {
            "art": "adjustment",
            "entity": f"p{p.pk}",
            "delta": "-2",
            "reason": "bruch",
            "note": "Regal",
        }
    )
    mv = StockMovement.objects.filter(product=p, kind=StockMovement.KIND_ADJUSTMENT).get()
    assert mv.delta == -2 and mv.note == "Bruch: Regal"


def test_stocktake_sets_absolute_count():
    p = ProductFactory(stock_quantity=3)
    _post({"art": "stocktake", "entity": f"p{p.pk}", "counted": "7"})
    p.refresh_from_db()
    assert p.stock_quantity == 7


def test_transfer_is_offered_only_with_two_locations():
    ProductFactory()
    html = book_views.stock_book(_req()).content.decode()
    assert "art=transfer" not in html
    StockLocation.objects.create(name="Laden", is_default=True)
    StockLocation.objects.create(name="Lager")
    html = book_views.stock_book(_req()).content.decode()
    assert "art=transfer" in html


def test_without_js_success_redirects_to_stock():
    p = ProductFactory(stock_quantity=1)
    resp = _post({"art": "receipt", "entity": f"p{p.pk}", "qty": "2"}, drawer=False)
    assert resp.status_code == 302 and resp.url == "/dashboard/stock/"


def test_drawer_aware_is_innermost_and_permissions_match_stock():
    from apps.core import drawer, view_perms

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [book_views.stock_book]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code
    assert view_perms.RULES["stock-book"] == view_perms.RULES["stock"]


def test_stock_page_has_no_inline_booking_forms_but_row_buttons():
    p = ProductFactory(stock_quantity=3)
    html = views.stock(_req(drawer=False, path="/dashboard/stock/")).content.decode()
    for action in ("receipt", "adjustment", "transfer"):
        assert f'name="action" value="{action}"' not in html, action
    btn = re.search(rf'<a href="/dashboard/stock/buchen/\?entity=p{p.pk}"[^>]*>', html).group(0)
    assert "data-drawer" in btn
    assert 'id="stock-region" data-drawer-refresh' in html
