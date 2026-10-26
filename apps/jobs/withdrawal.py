"""KA-12 A-7 (E7.5 ⚖️): право отказа потребителя по смете, принятой онлайн.

Смета Handwerker'а, принятая на `/angebot/<token>/`, — договор на расстоянии: у
потребителя 14 дней на отказ (§ 312g, § 355 BGB). До принятия ему показывается
Widerrufsbelehrung; он может попросить начать работы раньше (§ 356 Abs. 4,
§ 357a Abs. 2 — тогда при отказе он оплачивает уже сделанное). После принятия
отказ заявляется кнопкой на той же странице (§ 356a), а подтверждение получения
приходит письмом.

Всё видимое клиенту — за флагом `QUOTE_WITHDRAWAL_ENABLED` (тексты и порядок —
после вычитки юриста). Фирме (`customer_type = company`) права отказа нет.
Отмена идёт общим путём `transactions.apply_action` — возврат депозита тот же,
что при отмене из кабинета; удержание за начатые работы (Wertersatz) владелец
решает вручную.
"""

import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import payment_methods

WITHDRAWAL_DAYS = 14

# ⚖️ Заготовка по образцу Anlage 1 zu Art. 246a § 1 EGBGB для Dienstleistungen /
# Werkverträge — на вычитку юриста. Бизнес может заменить своим `withdrawal_policy`.
SERVICE_TEXT = (
    "Widerrufsrecht\n\n"
    "Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag "
    "zu widerrufen. Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des "
    "Vertragsabschlusses.\n\n"
    "Um Ihr Widerrufsrecht auszuüben, müssen Sie uns ({name}, {address}, {email}) mittels "
    "einer eindeutigen Erklärung (z. B. ein mit der Post versandter Brief oder E-Mail) "
    "über Ihren Entschluss, diesen Vertrag zu widerrufen, informieren. Sie können dafür "
    "auch die Schaltfläche „Vertrag widerrufen“ auf dieser Seite verwenden. Zur Wahrung "
    "der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über die Ausübung des "
    "Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.\n\n"
    "Folgen des Widerrufs\n\n"
    "Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von "
    "Ihnen erhalten haben, unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag "
    "zurückzuzahlen, an dem die Mitteilung über Ihren Widerruf bei uns eingegangen ist. "
    "Für diese Rückzahlung verwenden wir dasselbe Zahlungsmittel, das Sie bei der "
    "ursprünglichen Transaktion eingesetzt haben.\n\n"
    "Haben Sie verlangt, dass die Dienstleistungen während der Widerrufsfrist beginnen "
    "sollen, so haben Sie uns einen angemessenen Betrag zu zahlen, der dem Anteil der bis "
    "zu dem Zeitpunkt, zu dem Sie uns von der Ausübung des Widerrufsrechts hinsichtlich "
    "dieses Vertrags unterrichten, bereits erbrachten Dienstleistungen im Vergleich zum "
    "Gesamtumfang der im Vertrag vorgesehenen Dienstleistungen entspricht."
)


def enabled() -> bool:
    return bool(getattr(settings, "QUOTE_WITHDRAWAL_ENABLED", False))


def applies(job) -> bool:
    """Право отказа: флаг включён и покупатель — потребитель."""
    return enabled() and job.customer_type != payment_methods.COMPANY


def text_for(tenant) -> str:
    own = (getattr(tenant, "withdrawal_policy", "") or "").strip()
    if own:
        return own
    contact = getattr(tenant, "public_email", "") or getattr(tenant, "contact_email", "")
    address = ", ".join(
        b for b in [getattr(tenant, "address", ""), getattr(tenant, "city", "")] if b
    ).replace("\n", ", ")
    return SERVICE_TEXT.format(name=tenant.name, address=address or "—", email=contact or "—")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_info(job, tenant, *, early_start: bool) -> None:
    """Снимок при нажатии «Annehmen»: когда и какой текст показан, просил ли клиент
    начать раньше. Один раз — повторное нажатие (отказ Stripe, назад) не переписывает."""
    if not applies(job) or job.withdrawal_info_at is not None:
        return
    now = timezone.now()
    type(job).objects.filter(pk=job.pk, withdrawal_info_at__isnull=True).update(
        withdrawal_info_at=now,
        withdrawal_text_hash=text_hash(text_for(tenant)),
        early_start_requested_at=now if early_start else None,
    )
    job.refresh_from_db(
        fields=["withdrawal_info_at", "withdrawal_text_hash", "early_start_requested_at"]
    )


def deadline(job):
    """Последний момент отказа (None — отказ невозможен: не принято онлайн)."""
    if job.accepted_at is None or job.withdrawal_info_at is None:
        return None
    return job.accepted_at + timezone.timedelta(days=WITHDRAWAL_DAYS)


def can_withdraw(job, now=None) -> bool:
    """Кнопка отказа: потребитель, принял онлайн, работа не завершена, срок не вышел."""
    if not applies(job) or job.withdrawn_at is not None:
        return False
    if job.status != job.STATUS_ACCEPTED:
        return False
    end = deadline(job)
    return end is not None and (now or timezone.now()) <= end


class WithdrawalError(Exception):
    pass


def withdraw(job, tenant) -> bool:
    """Заявить отказ: отметка + отмена заявки общим путём (возврат депозита).

    → True, если отказ принят сейчас; False — уже был (повтор безопасен).
    WithdrawalError — отказ невозможен (срок вышел, работа завершена)."""
    from apps.core import transactions

    from .models import Job

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.withdrawn_at is not None:
            return False
        if not can_withdraw(locked):
            raise WithdrawalError(_("Der Widerruf ist für diesen Auftrag nicht mehr möglich."))
        locked.withdrawn_at = timezone.now()
        locked.save(update_fields=["withdrawn_at", "updated_at"])
        transactions.apply_action(
            "job", locked, Job.STATUS_CANCELLED, actor=None, extra={"refund": "1"}, tenant=tenant
        )
    job.refresh_from_db()
    transaction.on_commit(lambda: _notify(job))
    return True


def _notify(job) -> None:
    from .notifications import enqueue_job_email

    enqueue_job_email(job, "withdrawn")  # клиенту — подтверждение получения (§ 356a)
    enqueue_job_email(job, "withdrawn_owner")
