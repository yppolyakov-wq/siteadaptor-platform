"""FB-33 M2h-0: характеризация корзины-оформления ДО строк `items`/`form`/`summary`.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2h». Снимки сняты до кода M2h: без своих
строк страница корзины рисуется байт-в-байт как раньше (и со старыми строками блоков).
Замок § 312j BGB: между итогом и кнопкой заказа нет ни одного своего блока — при любых строках.

Обновить (осознанно): FB33M2H_GOLDEN=update uv run pytest <этот файл>
"""

import os
from pathlib import Path

import pytest
from django.utils import translation

from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2h"
UPDATE = os.environ.get("FB33M2H_GOLDEN") == "update"
frozen_now = _p5.frozen_now


def _text(bid, body):
    return {"key": "text", "id": bid, "enabled": True, "data": {"title": "", "body": body}}


TOP, HINT, MID, TAIL = (
    _text("t-top", "BLOCK-TOP"),
    _text("t-hint", "BLOCK-HINT"),
    _text("t-mid", "BLOCK-MID"),
    _text("t-tail", "BLOCK-TAIL"),
)


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _check(name, got):
    path = GOLDEN / f"{name}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2H_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"корзина изменилась: {path.name}"


def cart_html(cfg, *, table=False, empty=False):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views

    item = ProductFactory(name={"de": "Bauernbrot"})
    for i in range(4):
        ProductFactory(name={"de": f"Dazu {i}"})
    req = _p5._req("/warenkorb/", cfg)
    if not empty:
        req.session["cart"] = {str(item.pk): 1}
    if table:
        req.session["table"] = "7"
    return public_views.cart_view(req).content.decode()


CASES = {
    "bare": ({}, {}),
    "quote": ({"quote_cart": True}, {}),
    "table": ({}, {"table": True}),
    "empty": ({}, {"empty": True}),
    "empty-blocks": ({"page_blocks": {"cart": [TAIL]}}, {"empty": True}),
    "blocks-only": ({"page_blocks": {"cart": [MID, TAIL]}}, {}),
    "above-upsell": ({"page_blocks": {"cart": [MID, {"key": "upsell"}]}}, {}),
    "upsell-hidden": (
        {"cart_show_upsell": False, "page_blocks": {"cart": [MID, {"key": "upsell"}]}},
        {},
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_cart_before(case):
    cfg, kw = CASES[case]
    _check(f"cart-{case}", _p5._normalize(cart_html(cfg, **kw)))


def test_cart_before_ru():
    with translation.override("ru"):
        _check("cart-bare-ru", _p5._normalize(cart_html({})))


#: строки, которые может сохранить схема (и старые, и с неподвижными строками M2h)
ROWS_312J = {
    "old": [TOP, {"key": "upsell"}, TAIL],
    "all": [
        TOP,
        {"key": "items"},
        HINT,
        {"key": "form"},
        MID,
        {"key": "summary"},
        _text("t-sum", "BLOCK-SUM"),
        {"key": "upsell"},
        TAIL,
    ],
    "summary-first": [{"key": "summary"}, MID, {"key": "items"}, HINT, {"key": "upsell"}],
}


@pytest.mark.parametrize("case", sorted(ROWS_312J))
@pytest.mark.parametrize("quote", [False, True])
def test_no_block_between_summary_and_order_button(case, quote):
    """§ 312j BGB: кнопка заказа — сразу после итога; свои блоки туда не попадают."""
    cfg = {"page_blocks": {"cart": ROWS_312J[case]}, "quote_cart": quote}
    html = cart_html(cfg)
    start = html.index('id="order-summary"')
    label = "Unverbindlich anfragen" if quote else "Zahlungspflichtig bestellen"
    end = html.index(label, start)
    between = html[start:end]
    assert "BLOCK-" not in between
    assert between.count("<button") == 1, "кнопка заказа — первая после итога"
    assert html.count(label) == 1
