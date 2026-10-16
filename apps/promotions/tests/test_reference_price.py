"""SF-7 (§11 PAngV, EuGH C-330/23, BGH I ZR 183/24): объявленное снижение — от
низшей цены 30 дней ДО старта акции, а не от «обычной» цены, которую можно поднять."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import PriceLog, Product
from apps.promotions import reference_price
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db


def _product(price, *, logged_days_ago=40):
    p = Product.objects.create(name={"de": "Kaffee"}, base_price=Decimal(price))
    PriceLog.objects.filter(product=p).update(
        created_at=timezone.now() - timedelta(days=logged_days_ago)
    )
    return p


def _raise(product, price, *, days_ago):
    product.base_price = Decimal(price)
    product.save()
    PriceLog.objects.filter(product=product, price=Decimal(price)).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


def _promo(product=None, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    return Promotion.objects.create(title={"de": "Aktion"}, product=product, **kw)


def test_stable_price_keeps_owner_percent():
    p = _product("10.00")
    promo = _promo(p, discount_percent=20)
    assert promo.old_price == Decimal("10.00")
    assert promo.new_price == Decimal("8.00")
    assert promo.discount_percent_display == 20
    assert promo.reference_capped is False


def test_mondpreis_raised_before_promo_is_capped():
    """Подняли цену с 8 до 10 за неделю до акции −20 %: «statt 10 €, −20 %» незаконно."""
    p = _product("8.00")
    _raise(p, "10.00", days_ago=7)
    promo = _promo(p, discount_percent=20)
    assert promo.new_price == Decimal("8.00")  # продаём по-прежнему по 8 €
    assert promo.lowers_price is True  # ценовой слой (корзина) работает
    assert promo.old_price == Decimal("8.00")
    assert promo.has_discount is False  # но снижение объявлять нельзя
    assert promo.discount_percent_display is None
    assert promo.discount_amount is None
    assert promo.reference_capped is True


def test_inflated_compare_at_price_is_capped_and_percent_recomputed():
    p = _product("10.00")
    promo = _promo(p, compare_at_price=Decimal("15.00"), price_override=Decimal("7.50"))
    assert promo.old_price == Decimal("10.00")
    assert promo.discount_percent_display == 25  # от 10 €, не 50 % от 15 €
    assert promo.discount_amount == Decimal("2.50")


def test_repeated_weekly_promo_counts_as_applied_price():
    """Недельная акция подряд: прошлая цена 7 € в окне → «statt 10 €» уже нельзя."""
    p = _product("10.00")
    _promo(
        p,
        status="ended",
        price_override=Decimal("7.00"),
        starts_at=timezone.now() - timedelta(days=14),
        ends_at=timezone.now() - timedelta(days=7),
    )
    promo = _promo(p, price_override=Decimal("7.00"))
    assert promo.old_price == Decimal("7.00")
    assert promo.has_discount is False


def test_old_promo_outside_window_and_drafts_ignored():
    p = _product("10.00")
    _promo(
        p,
        status="ended",
        price_override=Decimal("5.00"),
        starts_at=timezone.now() - timedelta(days=60),
        ends_at=timezone.now() - timedelta(days=45),
    )
    _promo(p, status="draft", price_override=Decimal("4.00"), starts_at=timezone.now())
    promo = _promo(p, price_override=Decimal("8.00"))
    assert promo.old_price == Decimal("10.00")
    assert promo.discount_percent_display == 20


def test_window_is_anchored_to_promo_start_not_now():
    """Цену подняли уже ПОСЛЕ старта акции — на цену сравнения это не влияет."""
    p = _product("10.00")
    promo = _promo(p, price_override=Decimal("8.00"), starts_at=timezone.now() - timedelta(days=3))
    _raise(p, "12.00", days_ago=1)
    promo = Promotion.objects.get(pk=promo.pk)
    assert promo.old_price == Decimal("10.00")


def test_free_promo_and_percent_only_promo_unchanged():
    free = _promo(None, compare_at_price=Decimal("5.00"), price_override=Decimal("4.00"))
    assert free.old_price == Decimal("5.00") and free.discount_percent_display == 20
    everything = _promo(None, discount_percent=20)
    assert everything.discount_percent_display == 20  # «−20 % auf alles»


def test_bulk_attach_matches_single_and_is_batched(django_assert_max_num_queries):
    p1 = _product("8.00")
    _raise(p1, "10.00", days_ago=5)
    p2 = _product("20.00")
    a = _promo(p1, discount_percent=20)
    b = _promo(p2, discount_percent=10)
    fresh = list(Promotion.objects.filter(pk__in=[a.pk, b.pk]).select_related("product"))
    with django_assert_max_num_queries(3):
        reference_price.attach(fresh)
    by_pk = {x.pk: x for x in fresh}
    assert by_pk[a.pk].old_price == Decimal("8.00")
    assert by_pk[b.pk].old_price == Decimal("20.00")


def test_product_card_attrs_follow_reference_price():
    from apps.promotions.price_layer import attach_promos

    p = _product("8.00")
    _raise(p, "10.00", days_ago=7)
    _promo(p, discount_percent=20)
    (card,) = attach_promos([Product.objects.get(pk=p.pk)])
    assert card.promo_price == Decimal("8.00")  # корзина продаёт по акции
    assert card.promo_old is None  # но без зачёркнутой цены
    assert card.promo_savings is None
    assert "%" not in str(card.promo_badge)

    q = _product("10.00")
    _promo(q, discount_percent=20)
    (card,) = attach_promos([Product.objects.get(pk=q.pk)])
    assert card.promo_old == Decimal("10.00")
    assert card.promo_savings == Decimal("2.00")
    assert card.promo_badge == "−20 %"


def test_city_catalog_snapshot_drops_unlawful_old_price():
    from apps.aggregator.tasks import _snapshot

    p = _product("8.00")
    _raise(p, "10.00", days_ago=7)
    promo = _promo(p, discount_percent=20)
    snap = _snapshot(promo.pk)
    assert snap["new_price"] == Decimal("8.00")
    assert snap["old_price"] is None
    assert snap["discount_percent"] is None


def test_services_are_not_capped():
    """§11 PAngV — про Waren; у услуги прежнее поведение (история не нужна)."""
    from apps.booking.models import Service

    svc = Service.objects.create(name="Schnitt", duration_minutes=30, price_cents=3000)
    promo = _promo(
        None, service=svc, compare_at_price=Decimal("30.00"), price_override=Decimal("24.00")
    )
    assert promo.old_price == Decimal("30.00")
    assert promo.discount_percent_display == 20


def test_manual_activation_stamps_starts_at_so_window_sees_price_raise():
    """Ревью H1: черновик без расписания → окно считается от АКТИВАЦИИ, не от
    создания — повышение цены между ними попадает в минимум."""
    from apps.promotions.state_machine import PromotionSM

    p = _product("8.00")
    promo = _promo(p, status="draft", starts_at=None, discount_percent=20)
    Promotion.objects.filter(pk=promo.pk).update(created_at=timezone.now() - timedelta(days=40))
    _raise(p, "10.00", days_ago=2)
    promo = Promotion.objects.get(pk=promo.pk)
    PromotionSM().apply(promo, "active")
    assert promo.starts_at is not None
    assert promo.old_price == Decimal("8.00")
    assert promo.has_discount is False


def test_soft_deleted_past_promo_still_counts():
    """Ревью M2: удаление прошлой дешёвой акции не поднимает цену сравнения."""
    p = _product("10.00")
    old = _promo(
        p,
        status="ended",
        price_override=Decimal("6.00"),
        starts_at=timezone.now() - timedelta(days=10),
        ends_at=timezone.now() - timedelta(days=3),
    )
    old.delete()  # soft
    promo = _promo(p, price_override=Decimal("7.00"))
    assert promo.old_price == Decimal("6.00")


def test_facet_rabatt_filter_is_batched(django_assert_max_num_queries):
    """Ревью H2: фильтр «−N %+» и сорт по скидке не делают запросов на акцию."""
    from apps.promotions.facets import PromoFacets

    for i in range(6):
        _promo(_product("10.00"), discount_percent=10 * (i + 1))
    qs = Promotion.objects.filter(status="active").select_related("product")
    fx = PromoFacets()
    with django_assert_max_num_queries(4):
        items = fx.apply(qs, {"rabatt": "30"})
        items = fx.sort(items, "rabatt")
    assert [x.discount_percent_display for x in items] == [60, 50, 40, 30]
