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
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

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
# X1: подписи были голыми немецкими строками — на немецком экране незаметно, но
# в кабинете на en/tr/ru/uk выводился немецкий. msgid уже есть во всех 5 каталогах.
_RESERVATION_STATUS_LABELS = {
    "pending": _("Reserviert"),
    "confirmed": _("Bestätigt"),
    "cancelled": _("Storniert"),
    "expired": _("Abgelaufen"),
    "fulfilled": _("Eingelöst"),
}


def builtin_status_labels(kind: str) -> dict:
    """{code: подпись} ВСТРОЕННЫХ статусов kind: choices модели, у Reservation
    (без choices) — словарь выше. SM-3: общий фолбэк панелей статусов
    (status_manager / transition_rules) — иначе reservation показывал сырые коды."""
    labels = dict(getattr(model_for(kind), "STATUSES", []) or [])
    if not labels and kind == "reservation":
        return dict(_RESERVATION_STATUS_LABELS)
    return labels


# kind → короткая немецкая подпись вкладки доски (= заголовки разделов ЛК).
KIND_LABEL = {
    "order": _("Bestellungen"),
    "booking": _("Termine"),
    "stay": _("Übernachtungen"),
    "ticket": _("Tickets"),
    "job": _("Aufträge"),
    # VK-8 (фидбэк владельца 2026-08-20): «Reservierungen» не говорило, ЧТО это.
    # С волны PL (2026-08-03/04) покупка по акции создаёт ОБЫЧНЫЙ заказ/бронь —
    # здесь остались только резервы, созданные до неё (легаси-сущность
    # promotions.Reservation; витрина в неё больше не пишет).
    "reservation": _("Aktions-Reservierungen (alt)"),
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
    # VS-3: СЫРАЯ сумма рядом с готовой строкой — чтобы потребителям (справочный
    # итог прикреплённых услуг) не приходилось разбирать «85,00 €» обратно.
    amount_value: object
    currency: str
    status: str
    status_label: str
    pipeline_stage: str
    payment_method: str
    created_at: object
    detail_url_customer: str
    manage_url: str
    allowed_actions: list = field(default_factory=list)
    # LS-6: открытый ПРИОРИТЕТНЫЙ тред inbox с ref на эту сделку («⚠️ Problem»).
    has_problem: bool = False
    # W10-5: карточка доски показывает поле трек-номера (заказ-доставка с
    # доступным переходом shipped) — письмо «versendet» уходит с Sendungsnummer.
    needs_tracking: bool = False
    # VS-2c: «когда» сделки — дата мероприятия (заявка), выдачи (заказ), заезда
    # (бронь номера), записи (термин), события (билет). Доска сортируется по ней:
    # завтрашний корпоратив важнее свадьбы в сентябре, созданной раньше.
    when: object = None
    when_note: str = ""  # «80 Gäste» — вторая деталь строки «когда»
    deadline: object = None  # срок сметы (Job.valid_until) — бейдж «истекает/просрочено»
    # Просрочка считается НА СЕРВЕРЕ: карточку перерисовывает kanban_action со
    # своим (маленьким) контекстом — переменная `today` из шаблона доски туда бы
    # не доехала, и бейдж молча потерял бы красный цвет.
    deadline_overdue: bool = False
    # VS-3: связь «якорь ↔ прикреплённые сделки». `linked_children` — спутники
    # этой сделки (велопрокат/трансфер к брони), `linked_anchor` — к чему
    # прикреплена она сама. Заполняет `manage_sections_for` БАТЧЕМ (deal_links.
    # for_cards): на карточку запросов не приходится.
    linked_children: tuple = ()
    linked_anchor: object = None
    # VK-8: продажа пришла ИЗ АКЦИИ. Такой заказ ничем не отличается от обычного
    # (тот же движок, склад, письма) — но владелец обязан видеть, что позиция
    # ушла по акционной цене. Источник — Order.source_channel="promo", который
    # ставит promotions.services.purchase; лишних запросов нет.
    from_promo: bool = False


def _is_overdue(deadline) -> bool:
    """Срок сметы прошёл (сравниваем по дате; None → False)."""
    if not deadline:
        return False
    from django.utils import timezone

    value = deadline.date() if hasattr(deadline, "date") else deadline
    return value < timezone.localdate()


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
    return {
        "title": f"#{o.reference_code}",
        "amount": o.total,
        "currency": o.currency or "EUR",
        "when": o.pickup_slot,
    }


def _booking_fields(b):
    name = str(b.service or b.resource or "") or b.reference_code
    title = f"{name} · {b.start:%d.%m. %H:%M}" if b.start else name
    return {"title": title, "amount": _cents(b.total_cents), "currency": "EUR", "when": b.start}


def _stay_fields(s):
    name = str(s.unit or "") or s.reference_code
    return {
        "title": f"{name} · {s.arrival:%d.%m.}–{s.departure:%d.%m.}",
        "amount": _cents(s.total_cents),
        "currency": "EUR",
        "when": s.arrival,
    }


def _ticket_fields(t):
    return {
        "title": f"{t.event} ×{t.quantity}",
        "amount": _cents(t.total_cents),
        "currency": "EUR",
        "when": getattr(t.event, "starts_at", None),
    }


def _job_fields(j):
    # VS-2c: у заявки «когда» — ДАТА МЕРОПРИЯТИЯ (волна AF-1), а не дата создания:
    # кейтеринг живёт датами. `guest_count` идёт второй строкой карточки.
    note = ""
    if j.guest_count:
        note = ngettext("%(n)d Gast", "%(n)d Gäste", j.guest_count) % {"n": j.guest_count}
    return {
        "title": j.title or f"#{j.reference_code}",
        "amount": j.gross,
        "currency": j.currency or "EUR",
        "when": j.event_date,
        "when_note": note,
        "deadline": j.valid_until,
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


def kinds_with_sales(tenant) -> set[str]:
    """Kind'ы, по которым есть хотя бы одна сделка (модуль активен + exists()).

    Для правила видимости вкладок Verkäufe: «допродажные» типы появляются с
    первой продажей. До 6 запросов `SELECT 1 … LIMIT 1` — дешевле, чем любая
    материализация; схема тенанта изолирует выборку сама."""
    out = set()
    for kind in TRANSACTION_KINDS:
        if not tenant.is_module_active(KIND_MODULE[kind]):
            continue
        try:
            if model_for(kind).objects.exists():
                out.add(kind)
        except Exception:  # noqa: BLE001 — сломанный kind не роняет страницу продаж
            continue
    return out


def allowed_actions_for(kind: str, status: str, subset: dict | None = None, obj=None) -> list[dict]:
    """Переходы FSM из `status`: ``[{target, label, stage}]`` (читает allowed_targets,
    подписи — из pipeline; логику переходов не дублирует). FB-3: `subset` (правила
    переходов владельца {src: [dst]}) СКРЫВАЕТ не-danger переходы для отображения —
    FSM/apply() при этом не трогаются (жёсткий пол)."""
    from apps.core import transition_rules

    targets = [
        t
        for t in sm_for(kind).allowed_targets(status)
        if subset is None or transition_rules.keep_target(status, t, subset, kind=kind)
    ]
    # W7c (аудит 2026-08-05): заказ — picked_up/shipped взаимоисключающие по способу
    # получения. Карточка заказа это фильтровала, доска — нет: владельцу доставочного
    # заказа предлагалось «Abgeholt» (и письмо о самовывозе клиенту). Зеркалим
    # фильтр order_detail.html здесь — для всех канбан-поверхностей.
    if kind == "order" and obj is not None:
        drop = "picked_up" if getattr(obj, "is_delivery", False) else "shipped"
        targets = [t for t in targets if t != drop]

    # SM-3: danger кастом-цели — из дескриптора (роль cancelled → красная кнопка,
    # как builtin-отмена); pipeline.DANGER_TARGETS заморожен на импорте и кастомов
    # не знает.
    def _danger(t):
        from apps.core import status_registry

        d = status_registry.resolve(kind, t)
        return d.is_danger if d is not None else pipeline.is_danger(t)

    return [
        {
            "target": t,
            "label": pipeline.action_label(kind, t),
            "stage": pipeline.stage_for(kind, t),
            "danger": _danger(t),
        }
        for t in targets
    ]


def _status_label(kind: str, obj, labels: dict | None = None) -> str:
    """Читаемая подпись статуса. FB-4a/b: своё имя владельца (`labels`, только доска
    КАБИНЕТА — не клиентский аккаунт) поверх дефолта. Дефолт: `get_status_display()`
    (choices) где есть; у Reservation (без choices) — свой словарь; иначе сырой статус."""
    if labels:
        custom = labels.get(obj.status)
        if custom:
            return custom
    # FB-3 Вариант B Phase 6: кастом-статус → его label (get_status_display вернул бы код).
    from apps.core import status_registry

    d = status_registry.resolve(kind, obj.status)
    if d is not None and not d.builtin and d.label:
        return d.label
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
            # Фидбэк 2026-08-05: карточка брони (была ссылка на общий календарь —
            # «перекидывает на непонятную страницу», зеркало FB-11 у stays).
            return reverse("booking:booking-detail", args=[obj.pk])
        if kind == "stay":
            # FB-11: карточка брони (была ссылка на общий календарь)
            return reverse("stays:booking-detail", args=[obj.pk])
        if kind == "reservation":
            return reverse("promotions:reservation-list")
    except NoReverseMatch:
        return ""
    return ""


def transaction_for(
    kind: str, obj, labels: dict | None = None, transitions: dict | None = None
) -> Transaction:
    """Нормализовать транзакцию `kind` к `Transaction`.

    `status_label` = `obj.get_status_display()` (у Reservation без choices — сырое
    значение, как в ЛК); `labels` (FB-4a/b, {status: своё-имя}) переопределяет подпись,
    `transitions` (FB-3, {src: [dst]}) скрывает не-danger переходы — ОБА только на доске
    кабинета (клиентский аккаунт зовёт без них). `subtotal_display` — готовая DE-строка;
    `payment_method` — read-only из модели (E-7: только Order; иначе ''). Неизвестный kind
    → ValueError. Статус только читается.
    """
    if kind not in _FIELDS:
        raise ValueError(f"unknown transaction kind: {kind!r} (known: {TRANSACTION_KINDS})")
    f = _FIELDS[kind](obj)
    actions = allowed_actions_for(kind, obj.status, transitions, obj=obj)
    needs_tracking = (
        kind == "order"
        and bool(getattr(obj, "is_delivery", False))
        and any(a["target"] == "shipped" for a in actions)
    )
    return Transaction(
        kind=kind,
        pk=obj.pk,
        reference_code=obj.reference_code,
        customer=obj.customer,
        title=f["title"],
        subtotal_display=_money_str(f["amount"], f["currency"]),
        amount_value=f.get("amount"),
        currency=f["currency"],
        status=obj.status,
        status_label=_status_label(kind, obj, labels),
        pipeline_stage=pipeline.stage_for(kind, obj.status),
        payment_method=getattr(obj, "payment_method", "") or "",
        created_at=obj.created_at,
        detail_url_customer=_customer_url(kind, obj),
        manage_url=_manage_url(kind, obj),
        allowed_actions=actions,
        needs_tracking=needs_tracking,
        from_promo=(getattr(obj, "source_channel", "") or "") == "promo",
        when=f.get("when"),
        when_note=f.get("when_note", ""),
        deadline=f.get("deadline"),
        deadline_overdue=_is_overdue(f.get("deadline")),
    )


def apply_action(kind: str, obj, target: str, actor=None, extra=None):
    """W10-5: ЕДИНАЯ точка применения статуса со всех поверхностей (доска/
    Verkäufe/карточка/per-app вьюхи) — закрывает расхождения спец-полей.

    `extra` — поля поверхности (обычно request.POST): сейчас — `tracking_code`
    у заказа при переходе shipped; пишется ДО apply, чтобы письмо FSM ушло уже
    с Sendungsnummer (shipped_at ставит FSM сам — W7c). Прочие эффекты
    (письма/склад/деньги/таймстемпы) остаются в FSM on_transition."""
    extra = extra or {}
    if kind == "order" and target == "shipped":
        code = (extra.get("tracking_code") or "").strip()[:100]
        if code and code != (getattr(obj, "tracking_code", "") or ""):
            obj.tracking_code = code
            obj.save(update_fields=["tracking_code", "updated_at"])
    return sm_for(kind).apply(obj, target, actor=actor)


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


# W7c: поле «даты события» для сортировки списков (вид Liste на Verkäufe) —
# бронь на завтра, созданная месяц назад, важнее прошлогодней, созданной вчера.
_EVENT_ORDER = {"stay": "-arrival", "booking": "-start"}

# kind → поля, из которых складывается заголовок карточки (см. _FIELDS): по ним
# тоже ищем. У заказа заголовок = сам код, у резерва — название акции.
_TITLE_SEARCH = {
    "booking": ("resource__name", "service__name"),
    "stay": ("unit__name",),
    "job": ("title",),
    "ticket": ("event__title",),
    # У резерва заголовок — название акции, а `Promotion.title` это JSONField
    # (i18n-словарь): `icontains` по нему в Postgres не работает. Легаси-kind
    # ищется по коду и клиенту, как раньше.
}

# VS-2c: порядок ДОСКИ — по дате события ПО ВОЗРАСТАНИЮ (ближайшее сверху), у
# заявок это дата мероприятия (AF-1). Пустая дата уезжает в конец (nulls_last),
# внутри — свежие сверху. Список («Liste») сохраняет свой порядок (_EVENT_ORDER).
_BOARD_ORDER = {
    "job": "event_date",
    "order": "pickup_slot",
    "stay": "arrival",
    "booking": "start",
}


def status_filter_options(tenant, kind: str) -> list[tuple]:
    """X2c: варианты фильтра статуса для generic-списка продаж.

    Источник — реестр статусов (встроенные + КАСТОМНЫЕ владельца, SM-3) с
    учётом его собственных подписей (FB-4a/b). Раньше фильтр статуса был
    только на легаси-странице заявок и в списке заказов."""
    from apps.core import status_labels, status_registry

    custom = status_labels.custom_labels(tenant, kind)
    builtin = builtin_status_labels(kind)
    out = []
    for code, d in status_registry.all_descriptors(kind, tenant).items():
        label = custom.get(code) or builtin.get(code) or getattr(d, "label", "") or code
        out.append((code, label))
    return out


def _managed_queryset(
    kind, event_order: bool = False, q: str = "", status: str = "", board_order: bool = False
):
    """Базовый queryset kind для кабинета: свежие сверху, с select_related.
    `event_order` — сортировка по дате СОБЫТИЯ (W7c, только kind'ы из _EVENT_ORDER).

    X6-2: `q` — поиск по коду сделки и клиенту (имя/e-mail). У ВСЕХ шести kind
    есть `reference_code` и FK `customer` (проверено), поэтому условие общее —
    список Verkäufe искал только у заказов (W10-3), у остальных поиска не было."""
    from django.db.models import Q

    qs = model_for(kind).objects.select_related(*_SELECT_RELATED[kind])
    field = _BOARD_ORDER.get(kind) if board_order else None
    if field:
        # VS-2c: ближайшее событие сверху; сделки без даты — в конец (F(...).asc с
        # nulls_last), внутри — свежие первыми.
        from django.db.models import F

        qs = qs.order_by(F(field).asc(nulls_last=True), "-created_at")
    else:
        order = _EVENT_ORDER.get(kind, "-created_at") if event_order else "-created_at"
        qs = qs.order_by(order)
    if status:
        qs = qs.filter(status=status)  # X2c: фильтр статуса — паритет с легаси-списками
    q = (q or "").strip()
    if q:
        # VS-3 (стенд поймал): владелец ищет сделку по тому, что видит на карточке
        # — «Fahrrad», «Doppelzimmer», — а не по фамилии гостя. К коду и клиенту
        # добавлены поля, из которых складывается ЗАГОЛОВОК карточки (_FIELDS).
        # Выигрывают все поверхности поиска сразу: палитра Ctrl+K (X8), список
        # продаж (X6-2) и пикер привязки (VS-3c).
        condition = (
            Q(reference_code__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(customer__email__icontains=q)
        )
        for lookup in _TITLE_SEARCH.get(kind, ()):
            condition |= Q(**{f"{lookup}__icontains": q})
        qs = qs.filter(condition)
    return qs


# VS-2b (решение владельца 2026-08-20): КОЛОНКА = СТАТУС, а колонки одной стадии
# визуально сгруппированы. Раньше колонок было четыре (канонические стадии), и у
# кейтеринга «Angebot gesendet» (ждём ответа клиента) лежал в одной колонке с
# «Beauftragt» (подтверждено, надо готовить) — доска не отвечала «что горит».
# Стадия остаётся: она задаёт ГРУППУ и роль статуса (эффекты/ёмкость/деньги), а
# пер-тенантные настройки колонок (переименование/скрытие/порядок, W5) продолжают
# управлять ГРУППАМИ — `normalize_board` и его golden не тронуты.
#
# kind → (поле суммы в БД, делитель). Только там, где поле — ТОЧНЫЙ итог сделки:
# у booking/ticket «итог» считается в Python (price+extras−скидка), и агрегат по
# price_cents врал бы. Нет поля → шапка колонки просто без суммы.
_SUM_FIELD = {
    "order": ("total", 1),
    "job": ("gross", 1),
    "stay": ("total_cents", 100),
}


def status_columns(kind: str, tenant, board_cfg: dict | None = None) -> list[dict]:
    """Колонки доски = статусы kind (встроенные ∪ кастом тенанта, SM-3).

    Порядок: группы — в порядке стадий с учётом настроек тенанта
    (`pipeline.resolve_columns`: переименование/скрытие/порядок), внутри группы —
    порядок объявления в реестре. Подпись колонки — своё имя владельца (FB-4a)
    поверх встроенной подписи; у кастом-статуса — его label.
    """
    from apps.core import status_labels, status_registry

    custom_names = status_labels.custom_labels(tenant, kind)
    builtin_names = builtin_status_labels(kind)
    descriptors = status_registry.all_descriptors(kind, tenant)

    groups = pipeline.resolve_columns(kind, board_cfg)  # видимые стадии по порядку
    out = []
    for group in groups:
        for code, d in descriptors.items():
            if d.stage != group["stage"]:
                continue
            label = custom_names.get(code) or (d.label if not d.builtin else "")
            out.append(
                {
                    "status": code,
                    "label": label or builtin_names.get(code, code),
                    "stage": group["stage"],
                    "group_label": group["label"],
                    "custom": not d.builtin,
                }
            )
    return out


def column_groups(columns: list[dict]) -> list[dict]:
    """Полоса групп над колонками: подряд идущие колонки одной стадии.

    Возвращает [{stage, label, span}] — шаблон рисует группу как контейнер своих
    колонок (ширина следует из числа колонок, синхронизировать ничего не нужно).
    """
    out = []
    for col in columns:
        if out and out[-1]["stage"] == col["stage"]:
            out[-1]["columns"].append(col)
            continue
        out.append({"stage": col["stage"], "label": col["group_label"], "columns": [col]})
    return out


def manage_sections_for(
    tenant,
    limit: int = BOARD_LIMIT,
    only: str | None = None,
    event_order: bool = False,
    q: str = "",
    status: str = "",
    board_order: bool = False,
) -> list[dict]:
    """Секции доски по активным транзакционным модулям тенанта.

    Одна секция на активный kind (`is_module_active`): последние `limit`
    транзакций (нормализованных), колонки конвейера и счётчик по стадиям.
    Пустой активный модуль тоже даёт секцию (вкладка с нулём) — чтобы владелец
    видел все свои каналы продаж. Порядок kind — как TRANSACTION_KINDS.
    `only` — собрать ровно один kind (вкладка Verkäufe грузит только себя).
    """
    out = []
    # W5: пер-тенантные настройки доски (переименование/порядок/скрытие колонок).
    from apps.tenants import siteconfig

    board_cfg = siteconfig.normalize_board(
        (getattr(tenant, "site_config", None) or {}).get("board")
    )
    from apps.core import status_labels, transition_rules

    for kind in TRANSACTION_KINDS:
        if only and kind != only:
            continue
        module = KIND_MODULE[kind]
        if not tenant.is_module_active(module):
            continue
        # FB-4a/b: свои имена статусов + FB-3: правила переходов — только доска кабинета.
        labels = status_labels.custom_labels(tenant, kind)
        trans = transition_rules.subset_for(tenant, kind)
        txs = [
            transaction_for(kind, obj, labels, trans)
            for obj in _managed_queryset(kind, event_order, q, status, board_order=board_order)[
                :limit
            ]
        ]
        # LS-6: «⚠️ Problem»-полоса — открытые high-треды с ref на карточки секции.
        # ОДИН запрос на секцию по множеству кодов (не per-card — N+1); ключ =
        # reference_code (то же кладёт problem-кнопка витрины). Fail-safe.
        try:
            from dataclasses import replace as _dc_replace

            from apps.inbox.models import Conversation

            problem_codes = set(
                Conversation.objects.filter(
                    status__in=(Conversation.STATUS_OPEN, Conversation.STATUS_PENDING),
                    priority=Conversation.PRIORITY_HIGH,
                    ref_kind=kind,
                    ref_id__in={tx.reference_code for tx in txs if tx.reference_code},
                ).values_list("ref_id", flat=True)
            )
            if problem_codes:
                txs = [
                    _dc_replace(tx, has_problem=tx.reference_code in problem_codes) for tx in txs
                ]
        except Exception:  # noqa: BLE001 — полоса best-effort, доска важнее
            pass
        # VS-3: связи «якорь ↔ спутники» — ОДИН батч на секцию (тот же паттерн,
        # что problem-полоса выше): владелец видит на карточке брони «🔗 2
        # Zusatzleistungen», а на карточке велопроката — к чему он относится.
        try:
            from dataclasses import replace as _dc_replace

            from apps.core import deal_links

            links = deal_links.for_cards(kind, [tx.pk for tx in txs])
            if links:
                txs = [
                    _dc_replace(
                        tx,
                        linked_children=tuple(links.get(tx.pk, {}).get("children", ())),
                        linked_anchor=links.get(tx.pk, {}).get("anchor"),
                    )
                    for tx in txs
                ]
        except Exception:  # noqa: BLE001 — подсказка о связи не стоит падения доски
            pass
        # V4 (2026-08-03): счётчики честные — по БД, а не по загруженным limit
        # карточкам (при >limit шапки колонок врали). Кастом-статусы тенанта
        # резолвятся тем же реестром, что и карточки.
        counts = {stage: 0 for stage in pipeline.STAGES}
        status_counts: dict[str, int] = {}
        status_sums: dict[str, object] = {}
        try:
            from django.db.models import Count, Sum

            from apps.core import status_registry

            # VS-2c: сумма в шапке колонки — ТЕМ ЖЕ запросом, что и счётчик, и
            # только там, где поле суммы в БД = точный итог сделки (_SUM_FIELD).
            money = _SUM_FIELD.get(kind)
            # `.order_by()` СБРАСЫВАЕТ сортировку модели: иначе Django добавляет её
            # поля в GROUP BY, и агрегат дробится на строку-на-запись (счётчики
            # спасало сложение, а сумма перезаписывалась — ловил замок VS-2c).
            qs = _managed_queryset(kind).order_by().values("status").annotate(n=Count("pk"))
            if money:
                qs = qs.annotate(amount=Sum(money[0]))
            for row in qs:
                d = status_registry.resolve(kind, row["status"], tenant)
                stage = d.stage if d is not None else "intake"
                counts[stage] = counts.get(stage, 0) + row["n"]
                status_counts[row["status"]] = status_counts.get(row["status"], 0) + row["n"]
                if money and row.get("amount"):
                    status_sums[row["status"]] = status_sums.get(row["status"], Decimal(0)) + (
                        Decimal(row["amount"]) / money[1]
                    )
        except Exception:  # noqa: BLE001 — фолбэк: как раньше, по загруженным
            for tx in txs:
                counts[tx.pipeline_stage] = counts.get(tx.pipeline_stage, 0) + 1
                status_counts[tx.status] = status_counts.get(tx.status, 0) + 1
        # VS-2b: колонка = статус; стадия остаётся ГРУППОЙ (полоса над колонками).
        columns = status_columns(kind, tenant, board_cfg)
        for col in columns:
            col["count"] = status_counts.get(col["status"], 0)
            amount = status_sums.get(col["status"])
            col["sum_display"] = _money_str(amount) if amount else ""
        out.append(
            {
                "kind": kind,
                "module": module,
                "label": KIND_LABEL[kind],
                "columns": columns,
                "groups": column_groups(columns),
                "transactions": txs,
                "stage_counts": counts,
                "total": sum(counts.values()),  # V4: честный итог по БД
            }
        )
    return out
