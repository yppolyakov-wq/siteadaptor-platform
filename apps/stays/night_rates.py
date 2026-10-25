"""KA-12 Zimmer Z-3 (E4.6b): массовая правка поночного слоя цен и ограничений.

Единственный писатель ``NightRate``. Ядро — чистые функции (``parse_action``,
``apply_action``, ``plan_changes``): план строится из текущего состояния, в нём
только изменённые ячейки. Запись (``apply_plan``) — одна транзакция под
блокировкой категорий по возрастанию id (как ``book_stay``), план пересчитывается
под блокировкой и сверяется с отпечатком Vorschau: двойной клик «+10 %» не
поднимет цену дважды. Нейтральная строка (ничего не переопределяет) удаляется.
Брони не трогаются — их цена в снимке ``StayBooking.night_prices`` (Z-1).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from . import pricing

MAX_HORIZON_DAYS = 732  # 2 × 366, считая от сегодня
MAX_CELLS = 20_000  # категории × ночи за одну правку
MAX_UNITS = 200  # категорий за одну правку (кап IN-списка и времени блокировки)
MAX_PRICE_CENTS = 9_999_999  # 99 999,99 €
PERCENT_MIN, PERCENT_MAX = -90, 300
_FIELDS = ("price_cents", "stop_sell", "min_nights", "no_checkin", "no_checkout")


class StalePlan(Exception):
    """Данные изменились между Vorschau и «Übernehmen»."""


class PlanRejected(Exception):
    """Действие дало бы недопустимую цену (≤ 0 €) — ничего не записано."""


@dataclass(frozen=True)
class DayState:
    price_cents: int | None = None
    stop_sell: bool = False
    min_nights: int = 0
    no_checkin: bool = False
    no_checkout: bool = False

    @property
    def neutral(self) -> bool:
        """Зеркало CheckConstraint ``stays_nightrate_not_neutral``."""
        return (
            self.price_cents is None
            and not self.stop_sell
            and not self.min_nights
            and not self.no_checkin
            and not self.no_checkout
        )

    def as_tuple(self) -> tuple:
        return tuple(getattr(self, f) for f in _FIELDS)

    @classmethod
    def of(cls, night) -> DayState:
        if night is None:
            return cls()
        return cls(**{f: getattr(night, f) for f in _FIELDS})


@dataclass(frozen=True)
class Action:
    price_mode: str = "keep"  # keep | set | percent | reset
    price_cents: int | None = None
    percent: int | None = None
    stop_sell: bool | None = None  # None — не менять
    min_nights: int | None = None  # None — не менять; 0 — сброс
    no_checkin: bool | None = None
    no_checkout: bool | None = None

    @property
    def is_noop(self) -> bool:
        return self.price_mode == "keep" and all(
            getattr(self, f) is None
            for f in ("stop_sell", "min_nights", "no_checkin", "no_checkout")
        )

    def summary(self) -> dict:
        """Описание для журнала (без ПДн)."""
        out = {"price": self.price_mode}
        if self.price_mode == "set":
            out["price_cents"] = self.price_cents
        if self.price_mode == "percent":
            out["percent"] = self.percent
        for f in ("stop_sell", "min_nights", "no_checkin", "no_checkout"):
            if getattr(self, f) is not None:
                out[f] = getattr(self, f)
        return out


@dataclass(frozen=True)
class Change:
    unit_id: uuid.UUID
    day: date
    before: DayState
    after: DayState

    @property
    def kind(self) -> str:
        if self.after.neutral:
            return "delete"
        return "create" if self.before.neutral else "update"


@dataclass(frozen=True)
class Plan:
    changes: tuple[Change, ...]
    rejected: tuple[tuple[uuid.UUID, date], ...]
    cells: int

    def fingerprint(self, action: Action) -> str:
        """Отпечаток плана: изменения + параметры действия + охват (канонично)."""
        h = hashlib.sha256(repr(sorted(action.summary().items())).encode())
        h.update(f"#{self.cells};".encode())
        for c in self.changes:
            h.update(f"{c.unit_id}|{c.day}|{c.before.as_tuple()}|{c.after.as_tuple()};".encode())
        for unit_id, day in self.rejected:
            h.update(f"!{unit_id}|{day};".encode())
        return h.hexdigest()[:32]

    def counts(self) -> dict:
        out = {"create": 0, "update": 0, "delete": 0}
        for c in self.changes:
            out[c.kind] += 1
        return out


@dataclass(frozen=True)
class ApplyResult:
    created: int
    updated: int
    deleted: int
    nights: int


# ── разбор ввода ────────────────────────────────────────────────────────────


def select_days(von: date, bis: date, weekdays) -> list[date]:
    wd = set(weekdays)
    out, day = [], von
    while day <= bis:
        if day.weekday() in wd:
            out.append(day)
        day += timedelta(days=1)
    return out


def parse_day(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw or "").strip())
    except ValueError:
        return None


def parse_weekdays(values) -> list[int]:
    out = set()
    for raw in values:
        if str(raw).isdigit() and 0 <= int(raw) <= 6:
            out.add(int(raw))
    return sorted(out)


def parse_unit_ids(values) -> tuple[list[uuid.UUID], bool]:
    """(ids, есть_мусор). Мусор — повод отказать, а не тихо отбросить."""
    ids, bad = [], False
    for raw in values:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, AttributeError):
            bad = True
    return list(dict.fromkeys(ids)), bad


def validate_scope(*, n_units, n_requested, garbage, von, bis, weekdays, today) -> list[str]:
    errors = []
    if n_requested > MAX_UNITS:
        errors.append(_("Höchstens %(n)s Kategorien auf einmal.") % {"n": MAX_UNITS})
    if garbage or n_units != n_requested:
        errors.append(_("Unbekannte Kategorie."))
    if not n_requested:
        errors.append(_("Bitte mindestens eine Kategorie wählen."))
    if von is None or bis is None:
        errors.append(_("Bitte einen gültigen Zeitraum angeben."))
        return errors
    if von < today:
        errors.append(_("Zeitraum liegt in der Vergangenheit."))
    if bis < von:
        errors.append(_("Das Enddatum liegt vor dem Startdatum."))
    if bis > today + timedelta(days=MAX_HORIZON_DAYS):
        errors.append(_("Höchstens %(n)s Tage im Voraus.") % {"n": MAX_HORIZON_DAYS})
    if not weekdays:
        errors.append(_("Bitte mindestens einen Wochentag wählen."))
    if not errors:
        cells = n_units * len(select_days(von, bis, weekdays))
        if cells > MAX_CELLS:
            errors.append(
                _("Zu viele Nächte auf einmal (%(n)s). Bitte Zeitraum oder Kategorien verkleinern.")
                % {"n": cells}
            )
    return errors


def _tri(raw) -> bool | None:
    return {"on": True, "off": False}.get(str(raw or "").strip())


def _money_cents(raw) -> int:
    """Цена в центах; ValueError — с текстом для владельца."""
    from apps.core.money import parse_money

    try:
        amount = parse_money(raw)
    except ValueError:
        amount = None
    if amount is None or amount != amount.quantize(Decimal("0.01")):
        raise ValueError(_("Bitte einen gültigen Preis angeben (z. B. 89,00)."))
    cents = int(amount * 100)
    if not 0 < cents <= MAX_PRICE_CENTS:
        raise ValueError(_("Bitte einen gültigen Preis angeben (z. B. 89,00)."))
    return cents


def parse_action(data) -> tuple[Action | None, list[str]]:
    """Разбор формы массовой правки → Action. «nicht ändern» — дефолт каждого поля."""
    errors = []
    mode = str(data.get("price_mode") or "keep")
    if mode not in ("keep", "set", "percent", "reset"):
        mode = "keep"
    price_cents = percent = None
    if mode == "set":
        try:
            price_cents = _money_cents(data.get("price"))
        except ValueError as exc:
            errors.append(str(exc))
    elif mode == "percent":
        raw = str(data.get("percent") or "").strip().replace("+", "").replace(",", ".")
        try:
            percent = int(Decimal(raw)) if raw else None
            if percent is not None and Decimal(raw) != percent:
                percent = None
        except (ArithmeticError, ValueError, OverflowError):
            percent = None
        if percent is None or percent == 0 or not PERCENT_MIN <= percent <= PERCENT_MAX:
            errors.append(
                _("Bitte eine Änderung zwischen %(lo)s und +%(hi)s %% angeben.")
                % {"lo": PERCENT_MIN, "hi": PERCENT_MAX}
            )
    min_mode = str(data.get("min_mode") or "keep")
    min_nights = None
    if min_mode == "reset":
        min_nights = 0
    elif min_mode == "set":
        raw = str(data.get("min_nights") or "").strip()
        if raw.isdigit() and 1 <= int(raw) <= 365:
            min_nights = int(raw)
        else:
            errors.append(_("Mindestaufenthalt: 1 bis 365 Nächte."))
    action = Action(
        price_mode=mode,
        price_cents=price_cents,
        percent=percent,
        stop_sell=_tri(data.get("stop_sell")),
        min_nights=min_nights,
        no_checkin=_tri(data.get("no_checkin")),
        no_checkout=_tri(data.get("no_checkout")),
    )
    if errors:
        return None, errors
    if action.is_noop:
        return None, [_("Keine Änderung ausgewählt.")]
    return action, []


# ── ядро ────────────────────────────────────────────────────────────────────


def apply_action(state: DayState, action: Action, chain_cents: int) -> DayState | None:
    """Новое состояние дня. Меняются ТОЛЬКО поля действия. None — отказ (цена ≤ 0).

    ±% считается от ТЕКУЩЕЙ эффективной цены дня (своя цена дня, иначе цепочка
    сезон → выходные → база, без тарифа)."""
    patch = {}
    if action.price_mode == "set":
        patch["price_cents"] = action.price_cents
    elif action.price_mode == "reset":
        patch["price_cents"] = None
    elif action.price_mode == "percent":
        base = state.price_cents if state.price_cents is not None else chain_cents
        new = int(
            (Decimal(base) * (100 + action.percent) / 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        if new < 1 or new > MAX_PRICE_CENTS:
            return None
        patch["price_cents"] = new
    for f in ("stop_sell", "min_nights", "no_checkin", "no_checkout"):
        value = getattr(action, f)
        if value is not None:
            patch[f] = value
    return replace(state, **patch)


def plan_changes(unit_ids, days, action: Action, existing: dict, chain: dict) -> Plan:
    """Чистое построение плана. ``existing`` — {(unit_id, day): DayState},
    ``chain`` — {(unit_id, day): цена цепочки без своей цены дня}."""
    changes, rejected = [], []
    for unit_id in sorted(unit_ids, key=str):
        for day in days:
            before = existing.get((unit_id, day), DayState())
            after = apply_action(before, action, chain[(unit_id, day)])
            if after is None:
                rejected.append((unit_id, day))
            elif after != before:
                changes.append(Change(unit_id, day, before, after))
    return Plan(tuple(changes), tuple(rejected), len(unit_ids) * len(days))


def load_window(units, days) -> tuple[dict, dict]:
    """(existing, chain) для плана. ``units`` — с prefetch ``season_rates``."""
    if not days:
        return {}, {}
    window = pricing.night_rates_window([u.pk for u in units], min(days), max(days))
    existing, chain = {}, {}
    for unit in units:
        seasons = list(unit.season_rates.all())
        nights = window.get(unit.pk, {})
        for day in days:
            night = nights.get(day)
            if night is not None:
                existing[(unit.pk, day)] = DayState.of(night)
            chain[(unit.pk, day)] = pricing.nightly_price_cents(unit, day, seasons, None)
    return existing, chain


def state_fingerprint(unit_id, day, state: DayState) -> str:
    """Отпечаток СОСТОЯНИЯ одного дня — для формы дня (поля задаются целиком,
    отпечаток плана от действия там не годится): правка поверх чужой — отказ."""
    raw = f"{unit_id}|{day}|{state.as_tuple()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_plan(units, days, action) -> Plan:
    existing, chain = load_window(units, days)
    return plan_changes([u.pk for u in units], days, action, existing, chain)


def apply_plan(
    unit_ids,
    days,
    action: Action,
    *,
    expected_fingerprint="",
    expected_state="",
    actor,
    kind="bulk",
):
    """Записать план одной транзакцией. Пустой план — ничего не делает (повторный
    «set» идемпотентен); иной план, чем в Vorschau, — StalePlan. ``expected_state``
    (одна ячейка, форма дня) — сверка состояния дня вместо отпечатка плана."""
    from apps.audit.services import audit_event

    from .models import NightRate, StayUnit

    if not days or len(unit_ids) > MAX_UNITS:
        raise PlanRejected
    with transaction.atomic():
        # «Сегодня» — внутри транзакции: Vorschau до полуночи, «Übernehmen» после.
        if min(days) < timezone.localdate():
            raise StalePlan
        units = list(
            StayUnit.objects.select_for_update()
            .filter(id__in=list(unit_ids))
            .order_by("id")
            .prefetch_related("season_rates")
        )
        if len(units) != len(set(unit_ids)):
            raise StalePlan  # категорию удалили между Vorschau и записью
        existing, chain = load_window(units, days)
        plan = plan_changes([u.pk for u in units], days, action, existing, chain)
        if expected_state:
            if len(units) != 1 or len(days) != 1:
                raise StalePlan
            current = existing.get((units[0].pk, days[0]), DayState())
            if state_fingerprint(units[0].pk, days[0], current) != expected_state:
                raise StalePlan
        if plan.rejected:
            raise PlanRejected
        if not plan.changes:
            return ApplyResult(0, 0, 0, plan.cells)
        if not expected_state and plan.fingerprint(action) != expected_fingerprint:
            raise StalePlan
        now = timezone.now()
        upserts = [
            NightRate(
                unit_id=c.unit_id,
                day=c.day,
                updated_at=now,
                **{f: getattr(c.after, f) for f in _FIELDS},
            )
            for c in plan.changes
            if c.kind != "delete"
        ]
        if upserts:
            NightRate.objects.bulk_create(
                upserts,
                update_conflicts=True,
                unique_fields=["unit", "day"],
                update_fields=[*_FIELDS, "updated_at"],
                batch_size=500,
            )
        to_delete = {}
        for c in plan.changes:
            if c.kind == "delete":
                to_delete.setdefault(c.unit_id, []).append(c.day)
        for unit_id, del_days in to_delete.items():
            NightRate.objects.filter(unit_id=unit_id, day__in=del_days).delete()
        counts = plan.counts()
        audit_event(
            action=f"stays.night_rates.{kind}",
            resource_type="stay_night_rates",
            resource_id="",
            actor=actor,
            context={
                "units": len(units),
                "von": min(days).isoformat(),
                "bis": max(days).isoformat(),
                "nights": plan.cells,
                "created": counts["create"],
                "updated": counts["update"],
                "deleted": counts["delete"],
                "action": action.summary(),
            },
        )
    for unit in units:
        pricing.forget_night_rates(unit)
    return ApplyResult(counts["create"], counts["update"], counts["delete"], plan.cells)
