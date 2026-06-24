"""R10: график рассрочки билета (чистая логика, без Stripe).

Eligibility + расчёт долей/дат для `Event` (per-event конфиг). Суммы — равный
сплит с остатком центов на первые доли (сумма == total). Даты:
- `fixed` — помесячно от сегодня (`installment_count` долей);
- `until_event` — равномерно между сегодня и `start − installment_lead_days`.

Используется витриной (показать график), R10b (создать `InstallmentCharge`-ы) и
кабинетом. Помесячный сдвиг — `dateutil.relativedelta` (клампит день к длине месяца).
"""

from dateutil.relativedelta import relativedelta


def installments_available(event, total_cents, today, start_date) -> bool:
    """Можно ли предложить рассрочку для суммы (eligibility, R10).

    Включено в событии, ≥2 долей, сумма ≥ минимума и (для until_event) хватает
    времени до дедлайна последней доли.
    """
    if not getattr(event, "allow_installments", False):
        return False
    count = int(event.installment_count or 0)
    if count < 2 or total_cents <= 0:
        return False
    if total_cents < int(event.installment_min_cents or 0):
        return False
    if event.installment_mode == event.INSTALLMENT_UNTIL_EVENT:
        last_due = _last_due(event, start_date)
        # последний платёж должен быть строго в будущем (есть «коридор» под доли)
        if last_due is None or last_due <= today:
            return False
    return True


def _last_due(event, start_date):
    """Дедлайн последней доли для until_event: start − lead_days (или None)."""
    if not start_date:
        return None
    from datetime import timedelta

    return start_date - timedelta(days=int(event.installment_lead_days or 0))


def split_amounts(total_cents, count) -> list[int]:
    """Равный сплит суммы на count долей; остаток центов — на первые доли.

    Сумма результата == total_cents (front-load остатка: первая доля = «депозит»).
    """
    count = max(1, int(count))
    base, rem = divmod(int(total_cents), count)
    return [base + (1 if i < rem else 0) for i in range(count)]


def schedule_dates(event, today, start_date) -> list:
    """Список дат списаний (длина installment_count). Первая = сегодня.

    fixed — помесячно от сегодня; until_event — равномерно до start − lead_days.
    """
    from datetime import timedelta

    count = max(1, int(event.installment_count or 1))
    if count == 1:
        return [today]
    if event.installment_mode == event.INSTALLMENT_FIXED:
        return [today + relativedelta(months=i) for i in range(count)]
    # until_event: равномерно между сегодня и последним дедлайном (включительно).
    last_due = _last_due(event, start_date) or today
    span_days = (last_due - today).days
    return [today + timedelta(days=round(span_days * i / (count - 1))) for i in range(count)]


def build_schedule(event, total_cents, today, start_date) -> list[dict]:
    """График рассрочки: [{sequence, due_date, amount_cents}] (sequence с 1).

    Объединяет split_amounts + schedule_dates. Длина == installment_count.
    """
    count = max(1, int(event.installment_count or 1))
    amounts = split_amounts(total_cents, count)
    dates = schedule_dates(event, today, start_date)
    return [
        {"sequence": i + 1, "due_date": dates[i], "amount_cents": amounts[i]} for i in range(count)
    ]
