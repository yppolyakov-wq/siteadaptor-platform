"""Фидбэк 2026-07-29: явные типы акций — чипы механики на карточке
(reservieren/повтор/Neu/срок), секции групп на /aktionen/, «Sie sparen» на
детальной. Владелец на демо aktionsmarkt не мог отличить типы акций друг от
друга — механика была видна только из текста заголовка."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions.models import Promotion
from apps.promotions.public_views import promotion_detail, promotion_list
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/aktionen/", data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="grocery")
    return request


def _flags_promo(**kw):
    defaults = {
        "title": {"de": "Testaktion"},
        "status": "active",
        "promo_type": Promotion.DISCOUNT,
        "starts_at": timezone.now() - timedelta(days=30),  # не «Neu»
        "discount_percent": 10,
    }
    defaults.update(kw)
    return Promotion.objects.create(**defaults)


def test_promo_card_flags_show_mechanics():
    """Чипы механики: резервируемость / повторяемость / новизна / срок действия
    видны на карточке (раньше — только из текста заголовка)."""
    _flags_promo(
        title={"de": "Reservierbar"},
        promo_type=Promotion.RESERVATION,
        available_quantity=5,
        recurrence="weekly",
        ends_at=timezone.now() + timedelta(days=7),
        show_countdown=False,
    )
    body = promotion_list(_req()).content.decode()
    assert "Online reservieren, im Laden abholen" in body  # 📦 механика брони
    assert "Jede Woche" in body  # 🔁 повторяемость
    assert "bis " in body  # 📅 срок действия (не-countdown)
    # свежая акция → «Neu»
    _flags_promo(title={"de": "Frisch"}, starts_at=timezone.now())
    body2 = promotion_list(_req()).content.decode()
    assert "🆕" in body2


def test_promotion_list_grouped_sections_and_filter():
    """Группы — секциями с заголовками (безгрупповые в конце под «Weitere
    Angebote»); выбранный фильтр — плоская сетка без секций."""
    _flags_promo(title={"de": "A1"}, group="Wochenangebote")
    _flags_promo(title={"de": "B1"}, group="Räumung")
    _flags_promo(title={"de": "C1"})  # без группы
    body = promotion_list(_req()).content.decode()
    assert "Wochenangebote" in body and "Räumung" in body
    assert "Weitere Angebote" in body  # безгрупповая секция
    assert body.index("Weitere Angebote") > body.index("Räumung")  # в конце
    flat = promotion_list(_req(data={"gruppe": "Räumung"})).content.decode()
    assert "Weitere Angebote" not in flat and "B1" in flat and "A1" not in flat


def test_promotion_detail_shows_savings():
    """Рынок DACH: «Sie sparen X €» на детальной при скидке со сравнимой ценой."""
    promo = _flags_promo(
        title={"de": "Sparen"},
        price_override=Decimal("2.00"),
        compare_at_price=Decimal("4.00"),
        discount_percent=None,
    )
    body = promotion_detail(_req(f"/p/{promo.pk}/"), pk=promo.pk).content.decode()
    assert "Sie sparen" in body and "2.00" in body


def test_promotion_detail_modal_and_gallery():
    """Фидбэк 2026-07-29 (№2): форма брони — в попапе за CTA (в DOM всегда —
    паритет-замок buybox цел), при ошибках формы модал открыт; галерея-миниатюры
    под главным фото при >1 изображении."""
    promo = _flags_promo(
        title={"de": "Popup"},
        promo_type=Promotion.RESERVATION,
        available_quantity=5,
        images=[
            {"id": "a", "url": "/static/demo/a.webp", "is_primary": True},
            {"id": "b", "url": "/static/demo/b.webp"},
        ],
    )
    body = promotion_detail(_req(f"/p/{promo.pk}/"), pk=promo.pk).content.decode()
    # CTA открывает модал; сам модал скрыт (hidden), но форма брони — в DOM
    assert 'data-modal-open="promo-reserve-modal"' in body
    assert 'id="promo-reserve-modal" class="fixed inset-0 z-50 hidden"' in body
    assert f"/p/{promo.pk}/kaufen/" in body  # форма внутри модала (P5: стандартный заказ)
    # галерея: две миниатюры со свапом (атрибут+data-full; в JS селекторы тоже
    # содержат имя атрибута — считаем по разметке кнопки)
    assert body.count("data-gallery-thumb data-full") == 2
    assert "data-gallery-main" in body
    # sold-out → CTA становится «Benachrichtigen»
    promo.available_quantity = 0
    promo.save(update_fields=["available_quantity"])
    body2 = promotion_detail(_req(f"/p/{promo.pk}/"), pk=promo.pk).content.decode()
    assert "🔔" in body2 and f"/p/{promo.pk}/waitlist/" in body2


def test_promotion_detail_modal_opens_on_form_errors():
    """POST с ошибками ре-рендерит страницу — модал должен быть ОТКРЫТ
    (без hidden), иначе покупатель не увидит ошибку."""
    from apps.promotions.public_views import reservation_create

    promo = _flags_promo(
        title={"de": "Fehler"}, promo_type=Promotion.RESERVATION, available_quantity=5
    )
    request = RequestFactory().post(f"/p/{promo.pk}/reserve/", {"name": ""})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="grocery")
    body = reservation_create(request, pk=promo.pk).content.decode()
    assert 'id="promo-reserve-modal" class="fixed inset-0 z-50 "' in body  # открыт
