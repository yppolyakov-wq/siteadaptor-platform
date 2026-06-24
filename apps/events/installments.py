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


def first_installment_cents(event, total_cents, today=None) -> int:
    """Сумма первой доли (для Checkout первого платежа, R10b); 0 если не применимо."""
    from django.utils import timezone

    today = today or timezone.localdate()
    if not installments_available(event, total_cents, today, event.starts_at.date()):
        return 0
    return split_amounts(total_cents, int(event.installment_count or 1))[0]


def create_plan(ticket, *, payment_intent="", customer_id="", payment_method_id="", today=None):
    """R10b: создать план рассрочки для билета (идемпотентно). Первая доля = оплачена.

    Строит график по конфигу события и `ticket.payable_cents`, создаёт
    `InstallmentPlan` + `InstallmentCharge`-ы, помечает 1-ю долю paid (с её
    payment_intent), сохраняет мандат. Ставит `ticket.payment_state=installment`.
    Повторный вызов вернёт существующий план (вебхук-дедуп)."""
    from django.utils import timezone

    from .models import InstallmentCharge, InstallmentPlan, Ticket

    existing = InstallmentPlan.objects.filter(ticket=ticket).first()
    if existing is not None:
        return existing

    today = today or timezone.localdate()
    total = ticket.payable_cents
    schedule = build_schedule(ticket.event, total, today, ticket.event.starts_at.date())
    plan = InstallmentPlan.objects.create(
        ticket=ticket,
        total_cents=total,
        count=len(schedule),
        status=InstallmentPlan.STATUS_ACTIVE,
        stripe_customer_id=customer_id,
        stripe_payment_method_id=payment_method_id,
    )
    for i, row in enumerate(schedule):
        first = i == 0
        InstallmentCharge.objects.create(
            plan=plan,
            sequence=row["sequence"],
            due_date=row["due_date"],
            amount_cents=row["amount_cents"],
            status=InstallmentCharge.STATUS_PAID if first else InstallmentCharge.STATUS_SCHEDULED,
            stripe_payment_intent=payment_intent if first else "",
        )
    ticket.payment_state = Ticket.PAYMENT_INSTALLMENT
    if payment_intent and not ticket.stripe_payment_intent:
        ticket.stripe_payment_intent = payment_intent
    ticket.save(update_fields=["payment_state", "stripe_payment_intent", "updated_at"])
    # Первая доля оплачена → место за гостем (авто-подтверждение, если не ручное).
    if not ticket.event.require_manual_confirm and ticket.status == Ticket.STATUS_PENDING:
        from apps.core.fsm import IllegalTransition

        from .state_machine import TicketSM

        try:
            TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
        except IllegalTransition:
            pass
    return plan


def mark_charge_paid(charge, payment_intent=""):
    """R10c: отметить долю оплаченной; при полной оплате — завершить план + билет.

    Возвращает True, если план полностью оплачен (completed)."""
    from .models import InstallmentCharge, InstallmentPlan, Ticket

    charge.status = InstallmentCharge.STATUS_PAID
    charge.last_error = ""
    if payment_intent:
        charge.stripe_payment_intent = payment_intent
    charge.save(update_fields=["status", "last_error", "stripe_payment_intent", "updated_at"])
    plan = charge.plan
    if plan.charges.exclude(status=InstallmentCharge.STATUS_PAID).exists():
        return False
    plan.status = InstallmentPlan.STATUS_COMPLETED
    plan.save(update_fields=["status", "updated_at"])
    ticket = plan.ticket
    if ticket.payment_state != Ticket.PAYMENT_PAID:
        ticket.payment_state = Ticket.PAYMENT_PAID
        ticket.save(update_fields=["payment_state", "updated_at"])
    return True
