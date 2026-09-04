"""SF-2: PromoFacets — системные фильтры/поиск/сортировка листинга акций.

Особенность провайдера: реальная скидка живёт не в БД (свойства new_price/
discount_percent_display поверх discount_percent | price_override/compare_at |
base_price товара), поэтому «−N %+» и сортировки — in-memory; листинг не
пагинируется, материализация штатная.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug):
    return TenantFactory(schema_name="public", slug=slug, name="PF")


def _body(tenant, params=None):
    req = RequestFactory().get("/aktionen/", params or {})
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


def _promo(title, **kw):
    return Promotion.objects.create(title={"de": title}, status="active", **kw)


def test_endet_filters_by_window():
    t = _tenant("pf1")
    now = timezone.now()
    # Фильтр «heute» отсекает по МЕСТНОЙ полуночи, поэтому «сейчас + 2 часа»
    # после 22:00 уезжало на завтра и тест краснел каждый вечер (флак по
    # времени суток, не регрессия). Берём конец текущего локального дня.
    heute_ends = timezone.localtime(now).replace(hour=23, minute=59, second=59, microsecond=0)
    _promo("HeuteDeal", ends_at=heute_ends)
    _promo("WocheDeal", ends_at=now + timedelta(days=5))
    _promo("SpaeterDeal", ends_at=now + timedelta(days=30))
    _promo("EwigDeal")

    heute = _body(t, {"endet": "heute"})
    assert "HeuteDeal" in heute
    assert "WocheDeal" not in heute and "EwigDeal" not in heute

    woche = _body(t, {"endet": "woche"})
    assert "HeuteDeal" in woche and "WocheDeal" in woche
    assert "SpaeterDeal" not in woche

    # мусорное значение = фильтра нет
    alle = _body(t, {"endet": "morgen"})
    assert "EwigDeal" in alle


def test_rabatt_filter_uses_price_derived_percent():
    t = _tenant("pf2")
    # скидка задана процентом
    _promo("Feld40", discount_percent=40)
    # скидка выводится из цен: 10 → 7.50 = 25 %
    _promo(
        "Preis25",
        compare_at_price=Decimal("10.00"),
        price_override=Decimal("7.50"),
    )
    _promo("OhneRabatt")

    body = _body(t, {"rabatt": "30"})
    assert "Feld40" in body
    assert "Preis25" not in body and "OhneRabatt" not in body

    body20 = _body(t, {"rabatt": "20"})
    assert "Feld40" in body20 and "Preis25" in body20 and "OhneRabatt" not in body20

    # не-пресетное значение отбрасывается (fail-closed валидация)
    assert "OhneRabatt" in _body(t, {"rabatt": "1"})


def test_reservierbar_filter_and_search():
    t = _tenant("pf3")
    _promo("ReserveMich", promo_type="reservation", available_quantity=5)
    _promo("NurRabatt", promo_type="discount", discount_percent=10)

    body = _body(t, {"reservierbar": "1"})
    assert "ReserveMich" in body and "NurRabatt" not in body

    # поиск по title (JSON-i18n) — и в связке с фильтром
    found = _body(t, {"q": "reserve"})
    assert "ReserveMich" in found and "NurRabatt" not in found


def test_sort_endet_and_rabatt():
    t = _tenant("pf4")
    now = timezone.now()
    # уникальные токены: «Bald» столкнулся бы с подписью сортировки «Endet bald»
    # (класс MEN: пробные строки в замках — только уникальные)
    _promo("Xbald", ends_at=now + timedelta(days=1), discount_percent=10)
    _promo("Xspaet", ends_at=now + timedelta(days=6), discount_percent=50)
    _promo("Xewig", discount_percent=30)

    body = _body(t, {"sort": "endet"})
    assert body.index("Xbald") < body.index("Xspaet") < body.index("Xewig")

    body = _body(t, {"sort": "rabatt"})
    assert body.index("Xspaet") < body.index("Xewig") < body.index("Xbald")


def test_filtered_view_shows_count_and_reset_on_empty():
    t = _tenant("pf5")
    _promo("Eins", discount_percent=40)
    _promo("Zwei", discount_percent=40)

    body = _body(t, {"rabatt": "30"})
    assert "data-result-count" in body  # «N Angebote» при активном фильтре

    empty = _body(t, {"rabatt": "50"})
    assert "data-result-count" in empty
    assert "storefront-aktionen" not in empty or "?“" not in empty  # сброс — голый URL
    assert "text-indigo-600" in empty  # ссылка «Filter zurücksetzen»

    # чистый вид — без счётчика
    assert "data-result-count" not in _body(t)


def test_ending_soon_strip_only_on_clean_view():
    t = _tenant("pf6")
    now = timezone.now()
    _promo("FastVorbei", ends_at=now + timedelta(days=1))
    _promo("Normal")

    body = _body(t)
    assert "data-ending-soon" in body

    # с фильтром полосы нет; без подходящих акций — тоже нет
    assert "data-ending-soon" not in _body(t, {"endet": "woche"})
    Promotion.objects.filter(ends_at__isnull=False).delete()
    assert "data-ending-soon" not in _body(t)


def test_system_chips_carry_other_params():
    t = _tenant("pf7")
    _promo("Deal", group="Wochenangebote", discount_percent=30)
    _promo("Deal2", group="Wochenangebote", discount_percent=30)

    body = _body(t, {"gruppe": "Wochenangebote"})
    # чип «−30 %+» несёт выбранную группу (carry), активный чип endet — нет
    assert "gruppe=Wochenangebote" in body and "rabatt=30" in body
    # тулбар сортировки несёт активные фасеты hidden-полями
    assert '<input type="hidden" name="gruppe" value="Wochenangebote">' in body


def test_system_chip_is_not_offered_when_it_leads_to_an_empty_page():
    """Стенд аутлета: чип «Endet heute» предлагался, а акций, истекающих сегодня,
    не было — клик уводил на пустую страницу. Фильтр-тупик читается как «в
    магазине пусто», хотя это лишь нерелевантный срез (то же правило, что у
    `nur_angebote` в каталоге: предлагаем, только если есть что показать)."""
    t = _tenant("pf8")
    _promo("Läuft lange", discount_percent=20, ends_at=timezone.now() + timedelta(days=30))

    body = _body(t)
    assert "endet=woche" not in body  # через месяц — не «на этой неделе»
    assert "endet=heute" not in body
    assert "rabatt=20" in body  # чип, у которого выдача есть, остаётся

    # у акции, истекающей сегодня, чип появляется
    _promo("Heute vorbei", discount_percent=20, ends_at=timezone.now() + timedelta(hours=2))
    assert "endet=heute" in _body(t)


def test_active_system_chip_stays_offered_so_it_can_be_switched_off():
    """Гейт не должен запирать посетителя: даже если срез пуст, активный чип
    остаётся на странице — иначе снять его можно только правкой адреса."""
    t = _tenant("pf9")
    _promo("Läuft lange", discount_percent=20, ends_at=timezone.now() + timedelta(days=30))
    body = _body(t, {"endet": "heute"})
    assert "Endet heute" in body or "Ends today" in body
