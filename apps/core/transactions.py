"""U-D1: единый протокол `Transaction` над 6 доменными транзакциями.

Каждый архетип ведёт входящие транзакции своей моделью с собственным FSM:
заказ (`orders.Order`), запись по времени (`booking.Booking`), проживание
(`stays.StayBooking`), билет (`events.Ticket`), заявка/смета (`jobs.Job`),
резерв акции (`promotions.Reservation`). Владелец видит их в 6 разрозненных
экранах — нет «единой доски дел».

Этот модуль даёт адаптер (модели НЕ сливаем, прецедент — `apps.core.sellable`):
`transaction_for(kind, obj)` → нормализованный `Transaction` для ЛК (U-D1),
кабинетного резолвера/доски (U-D1.3, U-D2) и склад-леджера (U-D3).

Принципы:
- Импорт `apps.core.transactions` НЕ тянет orders/stays/events/… на загрузке.
  Модели резолвим лениво (`django.apps.get_model`), FSM — по строковому пути
  (`importlib`), объект приходит уже загруженным.
- Читаем статус, НИКОГДА не пишем. `allowed_actions` = `SM().allowed_targets` +
  подписи из `apps.core.pipeline` — без дублирования логики переходов.
- `subtotal_display` — готовая строка (D4: line-items НЕ унифицируем; отдаём
  title + посчитанный итог, без конфликта int-центы/Decimal).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from importlib import import_module

from django.urls import NoReverseMatch, reverse

from apps.core import pipeline

# kind → путь модели (ленивый apps.get_model). Порядок = порядок вкладок доски.
_KIND_MODEL = {
    "order": "orders.Order",
    "booking": "booking.Booking",
    "stay": "stays.StayBooking",
    "ticket": "events.Ticket",
    "job": "jobs.Job",
    "reservation": "promotions.Reservation",
}

# kind → (module_path, class) FSM-подкласса (ленивый импорт).
_KIND_SM = {
    "order": ("apps.orders.state_machine", "OrderSM"),
    "booking": ("apps.booking.state_machine", "BookingSM"),
    "stay": ("apps.stays.state_machine", "StayBookingSM"),
    "ticket": ("apps.events.state_machine", "TicketSM"),
    "job": ("apps.jobs.state_machine", "JobSM"),
    "reservation": ("apps.promotions.state_machine", "ReservationSM"),
}

# kind → ключ модуля-архетипа (гейтинг доски/резолвера по is_module_active).
KIND_MODULE = {
    "order": "orders",
    "booking": "booking",
    "stay": "stays",
    "ticket": "events",
    "job": "jobs",
    "reservation": "promotions",
}

# kind → (публичный url-name статус-страницы клиента, атрибут-аргумент). jobs —
# по public_token (не reference_code); остальные — по reference_code.
_CUSTOMER_URL = {
    "order": ("storefront-order", "reference_code"),
    "booking": ("storefront-termin-ok", "reference_code"),
    "stay": ("storefront-stay-ok", "reference_code"),
    "ticket": ("storefront-ticket-ok", "reference_code"),
    "job": ("storefront-angebot", "public_token"),
    "reservation": ("storefront-confirmation", "reference_code"),
}

TRANSACTION_KINDS = tuple(_KIND_MODEL)

# У Reservation.status НЕТ choices → нет get_status_display(); даём читаемые
# немецкие подписи сами (иначе показали бы сырой код статуса).
_RESERVATION_STATUS_LABELS = {
    "pending": "Reserviert",
    "confirmed": "Bestätigt",
    "cancelled": "Storniert",
    "expired": "Abgelaufen",
    "fulfilled": "Eingelöst",
}

# kind → короткая немецкая подпись вкладки доски (= заголовки разделов ЛК).
KIND_LABEL = {
    "order": "Bestellungen",
    "booking": "Termine",
    "stay": "Übernachtungen",
    "ticket": "Tickets",
    "job": "Aufträge",
    "reservation": "Reservierungen",
}

# Последних записей на вкладку доски (UD1-3): свежие сверху, счётчик по стадиям.
BOARD_LIMIT = 50


@dataclass(frozen=True)
class Transaction:
    """Нормализованный вид входящей транзакции. `allowed_actions` — список
    ``{target, label, stage}`` (переходы FSM из текущего статуса)."""

    kind: str
    pk: object
    reference_code: str
    customer: object
    title: str
    subtotal_display: str
    currency: str
    status: str
    status_label: str
    pipeline_stage: str
    payment_method: str
    created_at: object
    detail_url_customer: str
    manage_url: str
    allowed_actions: list = field(default_factory=list)


def _money_str(value, currency: str = "EUR") -> str:
    """DE-строка суммы из значения в евро (Decimal/int/float). None/≤0 → ''."""
    if value in (None, ""):
        return ""
    try:
        d = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return ""
    if d <= 0:
        return ""
    s = f"{d:.2f}".replace(".", ",")
    return f"{s} €" if currency == "EUR" else f"{s} {currency}"


def _cents(value) -> Decimal | None:
    """Центы (int) → евро (Decimal) или None для пустого/нулевого."""
    if not value:
        return None
    return Decimal(value) / 100


# --- per-kind извлечение title/суммы/валюты (только атрибуты объекта) ---------


def _order_fields(o):
    return {"title": f"#{o.reference_code}", "amount": o.total, "currency": o.currency or "EUR"}


def _booking_fields(b):
    name = str(b.service or b.resource or "") or b.reference_code
    title = f"{name} · {b.start:%d.%m. %H:%M}" if b.start else name
    return {"title": title, "amount": _cents(b.total_cents), "currency": "EUR"}


def _stay_fields(s):
    name = str(s.unit or "") or s.reference_code
    return {
        "title": f"{name} · {s.arrival:%d.%m.}–{s.departure:%d.%m.}",
        "amount": _cents(s.total_cents),
        "currency": "EUR",
    }


def _ticket_fields(t):
    return {"title": f"{t.event} ×{t.quantity}", "amount": _cents(t.total_cents), "currency": "EUR"}


def _job_fields(j):
    return {
        "title": j.title or f"#{j.reference_code}",
        "amount": j.gross,
        "currency": j.currency or "EUR",
    }


def _reservation_fields(r):
    promo = r.promotion
    price = getattr(promo, "new_price", None)
    amount = (price * r.quantity) if price else None
    return {
        "title": str(promo),
        "amount": amount,
        "currency": getattr(promo, "currency", "EUR") or "EUR",
    }


_FIELDS = {
    "order": _order_fields,
    "booking": _booking_fields,
    "stay": _stay_fields,
    "ticket": _ticket_fields,
    "job": _job_fields,
    "reservation": _reservation_fields,
}


# --- ленивые резолверы модели/FSM (без импорта на загрузке модуля) ------------


def model_for(kind: str):
    """Модель kind через apps.get_model (ленивая; неизвестный kind → KeyError)."""
    from django.apps import apps as django_apps

    return django_apps.get_model(_KIND_MODEL[kind])


def sm_for(kind: str):
    """Инстанс FSM-подкласса kind (ленивый импорт по строковому пути)."""
    module_path, cls_name = _KIND_SM[kind]
    return getattr(import_module(module_path), cls_name)()


def allowed_actions_for(kind: str, status: str) -> list[dict]:
    """Переходы FSM из `status`: ``[{target, label, stage}]`` (читает allowed_targets,
    подписи — из pipeline; логику переходов не дублирует)."""
    return [
        {
            "target": t,
            "label": pipeline.action_label(kind, t),
            "stage": pipeline.stage_for(kind, t),
            "danger": pipeline.is_danger(t),
        }
        for t in sm_for(kind).allowed_targets(status)
    ]


def _status_label(kind: str, obj) -> str:
    """Читаемая подпись статуса. `get_status_display()` (choices) где есть; у
    Reservation (без choices) — свой словарь; иначе сырой статус."""
    getter = getattr(obj, "get_status_display", None)
    if callable(getter):
        return getter()
    if kind == "reservation":
        return _RESERVATION_STATUS_LABELS.get(obj.status, obj.status)
    return obj.status


def _customer_url(kind: str, obj) -> str:
    name, attr = _CUSTOMER_URL[kind]
    try:
        return reverse(name, args=[getattr(obj, attr)])
    except NoReverseMatch:
        return ""


def _manage_url(kind: str, obj) -> str:
    """Кабинетная ссылка «управлять»: деталь, где есть (order/job/ticket→событие),
    иначе список/календарь модуля. NoReverseMatch → '' (без падения)."""
    try:
        if kind == "order":
            return reverse("orders:order-detail", args=[obj.pk])
        if kind == "job":
            return reverse("jobs:detail", args=[obj.pk])
        if kind == "ticket":
            return reverse("events:detail", args=[obj.event_id])
        if kind == "booking":
            return reverse("booking:calendar")
        if kind == "stay":
            # FB-11: карточка брони (была ссылка на общий календарь)
            return reverse("stays:booking-detail", args=[obj.pk])
        if kind == "reservation":
            return reverse("promotions:reservation-list")
    except NoReverseMatch:
        return ""
    return ""


def transaction_for(kind: str, obj) -> Transaction:
    """Нормализовать транзакцию `kind` к `Transaction`.

    `status_label` = `obj.get_status_display()` (у Reservation без choices — сырое
    значение, как в ЛК); `subtotal_display` — готовая DE-строка; `payment_method`
    — read-only из модели (E-7: только Order; иначе ''). Неизвестный kind →
    ValueError. Статус только читается.
    """
    if kind not in _FIELDS:
        raise ValueError(f"unknown transaction kind: {kind!r} (known: {TRANSACTION_KINDS})")
    f = _FIELDS[kind](obj)
    return Transaction(
        kind=kind,
        pk=obj.pk,
        reference_code=obj.reference_code,
        customer=obj.customer,
        title=f["title"],
        subtotal_display=_money_str(f["amount"], f["currency"]),
        currency=f["currency"],
        status=obj.status,
        status_label=_status_label(kind, obj),
        pipeline_stage=pipeline.stage_for(kind, obj.status),
        payment_method=getattr(obj, "payment_method", "") or "",
        created_at=obj.created_at,
        detail_url_customer=_customer_url(kind, obj),
        manage_url=_manage_url(kind, obj),
        allowed_actions=allowed_actions_for(kind, obj.status),
    )


# --- UD1-3: кабинетный резолвер транзакций (фундамент доски) ------------------

# kind → related-поля для select_related (без N+1 в title/customer).
_SELECT_RELATED = {
    "order": ("customer",),
    "booking": ("customer", "service", "resource"),
    "stay": ("customer", "unit"),
    "ticket": ("customer", "event"),
    "job": ("customer",),
    "reservation": ("customer", "promotion"),
}


def _managed_queryset(kind):
    """Базовый queryset kind для кабинета: свежие сверху, с select_related."""
    return model_for(kind).objects.select_related(*_SELECT_RELATED[kind]).order_by("-created_at")


def manage_sections_for(tenant, limit: int = BOARD_LIMIT) -> list[dict]:
    """Секции доски по активным транзакционным модулям тенанта.

    Одна секция на активный kind (`is_module_active`): последние `limit`
    транзакций (нормализованных), колонки конвейера и счётчик по стадиям.
    Пустой активный модуль тоже даёт секцию (вкладка с нулём) — чтобы владелец
    видел все свои каналы продаж. Порядок kind — как TRANSACTION_KINDS.
    """
    out = []
    # W5: пер-тенантные настройки доски (переименование/порядок/скрытие колонок).
    from apps.tenants import siteconfig

    board_cfg = siteconfig.normalize_board(
        (getattr(tenant, "site_config", None) or {}).get("board")
    )
    for kind in TRANSACTION_KINDS:
        module = KIND_MODULE[kind]
        if not tenant.is_module_active(module):
            continue
        txs = [transaction_for(kind, obj) for obj in _managed_queryset(kind)[:limit]]
        counts = {stage: 0 for stage in pipeline.STAGES}
        for tx in txs:
            counts[tx.pipeline_stage] = counts.get(tx.pipeline_stage, 0) + 1
        columns = pipeline.resolve_columns(kind, board_cfg)
        for col in columns:  # число карточек в колонке — в шапку колонки
            col["count"] = counts.get(col["stage"], 0)
        out.append(
            {
                "kind": kind,
                "module": module,
                "label": KIND_LABEL[kind],
                "columns": columns,
                "transactions": txs,
                "stage_counts": counts,
                "total": len(txs),
            }
        )
    return out
