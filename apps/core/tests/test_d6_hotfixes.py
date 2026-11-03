"""UX-D D6.0: хотфиксы денег и данных до вёрстки списков.

- Цена допа читалась `float(…replace(",", "."))`: «1.234,50» и мусор молча давали 0 €.
- Финансы — `Decimal(x.replace(",", "."))`: «1.234» = 1,234 €, `NaN`/`Infinity` → 500,
  мусорная дата → «сегодня» (запись не за тот день, GoBD).
- Подборка показывает только активные товары и не больше 200, а Save делал `.set()` из
  присланного → состав неактивных и 201-го+ товара стирался.
- Порог склада писал `site_config` без блокировки строки тенанта (класс W6).
- Отключить код ваучера было нельзя."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Extra, Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, data=None, method="post", tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = tenant or TenantFactory.build(disabled_modules=[])
    return req


def _levels(req):
    return [m.level_tag for m in get_messages(req)]


# --- общий разбор суммы ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, value",
    [("1.234,50", Decimal("1234.50")), ("12,5", Decimal("12.5")), ("0", Decimal("0"))],
)
def test_parse_amount_accepts_german_amounts(raw, value):
    from apps.core.money import parse_amount

    assert parse_amount(raw) == value


@pytest.mark.parametrize("raw", ["abc", "1,234", "NaN", "Infinity", "-inf", "12,345", "1.500"])
def test_parse_amount_rejects_garbage_and_three_decimals(raw):
    from apps.core.money import parse_amount

    with pytest.raises(ValueError):
        parse_amount(raw)


def test_parse_amount_bounds():
    from apps.core.money import parse_amount

    with pytest.raises(ValueError):
        parse_amount("-1")
    assert parse_amount("-1", allow_negative=True) == Decimal("-1")
    with pytest.raises(ValueError):
        parse_amount("2000000")
    assert parse_amount("") is None


# --- Zusatzleistungen -------------------------------------------------------------------


def _add_extra(**data):
    from apps.core import views

    req = _req("/dashboard/extras/", {"action": "add", "label": "Frühstück", **data})
    views.extras_view(req)
    return req


def test_extra_price_with_thousands_is_read_correctly():
    _add_extra(price="1.234,50")
    assert Extra.objects.get().price_cents == 123450


@pytest.mark.parametrize("raw", ["abc", "1,234", "NaN", "-5"])
def test_extra_garbage_price_is_an_error_without_write(raw):
    req = _add_extra(price=raw)
    assert not Extra.objects.exists() and "error" in _levels(req)


def test_extra_unknown_scope_falls_back_to_all():
    _add_extra(price="5", scope="<evil>")
    assert Extra.objects.get().scope == Extra.SCOPE_ALL


# --- Finanzen ---------------------------------------------------------------------------


def test_journal_reads_thousands_and_rejects_nan():
    from apps.finance import views
    from apps.finance.models import RevenueEntry

    views.journal(_req("/dashboard/finance/", {"amount": "1.234,50", "date": "2026-10-01"}))
    assert RevenueEntry.objects.get().amount == Decimal("1234.50")
    for raw in ("NaN", "Infinity", "1,234"):
        req = _req("/dashboard/finance/", {"amount": raw})
        resp = views.journal(req)
        assert resp.status_code == 302 and "error" in _levels(req)
    assert RevenueEntry.objects.count() == 1


def test_journal_garbage_date_is_an_error_not_today():
    from apps.finance import views
    from apps.finance.models import RevenueEntry

    req = _req("/dashboard/finance/", {"amount": "10", "date": "31.02.2026"})
    views.journal(req)
    assert not RevenueEntry.objects.exists() and "error" in _levels(req)


def test_expense_rejects_nan_and_garbage_dates():
    from apps.finance import views
    from apps.finance.models import ExpenseEntry

    for data in (
        {"amount": "NaN"},
        {"amount": "10", "date": "gestern"},
        {"amount": "10", "due_date": "bald"},
    ):
        req = _req("/dashboard/finance/ausgaben/", data)
        views.expenses(req)
        assert "error" in _levels(req)
    assert not ExpenseEntry.objects.exists()
    views.expenses(_req("/dashboard/finance/ausgaben/", {"amount": "1.234,50"}))
    assert ExpenseEntry.objects.get().amount == Decimal("1234.50")


def test_invoice_line_price_is_parsed_strictly():
    from apps.finance import views
    from apps.finance.models import Invoice

    base = {"line_text_1": "Catering", "line_qty_1": "1"}
    for raw in ("NaN", "1,234", "abc"):
        req = _req("/dashboard/finance/rechnungen/", {**base, "line_price_1": raw})
        views.invoices(req)
        assert "error" in _levels(req)
    assert not Invoice.objects.exists()
    views.invoices(_req("/dashboard/finance/rechnungen/", {**base, "line_price_1": "1.234,50"}))
    assert Invoice.objects.get().lines[0]["unit_price"] == "1234.50"


# --- Kollektionen -----------------------------------------------------------------------


def test_collection_save_keeps_members_not_shown_in_the_form():
    from apps.catalog.tests.factories import ProductFactory
    from apps.collections import views
    from apps.collections.models import Collection

    col = Collection.objects.create(name="Herbst", slug="herbst")
    shown = ProductFactory(name="A-shown")
    hidden = ProductFactory(name="Z-inactive", is_active=False)
    col.products.add(shown, hidden)
    # форма показала только `shown`, владелец его снял
    views.collections_view(
        _req(
            "/dashboard/collections/",
            {
                "action": "update",
                "collection": str(col.pk),
                "name": "Herbst",
                "products_present": "1",
                "products_shown": [str(shown.pk)],
            },
        )
    )
    assert set(col.products.all()) == {hidden}


def test_collection_save_ignores_checked_ids_that_were_not_shown():
    from apps.catalog.tests.factories import ProductFactory
    from apps.collections import views
    from apps.collections.models import Collection

    col = Collection.objects.create(name="Herbst", slug="herbst")
    shown, other = ProductFactory(), ProductFactory()
    views.collections_view(
        _req(
            "/dashboard/collections/",
            {
                "action": "update",
                "collection": str(col.pk),
                "name": "Herbst",
                "products_present": "1",
                "products_shown": [str(shown.pk)],
                "products": [str(shown.pk), str(other.pk)],
            },
        )
    )
    assert set(col.products.all()) == {shown}


def test_collection_form_lists_shown_ids_for_each_kind():
    from apps.catalog.tests.factories import ProductFactory
    from apps.collections import views
    from apps.collections.models import Collection

    Collection.objects.create(name="Herbst", slug="herbst")
    p = ProductFactory()
    html = views.collections_view(_req("/dashboard/collections/", method="get")).content.decode()
    assert f'name="products_shown" value="{p.pk}"' in html


# --- Lager ------------------------------------------------------------------------------


def test_stock_threshold_does_not_overwrite_concurrent_site_config_keys():
    from apps.inventory import views
    from apps.tenants.models import Tenant

    tenant = TenantFactory(site_config={"seo": {"x": 1}})
    stale = Tenant.objects.get(pk=tenant.pk)  # вкладка открыта до чужой правки
    Tenant.objects.filter(pk=tenant.pk).update(site_config={"seo": {"x": 1}, "notify": {"a": 1}})
    views.stock(_req("/dashboard/stock/", {"action": "threshold", "value": "3"}, tenant=stale))
    tenant.refresh_from_db()
    assert tenant.site_config["low_stock_threshold"] == 3
    assert tenant.site_config["notify"] == {"a": 1}
    views.stock(
        _req("/dashboard/stock/", {"action": "lots_toggle", "lots_enabled": "on"}, tenant=stale)
    )
    tenant.refresh_from_db()
    assert tenant.site_config["lots_enabled"] is True and tenant.site_config["notify"]


# --- Gutscheine -------------------------------------------------------------------------


def test_voucher_can_be_deactivated_and_is_then_not_redeemable():
    from apps.loyalty.models import Voucher
    from apps.promotions import services, views

    v = Voucher.objects.create(code="ABC123", label="−10 %", max_uses=5)
    views.voucher_list(
        _req("/promotions/vouchers/", {"action": "toggle_active", "voucher": str(v.pk)})
    )
    v.refresh_from_db()
    assert v.is_active is False and not v.is_redeemable
    with pytest.raises(services.VoucherError):  # у прилавка тот же отказ, что у истёкшего
        services.redeem_voucher("ABC123")
    views.voucher_list(
        _req("/promotions/vouchers/", {"action": "toggle_active", "voucher": str(v.pk)})
    )
    v.refresh_from_db()
    assert v.is_active is True


def test_voucher_list_has_toggle_button_per_code():
    from apps.loyalty.models import Voucher
    from apps.promotions import views

    v = Voucher.objects.create(code="XYZ789", label="Gratis Kaffee")
    html = views.voucher_list(_req("/promotions/vouchers/", method="get")).content.decode()
    assert 'name="action" value="toggle_active"' in html and f'value="{v.pk}"' in html
