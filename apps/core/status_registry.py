"""FB-3 Вариант B, Phase 0: реестр дескрипторов статусов (роль + флаги).

Полноценные пользовательские статусы требуют снять завязку кода на ЛИТЕРАЛЬНЫЕ коды
статуса (деньги/склад/anti-oversell/стадии доски). Дескриптор описывает КАЖДЫЙ статус
семантически, чтобы кастом-статус мог наследовать поведение соседа по роли.

Phase 0 = ТОЛЬКО описать текущий мир 1:1 (реестр + характеризационные замки). Поведение
НЕ меняется: PIPELINE/ACTIVE_STATUSES/DANGER_TARGETS/_COUNTED остаются источниками правды,
а тесты доказывают, что реестр их воспроизводит. Перевод чтения на реестр — Phase 1.

Ортогональные флаги (одного enum роли мало — см. план §1):
- `stage`      — колонка доски (intake|in_progress|done|terminal).
- `blocks_capacity` — занимает слот/ночь/место (anti-oversell; ACTIVE_STATUSES).
- `counts_in_reports` — входит в отчёты занятости/выручки (stays `_COUNTED`; включает
  `fulfilled`, которого НЕТ в ACTIVE_STATUSES → две независимые оси).
- `revenue_recognized` — при ВХОДЕ в статус фиксируется выручка (нужно Phase 2: отмена
  позже делает reversal только если покидаемый статус был revenue-recognized).
- `is_danger`  — отменяющий/негативный (красная кнопка; не прячется в Варианте A).
"""

from dataclasses import dataclass

STAGES = ("intake", "in_progress", "done", "terminal")
ROLES = ("intake", "active", "done", "cancelled")


@dataclass(frozen=True)
class StatusDescriptor:
    code: str
    role: str
    stage: str
    blocks_capacity: bool = False
    counts_in_reports: bool = False
    revenue_recognized: bool = False
    is_danger: bool = False
    builtin: bool = True


def _d(code, role, stage, **flags):
    return StatusDescriptor(code=code, role=role, stage=stage, **flags)


# Встроенные дескрипторы — заполнены ТОЧНО под текущие PIPELINE/ACTIVE_STATUSES/
# DANGER_TARGETS/_COUNTED/on_transition (замки паритета в test_status_registry.py).
BUILTIN: dict[str, dict[str, StatusDescriptor]] = {
    "order": {
        "new": _d("new", "intake", "intake"),
        "confirmed": _d("confirmed", "active", "in_progress"),
        "ready": _d("ready", "active", "in_progress"),
        "picked_up": _d("picked_up", "done", "done", revenue_recognized=True),
        "shipped": _d("shipped", "done", "done", revenue_recognized=True),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
        "returned": _d("returned", "cancelled", "terminal", is_danger=True),
    },
    "booking": {
        "pending": _d("pending", "intake", "intake", blocks_capacity=True),
        "confirmed": _d("confirmed", "active", "in_progress", blocks_capacity=True),
        "fulfilled": _d("fulfilled", "done", "done", revenue_recognized=True),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
        "no_show": _d("no_show", "cancelled", "terminal", is_danger=True),
    },
    "stay": {
        "pending": _d("pending", "intake", "intake", blocks_capacity=True, counts_in_reports=True),
        "confirmed": _d(
            "confirmed", "active", "in_progress", blocks_capacity=True, counts_in_reports=True
        ),
        "fulfilled": _d(
            "fulfilled", "done", "done", counts_in_reports=True, revenue_recognized=True
        ),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
        "no_show": _d("no_show", "cancelled", "terminal", is_danger=True),
    },
    "ticket": {
        # Асимметрия: attended = «done», НО занимает место (blocks_capacity) — в отличие
        # от booking/stay.fulfilled. Выручка тикета — при confirmed (не при attended).
        "pending": _d("pending", "intake", "intake", blocks_capacity=True),
        "confirmed": _d(
            "confirmed", "active", "in_progress", blocks_capacity=True, revenue_recognized=True
        ),
        "attended": _d("attended", "done", "done", blocks_capacity=True),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
    },
    "job": {
        "new": _d("new", "intake", "intake"),
        "quoted": _d("quoted", "active", "in_progress"),
        "accepted": _d("accepted", "active", "in_progress"),
        "done": _d("done", "done", "done"),  # commit_stock, но не record_revenue (invoice-флоу)
        "invoiced": _d("invoiced", "done", "done"),
        "declined": _d("declined", "cancelled", "terminal", is_danger=True),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
    },
    "reservation": {
        "pending": _d("pending", "intake", "intake", blocks_capacity=True),
        "confirmed": _d("confirmed", "active", "in_progress", blocks_capacity=True),
        "fulfilled": _d("fulfilled", "done", "done", revenue_recognized=True),
        "cancelled": _d("cancelled", "cancelled", "terminal", is_danger=True),
        "expired": _d("expired", "cancelled", "terminal", is_danger=True),
    },
}


# --- аксессоры (Phase 1 переведёт код на них; Phase 0 — только чтение реестра) ---


def descriptors(kind: str) -> dict[str, StatusDescriptor]:
    """Все дескрипторы kind (пока только built-in; Phase 3 добавит кастом тенанта)."""
    return BUILTIN.get(kind, {})


def descriptor(kind: str, status: str) -> StatusDescriptor | None:
    return BUILTIN.get(kind, {}).get(status)


def stage_map(kind: str) -> dict[str, str]:
    """{status: stage} для kind (= текущий PIPELINE[kind])."""
    return {code: d.stage for code, d in descriptors(kind).items()}


def active_statuses(kind: str) -> tuple[str, ...]:
    """Коды, занимающие ёмкость (= ACTIVE_STATUSES для booking/stay/ticket)."""
    return tuple(code for code, d in descriptors(kind).items() if d.blocks_capacity)


def counted_statuses(kind: str) -> tuple[str, ...]:
    """Коды, входящие в отчёты (= stays `_COUNTED`)."""
    return tuple(code for code, d in descriptors(kind).items() if d.counts_in_reports)


def revenue_statuses(kind: str) -> tuple[str, ...]:
    """Коды, при входе в которые фиксируется выручка (для Phase 2)."""
    return tuple(code for code, d in descriptors(kind).items() if d.revenue_recognized)


def danger_codes() -> set[str]:
    """Все отменяющие/негативные коды (= DANGER_TARGETS)."""
    return {code for kind in BUILTIN for code, d in descriptors(kind).items() if d.is_danger}
