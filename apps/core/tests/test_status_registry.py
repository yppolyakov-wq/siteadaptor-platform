"""FB-3 Вариант B, Phase 0: характеризационные замки реестра дескрипторов.

Доказывают, что status_registry описывает ТЕКУЩИЙ мир 1:1 — прежде чем Phase 1 переведёт
код на реестр. Любое расхождение реестра с PIPELINE/ACTIVE_STATUSES/DANGER_TARGETS/_COUNTED
= красный тест. Поведение продукта эти тесты НЕ меняют (чистая добавка).
"""

import pytest

from apps.core import pipeline, status_registry

# --- stage == PIPELINE ---------------------------------------------------------


@pytest.mark.parametrize("kind", ["order", "booking", "stay", "ticket", "job", "reservation"])
def test_stage_map_matches_pipeline(kind):
    assert status_registry.stage_map(kind) == pipeline.PIPELINE[kind]


def test_registry_covers_exactly_pipeline_kinds():
    assert set(status_registry.BUILTIN) == set(pipeline.PIPELINE)
    for kind in pipeline.PIPELINE:
        assert set(status_registry.descriptors(kind)) == set(pipeline.PIPELINE[kind])


def test_all_stages_and_roles_valid():
    for kind, node in status_registry.BUILTIN.items():
        for code, d in node.items():
            assert d.stage in status_registry.STAGES, (kind, code)
            assert d.role in status_registry.ROLES, (kind, code)


# --- blocks_capacity == ACTIVE_STATUSES ---------------------------------------


def test_active_statuses_match_models():
    from apps.booking.models import Booking
    from apps.events.models import Ticket
    from apps.stays.models import StayBooking

    assert set(status_registry.active_statuses("booking")) == set(Booking.ACTIVE_STATUSES)
    assert set(status_registry.active_statuses("stay")) == set(StayBooking.ACTIVE_STATUSES)
    assert set(status_registry.active_statuses("ticket")) == set(Ticket.ACTIVE_STATUSES)
    # order/job — без ёмкости
    assert status_registry.active_statuses("order") == ()
    assert status_registry.active_statuses("job") == ()


def test_reservation_active_matches_services_literal():
    # promotions/services оверсел-гейт использует ["pending","confirmed"] (не ACTIVE_STATUSES).
    assert set(status_registry.active_statuses("reservation")) == {"pending", "confirmed"}


# --- counts_in_reports == stays _COUNTED --------------------------------------


def test_stay_counted_matches_reports():
    from apps.stays import reports

    assert set(status_registry.counted_statuses("stay")) == set(reports._COUNTED)


# --- is_danger == DANGER_TARGETS ----------------------------------------------


def test_danger_codes_match_pipeline():
    assert status_registry.danger_codes() == set(pipeline.DANGER_TARGETS)


@pytest.mark.parametrize("kind", ["order", "booking", "stay", "ticket", "job", "reservation"])
def test_per_status_is_danger_matches_pipeline(kind):
    for code, d in status_registry.descriptors(kind).items():
        assert d.is_danger == pipeline.is_danger(code), (kind, code)


# --- revenue_recognized — документирует текущие точки record_revenue ----------
# (Phase 2 добавит runtime-замок эффектов; здесь фиксируем ожидаемый набор из разведки.)

_EXPECTED_REVENUE = {
    "order": {"picked_up", "shipped"},
    "booking": {"fulfilled"},
    "stay": {"fulfilled"},
    "ticket": {"confirmed"},  # тикет — выручка при confirmed, не при attended
    "job": set(),  # invoice-флоу, не FSM
    "reservation": {"fulfilled"},
}


@pytest.mark.parametrize("kind", list(_EXPECTED_REVENUE))
def test_revenue_statuses_documented(kind):
    assert set(status_registry.revenue_statuses(kind)) == _EXPECTED_REVENUE[kind]
