"""KA-W1: время самовывоза — окна из часов работы, ёмкость, отсечка.

`Order.pickup_slot` существует с orders/0001 и его уже читают Auftragsbuch, карточка
сделки и «Heute», но выбрать время на витрине было нельзя. Здесь — сетка окон и
проверка выбора; запись (с блокировкой под гонкой) — в `services.create_order`.

Настройка — `site_config["pickup_slots"]` (см. `siteconfig.normalize_pickup_slots`);
нет ключа → модуль молчит, чекаут прежний.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.tenants import openinghours


class SlotFull(Exception):
    """Окно самовывоза заполнилось, пока покупатель оформлял заказ."""


# Брошенная онлайн-оплата (Stripe Checkout не завершён) держит окно не дольше этого.
UNPAID_ONLINE_HOLD = timedelta(minutes=30)


def config(tenant) -> dict | None:
    from apps.tenants import siteconfig

    return siteconfig.normalize_pickup_slots(
        (getattr(tenant, "site_config", None) or {}).get("pickup_slots")
    )


def _utc(dt):
    return dt.astimezone(UTC).replace(microsecond=0)


def _taken(tenant, start, end) -> Counter:
    """Занятость окон (ключ — UTC). Не считаются отменённые (включая свои статусы
    владельца) и брошенная онлайн-оплата старше UNPAID_ONLINE_HOLD."""
    from apps.core import status_registry

    from .models import Order

    abandoned = Q(
        payment_method=Order.METHOD_STRIPE,
        created_at__lt=timezone.now() - UNPAID_ONLINE_HOLD,
    ) & ~Q(payment_state=Order.PAYMENT_PAID)
    rows = (
        Order.objects.filter(
            fulfillment=Order.FULFILLMENT_PICKUP,
            pickup_slot__gte=start,
            pickup_slot__lt=end,
        )
        .exclude(status__in=status_registry.cancelled_statuses_for("order", tenant))
        .exclude(abandoned)
        .values_list("pickup_slot", flat=True)
    )
    return Counter(_utc(dt) for dt in rows)


def slots_for(tenant, now=None, cfg=None) -> list[tuple]:
    """[(date, [(aware_dt, remaining|None), …]), …] — только дни, где есть окна.

    Окно предлагается, если начинается не раньше now + lead и целиком лежит в часах
    работы; полностью занятые окна не показываются. remaining=None — без лимита."""
    cfg = cfg if cfg is not None else config(tenant)
    if not cfg:
        return []
    hours = openinghours.normalize(getattr(tenant, "opening_hours_structured", None))
    if not hours:
        return []
    now = timezone.localtime(now or timezone.now())
    earliest = now + timedelta(minutes=cfg["lead"])
    step = timedelta(minutes=cfg["step"])
    capacity = cfg["capacity"]
    grid = []
    for offset in range(cfg["days"]):  # календарные дни, начиная с сегодня
        day = (now + timedelta(days=offset)).date()
        rng = hours.get(str(day.weekday()))
        if not rng:
            continue
        opens = openinghours._parse_hhmm(rng[0])
        closes = openinghours._parse_hhmm(rng[1])
        # Шаги — в UTC: настенная арифметика zoneinfo в ночь перевода часов дала бы
        # несуществующее (весна) или сдвоенное (осень) окно.
        start = _utc(timezone.make_aware(datetime.combine(day, opens)))
        end = _utc(timezone.make_aware(datetime.combine(day, closes)))
        day_slots = []
        slot = start
        while slot + step <= end:
            if slot >= earliest:
                day_slots.append(slot)
            slot += step
        if day_slots:
            grid.append((day, day_slots))
    if not grid:
        return []
    taken = _taken(tenant, grid[0][1][0], grid[-1][1][-1] + step) if capacity else Counter()
    out = []
    for day, day_slots in grid:
        row = []
        for slot in day_slots:
            if capacity:
                left = capacity - taken.get(slot, 0)
                if left <= 0:
                    continue
                row.append((slot, left))
            else:
                row.append((slot, None))
        if row:
            out.append((day, row))
    return out


def parse(raw):
    """ISO-строка из формы → aware datetime (локальная зона) или None."""
    value = (raw or "").strip()
    if not value or len(value) > 40:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return _utc(dt)


def validate(tenant, raw, now=None, cfg=None):
    """Выбор покупателя → aware datetime из текущей сетки, иначе None (fail-closed)."""
    chosen = parse(raw)
    if chosen is None:
        return None
    for _day, row in slots_for(tenant, now=now, cfg=cfg):
        for slot, _left in row:
            if slot == chosen:
                return slot
    return None


# Защита ограниченных окон от «выкупа» анонимными заказами без оплаты: один контакт
# держит не больше стольких будущих окон (ревью безопасности батча C).
MAX_OPEN_PER_CONTACT = 3


def contact_holds_too_many(email: str, phone: str, tenant=None, now=None) -> bool:
    from django.db.models import Q

    from apps.core import status_registry
    from apps.core.contacts import phone_candidates_regex, phone_key

    from .models import Order

    email, phone = (email or "").strip(), (phone or "").strip()
    key = phone_key(phone)
    regex = phone_candidates_regex(phone) if key else ""
    who = Q()
    if email:
        who |= Q(customer__email__iexact=email)
    if regex:
        # KA-12 E6.6: «0171 …» и «+49 171 …» — один контакт; хвост из БД — кандидаты,
        # точное совпадение — по ключу (чужой номер с тем же хвостом не в счёт).
        who |= Q(customer__phone__regex=regex)
    if not who:
        return False
    rows = (
        Order.objects.filter(who, pickup_slot__gte=now or timezone.now())
        .exclude(status__in=status_registry.cancelled_statuses_for("order", tenant))
        .values_list("customer__email", "customer__phone")
    )
    held = sum(
        1
        for row_email, row_phone in rows
        if (email and (row_email or "").lower() == email.lower())
        or (key and phone_key(row_phone) == key)
    )
    return held >= MAX_OPEN_PER_CONTACT


def claim(slot, capacity, tenant=None) -> None:
    """Под гонкой: внутри транзакции create_order. Блокировка на окно (схема в ключе —
    advisory-блокировки общие на всю БД), пересчёт, SlotFull при заполненном окне."""
    if not slot or not capacity:
        return
    tenant = tenant or getattr(connection, "tenant", None)
    slot = _utc(slot)
    key = f"pickup:{connection.schema_name}:{slot.isoformat()}"
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])
    if _taken(tenant, slot, slot + timedelta(seconds=1)).get(slot, 0) >= capacity:
        raise SlotFull()


def resolve_from_post(tenant, post, *, delivery=False, optional=False, table=False):
    """KA-12 E2.7: общий разбор выбранного времени самовывоза (корзина, покупка по
    акции, принятие предложения). → (slot | None, capacity, error | "").

    Опция выключена / доставка / заказ за столиком → (None, 0, "") — форма прежняя."""
    from django.utils.translation import gettext as _

    cfg = None if delivery or table else config(tenant)
    if not cfg:
        return None, 0, ""
    raw = post.get("pickup_slot", "")
    slot = validate(tenant, raw, cfg=cfg)
    if slot is None and (raw or not optional):
        if not slots_for(tenant, cfg=cfg):
            return None, 0, _("Zurzeit keine Abholzeiten verfügbar.")
        return None, 0, _("Bitte wählen Sie eine Abholzeit.")
    capacity = cfg["capacity"]
    if (
        slot
        and capacity
        and contact_holds_too_many(post.get("email", ""), post.get("phone", ""), tenant)
    ):
        return (
            None,
            0,
            _("Sie haben bereits mehrere offene Abholzeiten. Bitte melden Sie sich bei uns."),
        )
    return slot, capacity, ""


def context(tenant, *, table=False) -> dict:
    """Данные партиала `_pickup_slot_choice.html` (корзина/акция/предложение)."""
    cfg = None if table else config(tenant)
    return {
        "pickup_slot_enabled": bool(cfg),
        "pickup_slot_days": slots_for(tenant, cfg=cfg) if cfg else [],
    }
