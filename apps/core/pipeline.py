"""U-D2: единый «конвейер» транзакции — статус → стадия доски (Kanban).

Модели-транзакции (Order/Booking/StayBooking/Ticket/Job/Reservation) имеют
каждая свой FSM со своим словарём статусов. Для единой доски дел сводим их к
четырём каноническим стадиям-колонкам: приём → в работе → готово → закрыто.

Чистый Python, без импорта моделей/FSM: `transaction_for` (apps.core.transactions)
берёт отсюда `stage_for`/`action_label`, а вьюха доски — `pipeline_for`. Порядок
статусов в колонке важен: при drag в колонку целевой статус = ПЕРВЫЙ допустимый
FSM-переход, чей `stage` совпадает с колонкой (см. transactions.allowed_actions).
"""

from django.utils.translation import gettext_lazy as _

from apps.core import status_registry

# Канонические стадии доски (слева направо).
STAGES = ("intake", "in_progress", "done", "terminal")

# Немецкие подписи колонок (язык кабинета — DE, как NAV_TASK_LABELS).
STAGE_LABELS = {
    "intake": _("Neu"),
    "in_progress": _("In Bearbeitung"),
    "done": _("Fertig"),
    "terminal": _("Abgeschlossen"),
}

# kind → {status: stage}. FB-3 Вариант B Phase 1: выводится из ЕДИНОГО источника —
# реестра дескрипторов (`status_registry.BUILTIN`); порядок статусов в колонке сохранён
# (важно для группировки pipeline_for). Пропуск статуса → фолбэк intake (stage_for).
# Замок паритета — test_status_registry (замороженный golden-снимок).
PIPELINE = {kind: status_registry.stage_map(kind) for kind in status_registry.BUILTIN}

# kind → {target_status: немецкая подпись действия/кнопки}. Действие = переход
# FSM в этот статус (см. allowed_actions). Фолбэк — сам код статуса.
ACTION_LABELS = {
    "order": {
        "confirmed": _("Bestätigen"),
        "ready": _("Fertig zur Abholung"),
        "picked_up": _("Abgeholt"),
        "shipped": _("Versendet"),
        "cancelled": _("Stornieren"),
        "returned": _("Retoure"),
    },
    "booking": {
        "confirmed": _("Bestätigen"),
        "fulfilled": _("Erledigt"),
        "cancelled": _("Stornieren"),
        "no_show": _("No-Show"),
    },
    "stay": {
        "confirmed": _("Bestätigen"),
        "fulfilled": _("Abgereist"),
        "cancelled": _("Stornieren"),
        "no_show": _("No-Show"),
    },
    "ticket": {
        "confirmed": _("Bestätigen"),
        "attended": _("Teilgenommen"),
        "cancelled": _("Stornieren"),
    },
    "job": {
        "quoted": _("Angebot senden"),
        "accepted": _("Beauftragt"),
        "done": _("Erledigt"),
        "invoiced": _("Abgerechnet"),
        "declined": _("Ablehnen"),
        "cancelled": _("Stornieren"),
    },
    "reservation": {
        "confirmed": _("Bestätigen"),
        "fulfilled": _("Eingelöst"),
        "cancelled": _("Stornieren"),
        "expired": _("Abgelaufen"),
    },
}


# Отрицательные/отменяющие переходы — красная кнопка на карточке/строке. Phase 1:
# выводится из реестра (`is_danger`-флаг дескрипторов). Замок — test_status_registry.
DANGER_TARGETS = status_registry.danger_codes()


def is_danger(target: str) -> bool:
    """True для отменяющих/негативных переходов (стиль кнопки = danger)."""
    return target in DANGER_TARGETS


def stage_for(kind: str, status: str) -> str:
    """Стадия-колонка для (kind, status). Неизвестный статус → 'intake' (безопасно —
    новая запись попадает в приёмную колонку, а не теряется)."""
    return PIPELINE.get(kind, {}).get(status, "intake")


def action_label(kind: str, target: str) -> str:
    """Подпись кнопки/действия перехода в `target` (фолбэк — код статуса)."""
    return ACTION_LABELS.get(kind, {}).get(target, target)


def resolve_columns(kind: str, board: dict | None = None) -> list[dict]:
    """W5: колонки доски для `kind` с пер-тенантными настройками (переименование/
    порядок/скрытие). `board` = ``{"labels": {stage: str}, "order": [stage,…],
    "hidden": [stage,…]}`` (из site_config, уже нормализовано). Пусто/None → дефолт.

    Переименование — labels[stage] (иначе STAGE_LABELS); порядок — order (недостающие
    стадии добиваются в дефолтном порядке STAGES); скрытие — hidden. Статусы колонки
    (`statuses`, правила переходов) НЕ трогаем — V4 (FSM) фикс, решение владельца.
    """
    board = board or {}
    labels = board.get("labels") if isinstance(board.get("labels"), dict) else {}
    hidden = {s for s in (board.get("hidden") or []) if s in STAGES}
    raw_order = [s for s in (board.get("order") or []) if s in STAGES]
    order = raw_order + [s for s in STAGES if s not in raw_order]
    base = {c["stage"]: c for c in pipeline_for(kind)}
    out = []
    for stage in order:
        if stage in hidden or stage not in base:
            continue
        col = dict(base[stage])
        custom = labels.get(stage)
        if isinstance(custom, str) and custom.strip():
            col["label"] = custom.strip()
        out.append(col)
    return out


def pipeline_for(kind: str) -> list[dict]:
    """Упорядоченные колонки доски для `kind`: ``[{stage, label, statuses}]``.

    Колонки — все 4 стадии в порядке STAGES; `statuses` — статусы этого kind,
    относящиеся к стадии (в порядке объявления PIPELINE[kind]). Стадия без
    статусов у данного kind всё равно включается (пустая колонка) — чтобы доски
    разных kind визуально совпадали.
    """
    mapping = PIPELINE.get(kind, {})
    by_stage: dict[str, list[str]] = {s: [] for s in STAGES}
    for status, stage in mapping.items():
        by_stage.setdefault(stage, []).append(status)
    return [
        {"stage": stage, "label": STAGE_LABELS[stage], "statuses": by_stage.get(stage, [])}
        for stage in STAGES
    ]
