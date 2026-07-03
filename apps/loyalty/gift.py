"""Подарочные сертификаты (G1): покупка онлайн → выпуск Voucher → доставка кода.

Покупка создаёт GiftVoucher(pending) и ведёт на Stripe Connect Checkout (деньги
бизнесу). Вебхук (apps.billing.webhooks, kind="gift_voucher") после оплаты вызывает
`mark_gift_voucher_paid` кросс-схемно: выпускает `Voucher` (фикс-сумма, 1 использование)
и ставит письмо с кодом. Погашение — как обычный промокод (H4a, поле в брони).
"""

import secrets
import string

from django.db import transaction

from .models import GiftVoucher, Voucher

_ALPHABET = string.ascii_uppercase + string.digits
MIN_CENTS = 1000  # 10 €
MAX_CENTS = 200000  # 2000 €


def _unique_code() -> str:
    for _ in range(10):
        code = "GS-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Voucher.objects.filter(code=code).exists():
            return code
    raise RuntimeError("could not generate unique gift voucher code")


def create_gift_voucher(*, buyer_name, buyer_email, amount_cents, recipient_name="", message=""):
    """GiftVoucher(pending). Бросает ValueError при сумме вне [MIN, MAX] или без имени/почты."""
    amount_cents = int(amount_cents or 0)
    if not buyer_name.strip() or not buyer_email.strip():
        raise ValueError("buyer name and email required")
    if not (MIN_CENTS <= amount_cents <= MAX_CENTS):
        raise ValueError("amount out of range")
    return GiftVoucher.objects.create(
        buyer_name=buyer_name.strip()[:120],
        buyer_email=buyer_email.strip()[:254],
        recipient_name=recipient_name.strip()[:120],
        message=message.strip()[:300],
        amount_cents=amount_cents,
    )


@transaction.atomic
def mark_gift_voucher_paid(*, tenant_schema, gift_id, payment_intent="") -> bool:
    """Вебхук: сертификат оплачен → выпустить Voucher + письмо. Кросс-схемно,
    идемпотентно (повторный вызов не выпускает второй код)."""
    from django_tenants.utils import schema_context

    if not tenant_schema or not gift_id:
        return False
    with schema_context(tenant_schema):
        gift = GiftVoucher.objects.select_for_update().filter(id=gift_id).first()
        if gift is None:
            return False
        fields = []
        if gift.payment_state != GiftVoucher.PAYMENT_PAID:
            gift.payment_state = GiftVoucher.PAYMENT_PAID
            fields.append("payment_state")
        if payment_intent and gift.stripe_payment_intent != payment_intent:
            gift.stripe_payment_intent = payment_intent
            fields.append("stripe_payment_intent")
        if gift.voucher_id is None:  # выпускаем код один раз
            voucher = Voucher.objects.create(
                code=_unique_code(),
                label=f"Geschenkgutschein {gift.amount_eur:.0f} €"[:120],
                discount_cents=gift.amount_cents,  # номинал (дисплей)
                # B1.5 (владелец «а»): Wertgutschein с остатком — частичное
                # погашение до исчерпания, max_uses=0 (лимит — сам остаток).
                balance_cents=gift.amount_cents,
                max_uses=0,
            )
            gift.voucher = voucher
            fields.append("voucher")
        if fields:
            fields.append("updated_at")
            gift.save(update_fields=fields)
        _enqueue_gift_email(gift)
    return True


def _enqueue_gift_email(gift):
    """Письмо покупателю с кодом сертификата (idempotent — БД-дедуп)."""
    if not gift.buyer_email or gift.voucher is None:
        return
    from django.template.loader import render_to_string

    from apps.notifications.services import notify

    ctx = {"gift": gift, "code": gift.voucher.code}
    try:
        body = render_to_string("emails/gift_voucher.txt", ctx)
    except Exception:  # noqa: BLE001 — без шаблона не роняем выпуск
        body = f"Ihr Gutscheincode: {gift.voucher.code} ({gift.amount_eur:.0f} €)"
    notify(
        dedupe_key=f"gift:{gift.id}:issued",
        type="gift_voucher",
        recipient=gift.buyer_email,
        subject="Ihr Geschenkgutschein",
        body=body,
    )
