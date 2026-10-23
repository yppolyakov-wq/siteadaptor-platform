"""Пилот, батч E (KA-6, P5): кабинет с телефона.

M2 — денежные поля принимают «12,50» на любом языке кабинета. План — пилотная волна
`docs/pilot-wave-plan-2026-10-23.md` §«Батч E», находки `docs/ka-6-mobile-2026-10-23.md`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import translation

from apps.core.form_fields import MoneyField, format_money
from apps.core.money import parse_money

# --- M2: разбор суммы -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12,50", Decimal("12.50")),
        ("12.50", Decimal("12.50")),
        ("1.234,56", Decimal("1234.56")),
        ("1 299", Decimal("1299")),
        ("12,50 €", Decimal("12.50")),
        (" 12,50 ", Decimal("12.50")),
        ("9.90", Decimal("9.90")),
        ("0", Decimal("0")),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_parse_money_reads_german_and_dot_amounts(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "1,2,3", "NaN", "Infinity", "1e5", "1.234.5,6,7", "12,5x"])
def test_parse_money_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_parse_money_ignores_cabinet_language():
    """`DecimalField(localize=True)` читал бы «12,50» как 1250 при кабинете на en."""
    with translation.override("en"):
        assert parse_money("12,50") == Decimal("12.50")
    with translation.override("de"):
        assert parse_money("12.50") == Decimal("12.50")


def test_text_check_shares_the_rule():
    from apps.core.text_check import to_decimal

    assert to_decimal("1.299,00") == Decimal("1299.00")
    assert to_decimal("2,99") == Decimal("2.99")
    assert to_decimal("abc") is None


def test_money_field_validates_bounds_and_places():
    field = MoneyField(min_value=0, max_digits=10, decimal_places=2, required=False)
    assert field.clean("12,50") == Decimal("12.50")
    assert field.clean("") is None
    for bad in ("-1", "1,234", "abc"):
        with pytest.raises(Exception):  # noqa: B017 — ValidationError с разными кодами
            field.clean(bad)


def test_format_money_follows_the_language_and_round_trips():
    with translation.override("de"):
        shown = format_money(Decimal("12.5"))
        assert shown == "12,50"
        assert parse_money(shown) == Decimal("12.50")
    with translation.override("en"):
        shown = format_money(Decimal("12.5"))
        assert shown == "12.50"
        assert parse_money(shown) == Decimal("12.50")
    assert format_money("12,5x") == "12,5x"  # ввод человека показываем как есть


# --- M2: формы ------------------------------------------------------------------------------

pytestmark_db = pytest.mark.django_db


def _assert_money_widget(html: str, name: str):
    tag = (
        html.split(f'name="{name}"')[0].rsplit("<input", 1)[1]
        + html.split(f'name="{name}"')[1].split(">", 1)[0]
    )
    assert 'type="text"' in tag, tag
    assert 'inputmode="decimal"' in tag, tag
    assert "pattern=" not in tag and 'type="number"' not in tag, tag


@pytestmark_db
def test_product_form_accepts_comma_and_dot_prices():
    from apps.catalog.forms import ProductForm

    base = {"name_de": "Brot", "currency": "EUR"}
    form = ProductForm({**base, "base_price": "12,50", "cost_price": "5,5", "list_price": "14,90"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["base_price"] == Decimal("12.50")
    assert form.cleaned_data["cost_price"] == Decimal("5.5")
    assert form.cleaned_data["list_price"] == Decimal("14.90")
    dot = ProductForm({**base, "base_price": "12.50"})
    assert dot.is_valid(), dot.errors
    assert dot.cleaned_data["base_price"] == Decimal("12.50")
    neg = ProductForm({**base, "base_price": "-1"})
    assert not neg.is_valid() and "base_price" in neg.errors


@pytestmark_db
def test_product_form_renders_text_money_inputs():
    from apps.catalog.forms import ProductForm

    html = str(ProductForm().as_p())
    for name in ("base_price", "list_price", "cost_price"):
        _assert_money_widget(html, name)


@pytestmark_db
def test_promotion_voucher_campaign_event_forms_use_money_inputs():
    from apps.events.forms import EventForm
    from apps.promotions.forms import CouponCampaignForm, PromotionForm, VoucherCreateForm

    _assert_money_widget(str(PromotionForm().as_p()), "price_override")
    _assert_money_widget(str(PromotionForm().as_p()), "compare_at_price")
    for form in (VoucherCreateForm(), CouponCampaignForm()):
        html = str(form.as_p())
        _assert_money_widget(html, "discount_eur")
        _assert_money_widget(html, "min_order_eur")
    _assert_money_widget(str(EventForm().as_p()), "price_eur")
    camp = CouponCampaignForm(
        {"name": "X", "discount_eur": "2,50", "valid_days": "30", "subject": "S", "body": "B"}
    )
    assert camp.is_valid(), camp.errors
    assert camp.cleaned_data["discount_eur"] == Decimal("2.50")


@pytestmark_db
def test_quick_promotion_accepts_comma_and_its_dot_payload_round_trips():
    from apps.promotions.quick import QuickPromotionForm

    form = QuickPromotionForm(
        {"title": "Brötchen", "new_price": "2,99", "old_price": "4,50", "term": "7d"}
    )
    form.is_valid()
    assert "new_price" not in form.errors and "old_price" not in form.errors
    assert form.cleaned_data["new_price"] == Decimal("2.99")
    again = QuickPromotionForm(
        {"title": "Brötchen", "new_price": str(Decimal("2.99")), "term": "7d"}
    )
    again.is_valid()
    assert again.cleaned_data.get("new_price") == Decimal("2.99")


def test_hand_written_money_inputs_are_text_fields():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "templates"
    for rel, names in (
        ("promotions/promotion_quick.html", ("new_price", "old_price")),
        ("tenants/quick_start.html", ("new_price", "old_price")),
        ("promotions/coupon_campaigns.html", ("discount_eur", "min_order_eur")),
    ):
        src = (root / rel).read_text()
        for name in names:
            line = next(
                line for line in src.splitlines() if f'name="{name}"' in line and "<input" in line
            )
            assert 'type="text"' in line and 'inputmode="decimal"' in line, (rel, line)
            assert 'type="number"' not in line, (rel, line)


# --- M1/M3: поля 16 px и «Speichern» над таб-баром --------------------------------------

_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]


def _tpl(rel: str) -> str:
    return (_ROOT / "templates" / rel).read_text()


def test_mobile_inputs_are_16px_and_save_bar_clears_the_tab_bar():
    css = (_ROOT / "static/src/app.css").read_text()
    m1 = css.split("KA-M1", 1)[1].split("KA-M3", 1)[0]
    assert "@media (max-width: 767px)" in m1 and "font-size: 16px !important" in m1
    assert "select" in m1 and "textarea" in m1
    built = (_ROOT / "static/css/app.css").read_text()
    assert ".sticky-save" in built and ".tap44" in built and "data-confirm-armed" in built
    assert "data-tabbar" in _tpl("tenant/_base_dashboard.html")
    for rel in ("tenant/settings.html", "tenant/site_seo.html"):
        src = _tpl(rel)
        assert "sticky-save" in src, rel
        assert "sticky bottom-0" not in src, rel


# --- M4: видимость — явное состояние, безопасный next, «Rückgängig» -------------------


def _req(method="get", path="/dashboard/angebote/", data=None, tenant=None):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = get_user_model()(is_active=True)
    if tenant is not None:
        req.tenant = tenant
    return req


@pytest.fixture
def _tenant_urls(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytestmark_db
def test_visibility_is_explicit_so_a_double_tap_does_not_flip_back(_tenant_urls):
    from apps.core.views import sellable_visibility
    from apps.stays.models import StayUnit
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(enabled_modules=["stays"])
    unit = StayUnit.objects.create(name="Zimmer 1", price_cents=8000)
    for _ in range(2):
        sellable_visibility(_req("post", data={"visible": "0"}, tenant=t), "stay", unit.pk)
    unit.refresh_from_db()
    assert unit.is_active is False
    # без поля — прежний флип (старые формы/закладки)
    sellable_visibility(_req("post", tenant=t), "stay", unit.pk)
    unit.refresh_from_db()
    assert unit.is_active is True


@pytestmark_db
@pytest.mark.parametrize(
    ("nxt", "safe"),
    [
        ("/dashboard/angebote/?ansicht=liste", True),
        ("//evil.example/x", False),
        ("https://evil.example/", False),
        ("/\\evil.example", False),
        ("javascript:alert(1)", False),
    ],
)
def test_visibility_returns_only_to_own_paths(_tenant_urls, nxt, safe):
    from apps.core.views import sellable_visibility
    from apps.stays.models import StayUnit
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(enabled_modules=["stays"])
    unit = StayUnit.objects.create(name="Zimmer 1", price_cents=8000)
    resp = sellable_visibility(
        _req("post", data={"visible": "0", "next": nxt}, tenant=t), "stay", unit.pk
    )
    assert resp.status_code == 302
    if safe:
        assert resp.url == nxt
    else:
        assert resp.url.endswith("/angebote/"), resp.url


@pytestmark_db
def test_undo_is_offered_once_and_restores_the_previous_state(_tenant_urls):
    from apps.core.views import sellable_manage, sellable_visibility
    from apps.stays.models import StayUnit
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(enabled_modules=["stays"])
    unit = StayUnit.objects.create(name="Zimmer 1", price_cents=8000)
    hide = _req("post", data={"visible": "0"}, tenant=t)
    sellable_visibility(hide, "stay", unit.pk)
    assert hide.session["sellable_undo"] == {"kind": "stay", "pk": str(unit.pk), "visible": True}

    page = _req(tenant=t)
    page.session = hide.session
    page._messages = hide._messages
    body = sellable_manage(page).content.decode()
    assert "data-sellable-undo" in body and "Rückgängig" in body
    assert 'name="visible" value="1"' in body.split("data-sellable-undo", 1)[1][:600]
    assert "sellable_undo" not in page.session  # одноразово

    again = _req(tenant=t)
    again.session = page.session
    assert "data-sellable-undo" not in sellable_manage(again).content.decode()


def test_visibility_buttons_send_explicit_state_and_big_tap_zone():
    for rel in ("tenant/_sellable_manage_liste.html", "tenant/_sellable_manage_card.html"):
        form = _tpl(rel).split("{% url 'sellable-visibility'", 1)[1].split("</form>", 1)[0]
        assert 'name="visible"' in form and 'name="next"' in form, rel
        assert "tap44" in form, rel


# --- M5: удаление фото — отдельно от ★ и со вторым касанием -----------------------------


def test_photo_delete_is_apart_from_main_star_and_needs_confirm():
    for rel in ("catalog/product_form.html", "promotions/promotion_form.html"):
        src = _tpl(rel)
        delete = next(line for line in src.splitlines() if "✕</button>" in line and "Foto" in line)
        block = src.split(delete, 1)[0][-900:]
        assert "data-confirm-tap" in block and "tap44" in block, rel
        assert "absolute top-1 right-1" in block, rel  # угол фото, а не рядом со ★
    assert '{% include "core/_confirm_tap.html" %}' in _tpl("tenant/_base_dashboard.html")
    confirm = _tpl("core/_confirm_tap.html")
    assert "data-confirm-armed" in confirm and "preventDefault" in confirm


# --- M6: один сканер (с jsQR) на обеих страницах погашения ------------------------------


def test_voucher_page_uses_the_shared_scanner_with_ios_fallback():
    shared = _tpl("promotions/_qr_scanner.html")
    assert "jsQR" in shared and "BarcodeDetector" in shared and "saOnScan" in shared
    assert "vendor/jsqr/jsQR.min.js" in shared
    for rel in ("promotions/redeem.html", "promotions/voucher_redeem.html"):
        src = _tpl(rel)
        assert '{% include "promotions/_qr_scanner.html"' in src, rel
        assert "window.saOnScan" in src, rel
        assert "new BarcodeDetector" not in src, rel  # своей копии камеры больше нет
    voucher = _tpl("promotions/voucher_redeem.html")
    assert "data-scan-form" in voucher and 'value="voucher"' in voucher
    assert "location.href" not in voucher  # T-8.30e: на адрес из QR не переходим
