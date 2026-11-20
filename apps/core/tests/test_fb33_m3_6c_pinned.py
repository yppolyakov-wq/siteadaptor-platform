"""FB-33 M3-6c (макет M0-10): закреплённые строки 🔒 и правовые строки (§ 312j BGB).

Замки C0: «Kaufen»/«Buchung» закреплены (без ручки, но цель броска `data-schema-pinned`);
🔒 у закреплённых строк списка и в заголовке окна, у общих строк схемы объекта — нет; плашка
§ 312j — только у правовых строк; подпись кнопки заказа нигде не хранится и не пишется: поле
без `name` вне формы, любой POST на строку — отказ; подпись окна = подпись витрины (оба режима
корзины); строки 🔒 не двигаются.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import translation

from apps.core import detail_parts, legal_buttons, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CFG, _panel
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"

PLAQUE = (
    "Bestellübersicht, Gesamtpreis und der Button „Zahlungspflichtig bestellen“ müssen direkt "
    "untereinander stehen — so verlangt es § 312j BGB (Button-Lösung). Deshalb lässt er sich "
    "nicht verschieben, ausblenden oder in der Breite ändern. Texte und Felder können Sie anpassen."
)


def _shop(config=None):
    tenant = _tenant()
    tenant.site_config = config if config is not None else CFG
    tenant.save()
    return tenant


def _li(html, ref):
    at = html.index(f'data-schema-block="{ref}"')
    return html[html.rindex("<li", 0, at) : html.index("</li>", at)]


# ───────────── C5: «Kaufen» закреплена, бросок на неё ─────────────


def test_kauf_row_is_pinned_without_grip_but_is_a_drop_target():
    cfg = siteconfig.normalize({})
    kauf = next(r for r in site_schema.blocks_for(cfg, "product") if r["ref"] == "__kauf")
    assert kauf["pinned"] is True
    html = Browser(_shop()).get("?seite=product")
    li = _li(html, "__kauf")
    assert "data-schema-drag" not in li and 'data-schema-pinned="__kauf"' in li
    assert "schema-grip" not in li and "🔒" in li


def test_kauf_is_not_a_cart_pinned_section():
    assert all("kauf" not in keys for keys in detail_parts.PINNED.values())


def test_drop_before_and_after_kauf_still_moves_the_block():
    js = (Path(__file__).resolve().parents[3] / "static/js/aufbau.js").read_text()
    assert "[data-schema-drag],[data-schema-slot],[data-schema-pinned]" in js
    assert 'li.getAttribute("data-schema-drag") || li.getAttribute("data-schema-pinned")' in js
    # перетаскивать саму закреплённую строку нельзя (dragstart — только у data-schema-drag)
    assert 'if (!li || !li.hasAttribute("data-schema-drag")) return;' in js


def test_lock_in_list_and_window_title_but_not_on_shared_rows():
    b = Browser(_shop())
    html = b.get("?seite=cart&block=summary")
    assert "🔒" in _li(html, "summary") and 'data-schema-pinned="summary"' in _li(html, "summary")
    title = re.search(r'<h2 id="schema-panel-title".*?</h2>', html, re.S).group(0)
    assert "🔒" in title and "(fest)" in title
    # ★ и обычный блок — без замка
    assert "🔒" not in _li(b.get("?seite=home"), "t1")
    src = (TEMPLATES / "tenant/site_schema.html").read_text()
    shared = src[
        src.index("{% if b.shared %}") : src.index("{% else %}", src.index("{% if b.shared %}"))
    ]
    assert "🔒" not in shared, "общая строка схемы объекта — не «закон», без замка"


# ───────────── C5: подпись кнопки — только чтение, витрина = окно ─────────────


def test_cart_summary_window_shows_the_plaque_and_a_read_only_label():
    html = _panel(Browser(_shop()).get("?seite=cart&block=summary"))
    assert PLAQUE in html
    field = re.search(r'<input[^>]*id="schema-legal-label"[^>]*>', html).group(0)
    assert 'value="Zahlungspflichtig bestellen"' in field and "readonly" in field
    assert "name=" not in field, "поле подписи не отправляется ни одной формой"
    forms = re.findall(r"<form\b.*?</form>", html, re.S)
    assert all("schema-legal-label" not in f for f in forms)
    assert "Gesetzlich vorgegeben, nicht änderbar." in html
    assert "Hier werden keine Angaben abgefragt" in html  # «Felder» итога


def test_quote_cart_window_label_follows_the_storefront():
    html = _panel(Browser(_shop({**CFG, "quote_cart": True})).get("?seite=cart&block=summary"))
    assert 'value="Unverbindlich anfragen"' in html and PLAQUE not in html


def test_buchung_has_its_own_text_and_kaufen_no_button_field():
    product = _panel(Browser(_shop()).get("?seite=product&block=__kauf"))
    assert "§ 312j BGB" in product and 'id="schema-legal-label"' not in product
    text = legal_buttons.panel("service_detail", "__kauf")
    assert (
        "Zahlungspflichtig buchen" in text["text"] and text["label"] == "Zahlungspflichtig buchen"
    )
    assert legal_buttons.panel("event_detail", "__kauf")["label"] == "Zahlungspflichtig buchen"
    assert legal_buttons.panel("gift", "form")["text"] == PLAQUE


def test_only_legal_rows_have_the_plaque():
    assert legal_buttons.is_legal("cart", "summary")
    assert legal_buttons.is_legal("gift", "form")
    assert legal_buttons.is_legal("product_detail", "__kauf")
    for host, ref in (
        ("cart", "items"),
        ("cart", "form"),
        ("confirmation", "summary"),
        ("info", "pagetext"),
    ):
        assert not legal_buttons.is_legal(host, ref), (host, ref)
    html = _panel(Browser(_shop()).get("?seite=confirmation&block=summary"))
    assert "data-schema-legal" not in html


@pytest.mark.parametrize("ref", ["summary", "__kauf"])
def test_any_post_on_a_legal_row_is_refused_and_nothing_is_stored(ref):
    tenant = _shop()
    b = Browser(tenant)
    code = "cart" if ref == "summary" else "product"
    for data in (
        {"op": "update", "panel_present": "1", "f_button_label": "Jetzt kaufen"},
        {"op": "update", "panel_present": "1", "f_label": "Jetzt kaufen"},
        {"op": "toggle"},
        {"op": "up"},
        {"op": "move", "value": "after:items"},
        {"op": "width", "value": "half"},
    ):
        _resp, msgs = b.post(seite=code, ref=ref, **data)
        assert msgs == ["Diese Änderung ist hier nicht möglich."], data
    b.post(seite=code, op="save")
    tenant.refresh_from_db()
    assert "Jetzt kaufen" not in json.dumps(tenant.site_config)
    assert not (b.session.get("aufbau_draft") or {}).get(code)


def _cart_body(tenant, settings):
    from apps.orders import public_views
    from apps.orders.tests.test_quote_cart import _filled_cart, _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    cart = _filled_cart(tenant)
    return public_views.cart_view(
        _req(method="get", session={"cart": cart}, tenant=tenant)
    ).content.decode()


@pytest.mark.parametrize("quote", [False, True])
def test_window_label_equals_the_storefront_cart_button(quote, settings):
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(site_config={"quote_cart": True} if quote else {})
    with translation.override("de"):
        body = _cart_body(tenant, settings)
        label = legal_buttons.label("cart", "summary", tenant.site_config)
    buttons = re.findall(r'<button type="submit" form="checkout-form"[^>]*>([^<]*)</button>', body)
    assert buttons == [label]


def test_window_label_equals_the_booking_and_gift_buttons(settings):
    import uuid
    from datetime import datetime, timedelta

    settings.ROOT_URLCONF = "config.urls_tenant"
    start = datetime(2026, 11, 2, 12, 0)
    with translation.override("de"):
        body = render_to_string(
            "storefront/_booking_slots_box.html",
            {
                "resource": SimpleNamespace(pk=uuid.uuid4()),
                "selected": (start, start + timedelta(hours=1)),
                "service": SimpleNamespace(price_cents=2500),
            },
            request=RequestFactory().get("/"),
        )
        assert legal_buttons.label("service_detail", "__kauf") in body
        gift = (TEMPLATES / "storefront/gift_voucher.html").read_text()
        button = re.search(r'<button type="submit"[^>]*>\{% trans "([^"]+)" %\}</button>', gift)
        assert button.group(1) == legal_buttons.label("gift", "form")


def test_legal_texts_are_translated_and_nothing_stores_a_label():
    src = (Path(__file__).resolve().parents[3] / "apps/core/legal_buttons.py").read_text()
    assert "gettext as _" in src and "site_config" not in src.split('"""', 2)[2]
    for name in ("cart.html", "gift_voucher.html", "_booking_slots_box.html"):
        tpl = (TEMPLATES / "storefront" / name).read_text()
        assert "legal_label" not in tpl and "button_label" not in tpl, name
