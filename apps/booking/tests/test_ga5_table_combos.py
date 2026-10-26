"""KA-12 GA-5 (Gastro): комбинация столов «Tisch 3+4» — бронь комбинации держит
столы-части и наоборот; все пути занятости (book/move/слоты/самоперенос) видят
одну область; состав проверяется единственным писателем."""

import pathlib
import uuid
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.booking import availability, occupancy, services, table_rules
from apps.booking.models import AvailabilityRule, Resource

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)


def _table(name, seats, **kw):
    r = Resource.objects.create(
        name=f"{name} {uuid.uuid4().hex[:4]}",
        type=Resource.TYPE_TABLE,
        capacity=1,
        seats=seats,
        **kw,
    )
    AvailabilityRule.objects.create(
        resource=r, weekday=DAY.weekday(), start_time=time(18), end_time=time(20), slot_minutes=60
    )
    return r


def _start(hour=18):
    return datetime.combine(DAY, time(hour), tzinfo=timezone.get_current_timezone())


def _book(resource, party=2, hour=18):
    return services.book(
        resource,
        start=_start(hour),
        end=_start(hour) + timedelta(hours=1),
        name="G",
        party_size=party,
    )


@pytest.fixture
def combo():
    t3, t4 = _table("T3", 4), _table("T4", 4)
    c = _table("T3+4", None)
    occupancy.set_parts(c, [t3.pk, t4.pk])
    c.refresh_from_db()
    return c, t3, t4


def test_combo_seats_default_sum(combo):
    c, _t3, _t4 = combo
    assert c.seats == 8


def test_booked_part_blocks_combo_and_vice_versa(combo):
    c, t3, t4 = combo
    _book(t3)
    with pytest.raises(services.SlotTaken):
        _book(c, party=6)
    _book(t4, hour=19)
    assert (_start(18), _start(19)) not in availability.free_slots(c, DAY)
    c2, t5, t6 = _table("C2", None), _table("T5", 2), _table("T6", 2)
    occupancy.set_parts(c2, [t5.pk, t6.pk])
    _book(c2, party=4)
    with pytest.raises(services.SlotTaken):
        _book(t5)


def test_two_combos_sharing_a_table_exclude_each_other(combo):
    c, t3, _t4 = combo
    t2 = _table("T2", 2)
    other = _table("T2+3", None)
    occupancy.set_parts(other, [t2.pk, t3.pk])
    _book(c, party=6)
    with pytest.raises(services.SlotTaken):
        _book(other, party=5)


def test_move_into_occupied_scope_refused(combo):
    c, t3, _t4 = combo
    _book(c, party=6)
    other = _table("T9", 4)
    b = _book(other, hour=18)
    with pytest.raises(services.SlotTaken):
        services.move(b, start=_start(18), end=_start(19), resource=t3)


def test_autoassign_prefers_single_table_then_combo(combo):
    c, t3, t4 = combo
    assert table_rules.fitting_tables(4)[0].pk in {t3.pk, t4.pk}
    assert [t.pk for t in table_rules.fitting_tables(7)] == [c.pk]


def test_invalid_combos_refused():
    t1, t2 = _table("A", 2), _table("B", 2)
    pool = Resource.objects.create(
        name="Pool", type=Resource.TYPE_TABLE, capacity=40, counts_party_size=True
    )
    c = _table("C", None)
    with pytest.raises(occupancy.ComboInvalid):
        occupancy.set_parts(c, [t1.pk])  # один стол
    with pytest.raises(occupancy.ComboInvalid):
        occupancy.set_parts(c, [t1.pk, pool.pk])
    occupancy.set_parts(c, [t1.pk, t2.pk])
    nested = _table("N", None)
    with pytest.raises(occupancy.ComboInvalid):
        occupancy.set_parts(nested, [c.pk, t1.pk])  # комбинация — не часть
    with pytest.raises(occupancy.ComboInvalid):
        occupancy.set_parts(t1, [nested.pk, t2.pk])  # часть — не комбинация
    occupancy.set_parts(c, [])
    assert not c.parts.exists()


def test_pool_scope_is_itself():
    pool = Resource.objects.create(
        name="Pool", type=Resource.TYPE_TABLE, capacity=40, counts_party_size=True
    )
    assert occupancy.scope_ids(pool) == {pool.pk}


def test_occupancy_queries_go_through_scope():
    """Замок GA-5: проверки занятости брони фильтруют по области, а не по одному ресурсу."""
    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("services.py", "availability.py", "cancel_policy.py"):
        text = (root / name).read_text(encoding="utf-8")
        for chunk in text.split("Booking.objects")[1:]:
            head = chunk[:400]
            if 'active_statuses_for("booking")' in head:
                assert "resource=resource" not in head, name
