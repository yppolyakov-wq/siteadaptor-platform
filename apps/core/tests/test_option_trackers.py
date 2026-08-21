"""MX-2e: enforcement трекеров опций — пул и склад (+ 3b правка допов билета).

План docs/mx-followups-plan-2026-08-21.md. Пул: отказ при переполнении окна
исполнения. Склад: списание при продаже, возврат при отмене (идемпотентно,
включая двойной вызов builtin-хук + зеркало кастом-статусов).
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import option_trackers, transactions
from apps.core.models import Extra
from apps.events import services as event_services
from apps.events.models import Event
from apps.stays import services as stay_services
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 5)
    kw.setdefault("max_guests", 4)
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", **kw)


def _event(**kw):
    start = timezone.now() + timedelta(days=15)
    defaults = {
        "title": "Tour",
        "starts_at": start,
        "ends_at": start + timedelta(days=2),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
        "price_cents": 5000,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _pool_extra(scope="events", size=2, **kw):
    return Extra.objects.create(
        label="Enfield mieten",
        price_cents=40000,
        scope=scope,
        tracker=Extra.TRACKER_POOL,
        pool_size=size,
        **kw,
    )


def _stock_extra(product, scope="stays", **kw):
    return Extra.objects.create(
        label="Weinflasche",
        price_cents=1900,
        scope=scope,
        tracker=Extra.TRACKER_STOCK,
        product=product,
        **kw,
    )


def _snap(extra):
    return [
        {
            "id": str(extra.pk),
            "label": extra.label,
            "price_cents": extra.price_cents,
            "unit_cents": extra.price_cents,
            "per_night": extra.per_night,
        }
    ]


# --- пул -----------------------------------------------------------------------


def test_pool_full_rejects_ticket():
    """Пул 2: третий билет с той же опцией на пересекающиеся дни — отказ, билет
    не создаётся (откат atomic)."""
    ev = _event()
    extra = _pool_extra(size=2)
    for i in range(2):
        event_services.book_ticket(
            ev, name=f"G{i}", email=f"g{i}@t.de", extras=_snap(extra), auto_confirm=True
        )
    from apps.events.models import Ticket

    before = Ticket.objects.count()
    with pytest.raises(option_trackers.PoolFull):
        event_services.book_ticket(
            ev, name="G3", email="g3@t.de", extras=_snap(extra), auto_confirm=True
        )
    assert Ticket.objects.count() == before


def test_pool_frees_after_cancel_and_counts_cross_kind():
    """Отменённый билет пул не держит; бронь проживания с той же опцией в те же
    дни — считается (пул общий на все kind)."""
    ev = _event()
    extra = _pool_extra(size=2, scope="all")
    t1 = event_services.book_ticket(
        ev, name="A", email="a@t.de", extras=_snap(extra), auto_confirm=True
    )
    # Та же опция занята бронью проживания, пересекающей дни события.
    stay_services.book_stay(
        _unit(),
        arrival=ev.starts_at.date(),
        departure=ev.starts_at.date() + timedelta(days=2),
        name="B",
        extras=_snap(extra),
    )
    with pytest.raises(option_trackers.PoolFull):
        event_services.book_ticket(
            ev, name="C", email="c@t.de", extras=_snap(extra), auto_confirm=True
        )
    # Отмена билета через ЕДИНУЮ точку доски освобождает единицу пула.
    transactions.apply_action("ticket", t1, "cancelled")
    event_services.book_ticket(ev, name="C", email="c@t.de", extras=_snap(extra), auto_confirm=True)


def test_pool_zero_size_means_unlimited():
    """pool_size=0 — лимит не задан, отказов нет (fail-open по конфигу)."""
    ev = _event()
    extra = _pool_extra(size=0)
    for i in range(3):
        event_services.book_ticket(
            ev, name=f"G{i}", email=f"g{i}@t.de", extras=_snap(extra), auto_confirm=True
        )


# --- склад ---------------------------------------------------------------------


def _product(stock=5):
    from apps.catalog.models import Product

    return Product.objects.create(name={"de": "Wein"}, base_price=19, stock_quantity=stock)


def test_stock_option_decrements_and_restores_idempotently():
    product = _product(stock=3)
    extra = _stock_extra(product)
    unit = _unit()
    arrival = timezone.localdate() + timedelta(days=30)
    b = stay_services.book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="G",
        extras=_snap(extra),
    )
    product.refresh_from_db()
    assert product.stock_quantity == 2

    # Отмена возвращает; повторный release (зеркало кастом-статусов) — no-op.
    transactions.apply_action("stay", b, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 3
    option_trackers.release_options("stay", b)
    product.refresh_from_db()
    assert product.stock_quantity == 3


def test_stock_option_out_of_stock_rejects():
    product = _product(stock=0)
    extra = _stock_extra(product)
    unit = _unit()
    arrival = timezone.localdate() + timedelta(days=30)
    from apps.stays.models import StayBooking

    before = StayBooking.objects.count()
    with pytest.raises(option_trackers.OptionOutOfStock):
        stay_services.book_stay(
            unit,
            arrival=arrival,
            departure=arrival + timedelta(days=2),
            name="G",
            extras=_snap(extra),
        )
    assert StayBooking.objects.count() == before


def test_release_without_sale_movement_does_not_inflate_stock():
    """Смена трекера опции после продажи не должна доливать склад при отмене."""
    product = _product(stock=5)
    extra = Extra.objects.create(  # продана как надбавка, БЕЗ трекера
        label="Deko", price_cents=500, scope="stays"
    )
    unit = _unit()
    arrival = timezone.localdate() + timedelta(days=30)
    b = stay_services.book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="G",
        extras=_snap(extra),
    )
    # Владелец делает опцию складской ПОСЛЕ продажи.
    extra.tracker = Extra.TRACKER_STOCK
    extra.product = product
    extra.save(update_fields=["tracker", "product"])
    transactions.apply_action("stay", b, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 5  # sale-движения не было → возврата нет


# --- sync (правка состава, MX-3/3b) --------------------------------------------


def test_sync_options_commits_added_and_releases_removed():
    product = _product(stock=2)
    stock_extra = _stock_extra(product)
    unit = _unit()
    arrival = timezone.localdate() + timedelta(days=30)
    b = stay_services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="G"
    )
    # Добавили складскую опцию правкой.
    option_trackers.sync_options([], _snap(stock_extra), kind="stay", deal=b)
    product.refresh_from_db()
    assert product.stock_quantity == 1
    # Убрали правкой — вернулось.
    option_trackers.sync_options(_snap(stock_extra), [], kind="stay", deal=b)
    product.refresh_from_db()
    assert product.stock_quantity == 2
