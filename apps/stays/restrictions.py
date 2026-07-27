"""G12: правила продаж («Verkaufsregeln», revenue management) — резолвер.

Ограничения ОНЛАЙН-продаж отеля поверх `StayUnit.min_nights`: сезонный
min/max-stay, запрет заезда/выезда по дням недели (CTA/CTD), окно бронирования
(глубина + минимальный срок до заезда). Хранение — `StaySettings.restriction_rules`
(JSON, паттерн G4) + `max_advance_days`/`min_advance_days`.

Семантика (стандарт PMS): min_nights / max_nights / no_checkin матчатся по ДАТЕ
ЗАЕЗДА в периоде правила; no_checkout — по дате ВЫЕЗДА. Несколько подходящих
правил → строжайшее (max(min), min(max>0), объединение запретов). Гейтится
ТОЛЬКО витрина — кабинет владельца (walk-in/телефон) правила не ограничивают.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone


def _parse(day: str) -> date | None:
    try:
        return date.fromisoformat(day)
    except (TypeError, ValueError):
        return None


def _in_period(day: date, rule: dict) -> bool:
    start = _parse(rule.get("start", ""))
    end = _parse(rule.get("end", ""))
    if start and day < start:
        return False
    return not (end and day > end)


def _rules_for(settings_obj, unit) -> list[dict]:
    unit_pk = str(getattr(unit, "pk", unit))
    return [
        r
        for r in settings_obj.clean_restriction_rules()
        if not r.get("unit") or r["unit"] == unit_pk
    ]


def violation(unit, arrival: date, departure: date, *, today: date | None = None):
    """(code, n) первого нарушения правил продаж или None (бронь допустима).

    Коды: "window" (глубина бронирования, n=дней), "lead" (мин. срок до заезда,
    n=дней), "rule_min_nights" (n=ночей), "rule_max_nights" (n=ночей),
    "no_checkin" / "no_checkout" (n=None). Порядок проверки — окно → правила.
    """
    from .models import StaySettings

    settings_obj = StaySettings.load()
    today = today or timezone.localdate()
    if settings_obj.max_advance_days and arrival > today + timedelta(
        days=settings_obj.max_advance_days
    ):
        return ("window", settings_obj.max_advance_days)
    if settings_obj.min_advance_days and arrival < today + timedelta(
        days=settings_obj.min_advance_days
    ):
        return ("lead", settings_obj.min_advance_days)

    nights = (departure - arrival).days
    min_nights = 0
    max_nights = 0
    for rule in _rules_for(settings_obj, unit):
        if _in_period(arrival, rule):
            min_nights = max(min_nights, rule["min_nights"])
            if rule["max_nights"]:
                max_nights = (
                    rule["max_nights"] if not max_nights else min(max_nights, rule["max_nights"])
                )
            if arrival.weekday() in rule["no_checkin"]:
                return ("no_checkin", None)
        if _in_period(departure, rule) and departure.weekday() in rule["no_checkout"]:
            return ("no_checkout", None)
    if min_nights and nights < min_nights:
        return ("rule_min_nights", min_nights)
    if max_nights and nights > max_nights:
        return ("rule_max_nights", max_nights)
    return None


def message(code: str, n=None) -> str:
    """Человеческий текст причины отказа (msgid 1:1 с _buybox_stay_unavailable)."""
    from django.utils.translation import gettext as _

    if code == "window":
        return _("Bookings are possible at most %(n)s days in advance.") % {"n": n}
    if code == "lead":
        return _("Bookings must be made at least %(n)s days before arrival.") % {"n": n}
    if code == "rule_min_nights":
        return _("These dates require a stay of at least %(n)s nights.") % {"n": n}
    if code == "rule_max_nights":
        return _("These dates allow a stay of at most %(n)s nights.") % {"n": n}
    if code == "no_checkin":
        return _("Check-in is not possible on this weekday — please pick another arrival day.")
    if code == "no_checkout":
        return _("Check-out is not possible on this weekday — please pick another departure day.")
    return _("Sorry, these dates are not available. Please try another range.")
