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

from django.utils.translation import gettext_lazy as _

STAGES = ("intake", "in_progress", "done", "terminal")
ROLES = ("intake", "active", "done", "cancelled")

# FB-3 Вариант B Phase 5: роль → стадия + дефолт-флаги (для редактора — владелец выбирает
# роль, поведение следует; продвинутое (counts_in_reports/своя стадия) — через site_config API).
ROLE_STAGE = {"intake": "intake", "active": "in_progress", "done": "done", "cancelled": "terminal"}
ROLE_DEFAULT_FLAGS = {"active": {"blocks_capacity": True}, "done": {"revenue_recognized": True}}
ROLE_LABELS = {
    "intake": _("Neu / Eingang"),
    "active": _("In Arbeit (hält Kapazität)"),
    "done": _("Abgeschlossen (Umsatz)"),
    "cancelled": _("Storniert / Abbruch"),
}


def def_from_role(code: str, label: str, role: str) -> dict:
    """Кастом-определение статуса из code+label+role: стадия и флаги выводятся по роли."""
    role = role if role in ROLES else "active"
    return {
        "code": code,
        "label": label,
        "role": role,
        "stage": ROLE_STAGE[role],
        **ROLE_DEFAULT_FLAGS.get(role, {}),
    }


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
    label: str = ""  # отображаемая подпись кастом-статуса (Phase 6); built-in — из pipeline


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


# --- FB-3 Вариант B Phase 3: кастом-статусы тенанта (per-tenant) --------------
# tenant передаётся явно ИЛИ берётся из текущего соединения (django-tenants). Хранение —
# site_config["status_defs"][kind] (нормализовано siteconfig.normalize_status_defs при записи).


def _current_tenant():
    """Текущий тенант из соединения (django-tenants) или None (public/нет)."""
    from django.db import connection

    t = getattr(connection, "tenant", None)
    if t is None or getattr(t, "schema_name", "public") == "public":
        return None
    return t


def custom_descriptors(tenant, kind: str) -> dict[str, StatusDescriptor]:
    """Кастом-дескрипторы тенанта для kind (builtin=False). is_danger выводится из роли
    cancelled. Пусто, если нет. Читает уже-нормализованный site_config."""
    cfg = getattr(tenant, "site_config", None)
    defs = cfg.get("status_defs") if isinstance(cfg, dict) else None
    if not isinstance(defs, dict):
        return {}
    out = {}
    for d in defs.get(kind, []) or []:
        code = d.get("code")
        if code and code not in BUILTIN.get(kind, {}):
            out[code] = StatusDescriptor(
                code=code,
                role=d.get("role", "active"),
                stage=d.get("stage", "in_progress"),
                blocks_capacity=bool(d.get("blocks_capacity")),
                counts_in_reports=bool(d.get("counts_in_reports")),
                revenue_recognized=bool(d.get("revenue_recognized")),
                is_danger=(d.get("role") == "cancelled"),
                builtin=False,
                label=d.get("label") or code,
            )
    return out


def resolve(kind: str, status: str, tenant=None) -> StatusDescriptor | None:
    """Дескриптор (kind, status): встроенный ИЛИ кастом тенанта. tenant=None → текущий."""
    d = BUILTIN.get(kind, {}).get(status)
    if d is not None:
        return d
    if tenant is None:
        tenant = _current_tenant()
    return custom_descriptors(tenant, kind).get(status) if tenant is not None else None


def all_descriptors(kind: str, tenant=None) -> dict[str, StatusDescriptor]:
    """Встроенные ∪ кастом тенанта."""
    out = dict(descriptors(kind))
    if tenant is None:
        tenant = _current_tenant()
    if tenant is not None:
        out.update(custom_descriptors(tenant, kind))
    return out


def active_statuses_for(kind: str, tenant=None) -> tuple[str, ...]:
    """Коды, занимающие ёмкость: встроенные ∪ кастом-active тенанта (anti-oversell).
    ВСЕГДА включает built-in (безопасное направление — кастом лишь ДОБАВЛЯЕТ)."""
    codes = list(active_statuses(kind))
    if tenant is None:
        tenant = _current_tenant()
    if tenant is not None:
        codes += [c for c, d in custom_descriptors(tenant, kind).items() if d.blocks_capacity]
    return tuple(codes)


def stage_of(kind: str, status: str, tenant=None) -> str:
    """Стадия доски для (kind, status): дескриптор или фолбэк intake (как pipeline.stage_for)."""
    d = resolve(kind, status, tenant)
    return d.stage if d is not None else "intake"


def custom_edges(tenant, kind: str) -> set:
    """FB-3 Вариант B Phase 4: валидные кастом-переходы тенанта {(src, dst)}. Оба статуса
    ДОЛЖНЫ быть известны (built-in ∪ кастом kind) и ≥1 эндпоинт — кастомный (built-in↔built-in
    shortcut запрещён: встроенный граф FSM — жёсткий пол). Мусор/невалидное отброшено."""
    cfg = getattr(tenant, "site_config", None)
    node = cfg.get("status_edges") if isinstance(cfg, dict) else None
    edges_raw = node.get(kind, []) if isinstance(node, dict) else []
    custom_codes = set(custom_descriptors(tenant, kind))
    known = set(BUILTIN.get(kind, {})) | custom_codes
    out = set()
    for e in edges_raw:
        src, dst = e.get("src"), e.get("dst")
        if (
            src in known
            and dst in known
            and src != dst
            and (src in custom_codes or dst in custom_codes)
        ):
            out.add((src, dst))
    return out
