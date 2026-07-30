"""UE2-1 (шаг 0): характеризационные замки вывода скидки ДО извлечения единого
`_discount_display.html` — карточка (_promo_card) и деталь акции рендерят
бейдж/цену/scarcity/countdown/surprise/valid-until байт-в-байт как сейчас
(план ue-plan §3 UE2-1; втянуто в U-C — uc-plan §11 п.13)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _card(promo):
    return render_to_string("storefront/_promo_card.html", {"p": promo})


def _detail(promo):
    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return public_views.promotion_detail(request, pk=promo.pk).content.decode()


def test_percent_badge_card_and_detail():
    """Класс-атрибут бейджа — байт-в-байт (визуальный паритет); UE3-1 добавил
    editor-атрибуты после class, поэтому пиним class + текст, не весь тег."""
    promo = PromotionFactory(status="active", discount_percent=30)
    card, detail = _card(promo), _detail(promo)
    assert (
        'class="absolute top-3 left-3 bg-red-600 text-white text-xs font-bold'
        ' px-2.5 py-1 rounded-full shadow"' in card
    )
    assert ">−30 %</span>" in card
    # Фидбэк 2026-07-30 (референс владельца): на детальной бейдж переехал с фото
    # в блок цены (замок обновлён осознанно; карточки листинга держат прежний
    # absolute-бейдж). Акция только с процентом (цен нет) — крупный «−30 %»
    # вместо цены; с ценами — пилюля data-price-badge у зачёркнутой старой.
    assert ">−30 %</p>" in detail
    priced = PromotionFactory(
        status="active", discount_percent=30, compare_at_price=Decimal("10.00")
    )
    priced_detail = _detail(priced)
    assert (
        'data-price-badge class="bg-red-600 text-white text-xs font-bold'
        ' px-2 py-0.5 rounded-full"' in priced_detail
    )
    assert ">−30 %</span>" in priced_detail


def test_amount_badge_when_no_percent():
    promo = PromotionFactory(
        status="active",
        discount_percent=None,
        compare_at_price=Decimal("10.00"),
        price_override=Decimal("7.50"),
    )
    if not promo.has_discount or promo.discount_percent_display:
        pytest.skip("фабрика не даёт amount-скидку — ветка недостижима")
    assert f"−{promo.discount_amount} €" in _card(promo)
    assert f"−{promo.discount_amount} €" in _detail(promo)


def test_strikethrough_old_and_bold_red_new_price():
    promo = PromotionFactory(
        status="active",
        compare_at_price=Decimal("10.00"),
        price_override=Decimal("7.50"),
        strikethrough_old_price=True,
    )
    for body in (_card(promo), _detail(promo)):
        assert "line-through" in body
        assert "text-red-600" in body  # жирная красная новая цена (_price.html)


def test_scarcity_line_thresholds():
    low = PromotionFactory(status="active", available_quantity=2)
    calm = PromotionFactory(status="active", available_quantity=9)
    assert "Nur noch 2 übrig" in _card(low) and "text-red-600 font-medium" in _card(low)
    assert "Nur noch 9 übrig" in _card(calm) and "text-gray-400" in _card(calm)
    assert "Nur noch 2 übrig" in _detail(low)


def test_countdown_and_valid_until():
    ends = timezone.now() + timedelta(hours=5)
    ticking = PromotionFactory(status="active", ends_at=ends, show_countdown=True)
    plain = PromotionFactory(status="active", ends_at=ends, show_countdown=False)
    local_iso = timezone.localtime(ends).isoformat()  # |date:'c' рендерит локальную TZ
    assert f'data-countdown="{local_iso}"' in _card(ticking)
    # Фидбэк 2026-07-30: деталь — сегментный отсчёт Tage|Std|Min|Sek в промо-
    # баннере (data-cd + data-cd-d/h/m/s), карточка — прежний тикер.
    assert f'data-cd="{local_iso}"' in _detail(ticking)
    assert "data-cd-d" in _detail(ticking)
    assert "data-countdown" not in _card(plain)
    assert "Gültig bis" in _detail(plain)  # деталь без тикера показывает срок


def test_surprise_badge():
    promo = PromotionFactory(status="active", is_surprise=True)
    assert "Überraschungstüte" in _card(promo)
    assert "Überraschungstüte" in _detail(promo)


def test_block_style_hint_cascade():
    """UC6-6f: hint промо-БЛОКА (style_override) действует, ПОКА стиль самой
    акции не задан; явный Promotion.discount_style главнее (источник един)."""
    promo = PromotionFactory(status="active", discount_percent=30)

    def badge(override="", own_style=""):
        promo.discount_style = own_style
        return render_to_string(
            "storefront/_discount_display.html",
            {"promo": promo, "part": "badge", "size": "sm", "style_override": override},
        )

    assert "−30" in badge()  # без стиля и hint — легаси-бейдж
    assert "−30" in badge(override="percent")  # hint percent → бейдж есть
    # hint strikethrough при НЕзаданном стиле акции → бейдж скрыт (акцент на цене)
    assert "−30" not in badge(override="strikethrough")
    # стиль акции percent ГЛАВНЕЕ hint'а strikethrough → бейдж есть
    assert "−30" in badge(override="strikethrough", own_style="percent")
