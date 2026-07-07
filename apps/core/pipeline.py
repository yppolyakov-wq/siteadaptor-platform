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

# Канонические стадии доски (слева направо).
STAGES = ("intake", "in_progress", "done", "terminal")

# Немецкие подписи колонок (язык кабинета — DE, как NAV_TASK_LABELS).
STAGE_LABELS = {
    "intake": _("Neu"),
    "in_progress": _("In Bearbeitung"),
    "done": _("Fertig"),
    "terminal": _("Abgeschlossen"),
}

# kind → {status: stage}. Каждая запись перечисляет ВСЕ статусы FSM этого kind
# (источник — apps/<app>/state_machine.py). Пропуск статуса → фолбэк intake.
PIPELINE = {
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


# Отрицательные/отменяющие переходы — красная кнопка на карточке/строке.
DANGER_TARGETS = {"cancelled", "declined", "no_show", "returned", "expired"}


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
