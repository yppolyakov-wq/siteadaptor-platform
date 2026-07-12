"""FB-3 Вариант B, Phase 0/1: характеризационные замки реестра дескрипторов.

Phase 1 делает `status_registry` ЕДИНСТВЕННЫМ источником правды: PIPELINE / ACTIVE_STATUSES /
DANGER_TARGETS / stays `_COUNTED` выводятся из реестра. Поэтому замки сравнивают реестр не
с этими (теперь производными) константами, а с ЗАМОРОЖЕННЫМИ golden-литералами ниже —
снимком поведения ДО рефактора. Любое расхождение = красный тест. Дополнительно проверяем,
что производные константы совпали с golden (доказывает эквивалентность перевода Phase 1).
"""

import pytest

from apps.core import pipeline, status_registry

# --- ЗАМОРОЖЕННЫЙ снимок текущего мира (golden) --------------------------------

GOLDEN_STAGE = {
    "order": {
        "new": "intake",
        "confirmed": "in_progress",
        "ready": "in_progress",
        "picked_up": "done",
        "shipped": "done",
        "cancelled": "terminal",
        "returned": "terminal",
    },
    "booking": {
        "pending": "intake",
        "confirmed": "in_progress",
        "fulfilled": "done",
        "cancelled": "terminal",
        "no_show": "terminal",
    },
    "stay": {
        "pending": "intake",
        "confirmed": "in_progress",
        "fulfilled": "done",
        "cancelled": "terminal",
        "no_show": "terminal",
    },
    "ticket": {
        "pending": "intake",
        "confirmed": "in_progress",
        "attended": "done",
        "cancelled": "terminal",
    },
    "job": {
        "new": "intake",
        "quoted": "in_progress",
        "accepted": "in_progress",
        "done": "done",
        "invoiced": "done",
        "declined": "terminal",
        "cancelled": "terminal",
    },
    "reservation": {
        "pending": "intake",
        "confirmed": "in_progress",
        "fulfilled": "done",
        "cancelled": "terminal",
        "expired": "terminal",
    },
}

GOLDEN_ACTIVE = {
    "order": set(),
    "booking": {"pending", "confirmed"},
    "stay": {"pending", "confirmed"},
    "ticket": {"pending", "confirmed", "attended"},
    "job": set(),
    "reservation": {"pending", "confirmed"},
}

GOLDEN_DANGER = {"cancelled", "declined", "no_show", "returned", "expired"}
GOLDEN_STAY_COUNTED = {"pending", "confirmed", "fulfilled"}
GOLDEN_REVENUE = {
    "order": {"picked_up", "shipped"},
    "booking": {"fulfilled"},
    "stay": {"fulfilled"},
    "ticket": {"confirmed"},  # тикет — выручка при confirmed, не при attended
    "job": set(),  # invoice-флоу, не FSM
    "reservation": {"fulfilled"},
}

_KINDS = list(GOLDEN_STAGE)


# --- реестр == golden ----------------------------------------------------------


@pytest.mark.parametrize("kind", _KINDS)
def test_stage_map_matches_golden(kind):
    assert status_registry.stage_map(kind) == GOLDEN_STAGE[kind]


@pytest.mark.parametrize("kind", _KINDS)
def test_active_matches_golden(kind):
    assert set(status_registry.active_statuses(kind)) == GOLDEN_ACTIVE[kind]


@pytest.mark.parametrize("kind", _KINDS)
def test_revenue_matches_golden(kind):
    assert set(status_registry.revenue_statuses(kind)) == GOLDEN_REVENUE[kind]


def test_danger_matches_golden():
    assert status_registry.danger_codes() == GOLDEN_DANGER


def test_stay_counted_matches_golden():
    assert set(status_registry.counted_statuses("stay")) == GOLDEN_STAY_COUNTED


def test_all_stages_and_roles_valid():
    for kind, node in status_registry.BUILTIN.items():
        for code, d in node.items():
            assert d.stage in status_registry.STAGES, (kind, code)
            assert d.role in status_registry.ROLES, (kind, code)


# --- Phase 1: производные константы совпали с golden (эквивалентность перевода) ---


@pytest.mark.parametrize("kind", _KINDS)
def test_pipeline_derived_equals_golden(kind):
    assert pipeline.PIPELINE[kind] == GOLDEN_STAGE[kind]


def test_pipeline_danger_derived_equals_golden():
    assert set(pipeline.DANGER_TARGETS) == GOLDEN_DANGER


def test_model_active_statuses_equal_golden():
    # Модельные ACTIVE_STATUSES остаются литералами (oversell-критичны); реестр им
    # эквивалентен (обе стороны == golden). Перевод на рантайм-аксессор — Phase 3.
    from apps.booking.models import Booking
    from apps.events.models import Ticket
    from apps.stays.models import StayBooking

    assert set(Booking.ACTIVE_STATUSES) == GOLDEN_ACTIVE["booking"]
    assert set(StayBooking.ACTIVE_STATUSES) == GOLDEN_ACTIVE["stay"]
    assert set(Ticket.ACTIVE_STATUSES) == GOLDEN_ACTIVE["ticket"]


def test_stay_reports_counted_equal_golden():
    from apps.stays import reports

    assert set(reports._COUNTED) == GOLDEN_STAY_COUNTED
