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


# --- Phase 3: normalize кастом-определений + tenant-aware аксессоры ------------


def test_normalize_status_defs_whitelist_and_dedup():
    from apps.tenants import siteconfig

    out = siteconfig.normalize_status_defs(
        {
            "booking": [
                {
                    "code": "Beim Lieferanten!",
                    "role": "active",
                    "stage": "in_progress",
                    "blocks_capacity": True,
                },
                {
                    "code": "confirmed",
                    "role": "active",
                    "stage": "in_progress",
                },  # коллизия built-in
                {"code": "bad", "role": "nope", "stage": "in_progress"},  # плохая роль
                {"code": "x", "role": "active", "stage": "wrong"},  # плохая стадия
                {"code": "beim_lieferanten", "role": "active", "stage": "done"},  # дубль slug
            ],
            "nope_kind": [{"code": "z", "role": "active", "stage": "done"}],
        }
    )
    assert list(out) == ["booking"] and len(out["booking"]) == 1
    d = out["booking"][0]
    assert d["code"] == "beim_lieferanten" and d["blocks_capacity"] is True


def test_normalize_status_defs_presence_minimal():
    from apps.tenants import siteconfig

    assert siteconfig.normalize_status_defs({}) == {}
    assert "status_defs" not in siteconfig.normalize({})
    assert siteconfig.normalize(
        {"status_defs": {"booking": [{"code": "wip", "role": "active", "stage": "in_progress"}]}}
    )["status_defs"]["booking"]


@pytest.mark.django_db
def test_custom_descriptors_and_resolve():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {
                        "code": "beim_lieferanten",
                        "label": "Beim Lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    },
                    {
                        "code": "reklamation",
                        "label": "Reklamation",
                        "role": "cancelled",
                        "stage": "terminal",
                    },
                ]
            }
        }
    )
    cd = status_registry.custom_descriptors(t, "booking")
    assert set(cd) == {"beim_lieferanten", "reklamation"}
    assert cd["beim_lieferanten"].builtin is False and cd["beim_lieferanten"].blocks_capacity
    assert cd["reklamation"].is_danger is True  # роль cancelled → danger
    assert status_registry.resolve("booking", "confirmed", t).builtin is True  # built-in
    assert status_registry.resolve("booking", "beim_lieferanten", t).stage == "in_progress"
    assert status_registry.resolve("booking", "ghost", t) is None


@pytest.mark.django_db
def test_active_statuses_for_includes_custom_capacity():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {
                        "code": "beim_lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    },
                    {
                        "code": "wartet",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": False,
                    },
                ]
            }
        }
    )
    a = set(status_registry.active_statuses_for("booking", t))
    assert {"pending", "confirmed"} <= a  # built-in всегда включены
    assert "beim_lieferanten" in a  # кастом-active блокирует ёмкость
    assert "wartet" not in a  # blocks_capacity=False → не блокирует
    # без тенанта — built-in обязательно присутствуют (кастом лишь добавляет)
    assert {"pending", "confirmed"} <= set(status_registry.active_statuses_for("booking"))


@pytest.mark.django_db
def test_stage_of_custom_and_fallback():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [{"code": "beim_lieferanten", "role": "active", "stage": "in_progress"}]
            }
        }
    )
    assert status_registry.stage_of("booking", "beim_lieferanten", t) == "in_progress"
    assert status_registry.stage_of("booking", "confirmed", t) == "in_progress"  # built-in
    assert status_registry.stage_of("booking", "ghost", t) == "intake"  # фолбэк


# --- Phase 4: кастом-переходы (custom_edges + normalize) -----------------------


def test_normalize_status_edges_structural_and_presence():
    from apps.tenants import siteconfig

    out = siteconfig.normalize_status_edges(
        {
            "booking": [
                {"src": "confirmed", "dst": "beim_lieferanten"},
                {"src": "x", "dst": "x"},  # src==dst → отброшено
                {"src": "", "dst": "y"},  # пустой src → отброшено
                {"src": "confirmed", "dst": "beim_lieferanten"},  # дубль
            ],
            "nope": [{"src": "a", "dst": "b"}],
        }
    )
    assert out == {"booking": [{"src": "confirmed", "dst": "beim_lieferanten"}]}
    assert siteconfig.normalize_status_edges({}) == {}
    assert "status_edges" not in siteconfig.normalize({})


@pytest.mark.django_db
def test_custom_edges_requires_known_endpoints_and_custom():
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [{"code": "beim_lieferanten", "role": "active", "stage": "in_progress"}]
            },
            "status_edges": {
                "booking": [
                    {"src": "confirmed", "dst": "beim_lieferanten"},  # ok (built-in→custom)
                    {"src": "beim_lieferanten", "dst": "fulfilled"},  # ok (custom→built-in)
                    {"src": "confirmed", "dst": "fulfilled"},  # built-in↔built-in → запрещён
                    {"src": "confirmed", "dst": "ghost"},  # неизвестный эндпоинт → отброшен
                ]
            },
        }
    )
    edges = status_registry.custom_edges(t, "booking")
    assert edges == {("confirmed", "beim_lieferanten"), ("beim_lieferanten", "fulfilled")}
