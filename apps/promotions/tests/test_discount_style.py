"""UE2-2: селектор `Promotion.discount_style` ветвит вывод скидки в едином
`_discount_display.html` — default "" сохраняет легаси-вид (замки parity),
именованные стили меняют бейдж/цену/countdown на карточке И детали.
Только презентация: свойства цены/has_discount не зависят от стиля."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.forms import PromotionForm
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db

BADGE_MARK = "rounded-full shadow"  # присутствует только в бейдже скидки


def _card(promo):
    return render_to_string("storefront/_promo_card.html", {"p": promo})


def _detail(promo):
    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return public_views.promotion_detail(request, pk=promo.pk).content.decode()


def _discounted(**kwargs):
    return PromotionFactory(
        status="active",
        compare_at_price=Decimal("10.00"),
        price_override=Decimal("7.50"),
        **kwargs,
    )


def test_percent_style_forces_percent_badge():
    promo = _discounted(discount_style="percent")
    card, detail = _card(promo), _detail(promo)
    assert "−25 %" in card  # 10 → 7.50
    assert "€</span>" not in card.split(BADGE_MARK)[1][:60]  # бейдж не −€
    # деталь (2026-07-30, референс): пилюля у зачёркнутой цены — процент, не −€
    assert ">−25 %</span>" in detail.split("data-price-badge")[1][:120]


def test_badge_style_forces_amount_badge_even_with_percent():
    promo = _discounted(discount_style="badge", discount_percent=None)
    for body in (_card(promo), _detail(promo)):
        assert "−2,50 €" in body  # DE-локаль: запятая
        # именно БЕЙДЖ процента скрыт; строка выгоды «Sie sparen … (−25 %)»
        # (фидбэк 2026-07-29) легитимна и стилем не управляется
        assert ">−25 %</span>" not in body


def test_strikethrough_style_hides_badge_keeps_struck_price():
    promo = _discounted(discount_style="strikethrough", strikethrough_old_price=True)
    for body in (_card(promo), _detail(promo)):
        assert BADGE_MARK not in body  # бейджа нет
        assert "line-through" in body  # зачёркнутая старая цена осталась


def test_festpreis_style_only_new_price():
    promo = _discounted(discount_style="festpreis")
    for body in (_card(promo), _detail(promo)):
        assert BADGE_MARK not in body
        assert "line-through" not in body
        assert "7,50" in body  # только новая цена (DE-локаль)


def test_ab_style_from_price_prefix():
    promo = _discounted(discount_style="ab")
    for body in (_card(promo), _detail(promo)):
        assert BADGE_MARK not in body
        assert "line-through" not in body
        assert "ab" in body and "7,50" in body


def test_countdown_style_forces_timer_without_flag():
    ends = timezone.now() + timedelta(hours=5)
    promo = _discounted(discount_style="countdown", ends_at=ends, show_countdown=False)
    local_iso = timezone.localtime(ends).isoformat()
    card, detail = _card(promo), _detail(promo)
    assert BADGE_MARK not in card
    assert f'data-countdown="{local_iso}"' in card
    # деталь (2026-07-30, референс): сегментный баннер Tage|Std|Min|Sek
    assert BADGE_MARK not in detail
    assert f'data-cd="{local_iso}"' in detail
    assert "data-cd-d" in detail


def test_surprise_style_hides_badge_keeps_pill():
    promo = _discounted(discount_style="surprise", is_surprise=True)
    assert BADGE_MARK not in _card(promo)
    assert "Überraschungstüte" in _card(promo)
    assert "Überraschungstüte" in _detail(promo)


def test_default_style_is_legacy_view():
    """Default "" — легаси: %-бейдж + strikethrough (полный паритет — замки
    test_discount_display_parity)."""
    promo = _discounted(discount_style="")
    body = _card(promo)
    assert "−25 %" in body and "line-through" in body


def test_form_has_style_selector_and_price_props_untouched():
    assert "discount_style" in PromotionForm.Meta.fields
    promo = _discounted(discount_style="festpreis")
    # презентация не влияет на цену/скидку (анти-оверселл/price-логика целы)
    assert promo.has_discount is True
    assert promo.new_price == Decimal("7.50")
    assert promo.discount_amount == Decimal("2.50")


def test_mystery_style_hides_price_and_blurs_photo():
    """UE2-3: mystery — цена скрыта (data-mystery-price hidden), фото в blur,
    кнопка-reveal (a11y <button>); бейджа нет. Механика брони не зависит."""
    promo = _discounted(
        discount_style="mystery",
        images=[{"id": "x", "url": "/x.png", "is_primary": True}],
    )
    for body in (_card(promo), _detail(promo)):
        assert BADGE_MARK not in body
        assert "data-mystery-price" in body and "hidden" in body
        assert "data-mystery-reveal" in body
        assert "data-mystery-root" in body
        assert "blur-lg" in body and "data-mystery-blur" in body


def test_non_mystery_has_no_reveal_artifacts():
    promo = _discounted(images=[{"id": "x", "url": "/x.png", "is_primary": True}])
    body = _card(promo)
    assert "data-mystery" not in body and "blur-lg" not in body


def test_mystery_hides_savings_and_metadata_leaks():
    """SF-1.4: до reveal не светим выгоду/PAngV/og-фото/цену в JSON-LD — по
    «Sie sparen 2,50 € (−25 %)» скрытая цена восстанавливалась арифметикой,
    og:image показывал неразмытое фото в превью ссылки, Offer клал цену в
    исходник, миниатюры галереи шли без блюра."""
    promo = _discounted(
        discount_style="mystery",
        images=[
            {"id": "x", "url": "/x.png", "is_primary": True},
            {"id": "y", "url": "/y.png"},
        ],
    )
    body = _detail(promo)
    # выгода в DOM, но внутри скрытой mystery-обёртки (появится по reveal)
    assert "data-mystery-extra" in body
    extra = body.split("data-mystery-extra")[1].split("</div>")[0]
    assert "Sie sparen" in extra or "You save" in extra
    # блюр и на главной, и на миниатюрах галереи
    assert body.count("data-mystery-blur") >= 3
    # метаданные не выдают секрет
    assert 'property="og:image"' not in body
    assert '"offers"' not in body
    # root несёт pk — ключ sessionStorage-персиста reveal (SF-1.5)
    assert f'data-mystery-root="{promo.pk}"' in body
    assert f'data-mystery-root="{promo.pk}"' in _card(promo)


def test_non_mystery_detail_keeps_savings_offer_and_og():
    """Обратная сторона SF-1.4: обычная акция ничего не теряет."""
    promo = _discounted(images=[{"id": "x", "url": "/x.png", "is_primary": True}])
    body = _detail(promo)
    assert "data-mystery-extra" not in body
    assert '"offers"' in body
    assert 'property="og:image"' in body
