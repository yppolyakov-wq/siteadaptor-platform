"""SF-6 (фидбэк владельца 2026-09-03): «на русском положение картинки меняется,
хотя на немецком нет».

Причина: в форме карточки «Preis zuerst» плашка цены стоит НАД фото, а её высота
зависела от того, переносится ли строка «цена · statt · бейдж» и есть ли мета-строка
(Grundpreis / Sie sparen). На немецком часть карточек ряда была 69 px, часть 91 px;
на длинных локалях (ru/uk) картина менялась ещё сильнее — стенд Playwright показывал
mediaTop {43, 69, 91} у de и {14, 63, 69, 91} у ru. Замок держит резерв высоты:
разметка одинакова на всех языках, поэтому фото у карточек ряда на одном уровне.
"""

from __future__ import annotations

import re

import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db

PRICE_ROW_RESERVE = "min-h-[3.125rem] md:min-h-[3.375rem]"
META_ROW_RESERVE = "min-h-[0.875rem]"


def _card(promo, locale="de"):
    with translation.override(locale):
        return render_to_string(
            "storefront/_promo_card.html", {"p": promo, "storefront_promo_card": "preis"}
        )


def _promo(**kw):
    return Promotion(
        title={"de": "Deal"},
        status="active",
        price_override=kw.pop("price", "1.99"),
        compare_at_price=kw.pop("old", "2.99"),
        **kw,
    )


def test_price_block_reserves_height_above_the_photo():
    html = _card(_promo())
    block = re.search(
        r"<div[^>]*data-promo-price-block[^>]*>(.*?)<div[^>]*data-sf-media-box", html, re.S
    )
    assert block, "плашка цены должна стоять НАД фото (форма Preis zuerst)"
    body = block.group(1)
    assert PRICE_ROW_RESERVE in body, "строка цены без резерва под перенос «statt …»"
    assert META_ROW_RESERVE in body, "мета-строка должна занимать место и когда пуста"


def test_reserve_is_the_same_on_every_locale():
    """Перевод меняет ТЕКСТ, а не структуру плашки: резерв на месте на всех языках."""
    promo = _promo()
    for loc in ("de", "en", "ru", "uk", "tr"):
        html = _card(promo, loc)
        assert html.count(PRICE_ROW_RESERVE) == 1 and html.count(META_ROW_RESERVE) == 1, loc


def test_reserve_holds_for_a_card_without_meta_line():
    """Mystery/акция без Grundpreis и без «Sie sparen»: мета пуста — раньше плашка
    была на 26 px ниже, и фото уезжало вверх относительно соседей."""
    html = _card(_promo(discount_style="mystery"))
    assert PRICE_ROW_RESERVE in html and META_ROW_RESERVE in html
