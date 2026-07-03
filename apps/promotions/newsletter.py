"""G3: рассылки гостям с Double-Opt-In (UWG §7).

Согласие подтверждается по подписанной ссылке (DOI) → marketing_opt_in=True +
отметка времени (доказательство). Кампания уходит только подтвердившим и не
отписавшимся, через notifications (idempotent по кампании+клиенту), с one-click
отпиской в каждом письме (RFC 8058).
"""

from django.core import signing
from django.urls import reverse
from django.utils import timezone

from apps.notifications.services import notify

from .models import Customer, NewsletterCampaign

_DOI_SALT = "newsletter-doi"


def doi_token(customer) -> str:
    return signing.dumps(str(customer.pk), salt=_DOI_SALT)


def load_doi_token(token: str):
    """Customer по DOI-токену (или None при плохой подписи/отсутствии)."""
    try:
        pk = signing.loads(token, salt=_DOI_SALT, max_age=60 * 60 * 24 * 14)  # 14 дней
    except signing.BadSignature:
        return None
    return Customer.objects.filter(pk=pk).first()


def confirm_opt_in(customer) -> bool:
    """Подтвердить согласие (DOI). True — если статус изменился."""
    if customer.marketing_opt_in and not customer.unsubscribed:
        return False
    customer.marketing_opt_in = True
    customer.marketing_opt_in_at = timezone.now()
    customer.unsubscribed = False  # повторная подписка снимает прежнюю отписку
    customer.save(
        update_fields=["marketing_opt_in", "marketing_opt_in_at", "unsubscribed", "updated_at"]
    )
    return True


def consented_customers():
    """Получатели рассылки: подтвердившие opt-in, не отписавшиеся, с e-mail."""
    return Customer.objects.filter(marketing_opt_in=True, unsubscribed=False).exclude(email="")


def segment_customers(*, tag="", inactive_days=None, top_ltv=None):
    """B4/CM-9: сегмент ПОВЕРХ consented_customers() (UWG-гейт по построению).

    Фильтры комбинируются AND; всё пустое = вся opt-in-база.
    - tag: точное совпадение тега (теги хранятся lower-case);
    - inactive_days: последняя покупка (Max по RevenueEntry) старше N дней —
      клиенты БЕЗ покупок отсекаются (win-back целит бывших покупателей);
    - top_ltv: топ-N по сумме выручки (слайс — последним, дальше не фильтровать).
    """
    from datetime import timedelta

    from django.db.models import Max, Sum

    qs = consented_customers()
    if tag:
        qs = qs.filter(tags__contains=[tag.strip().lower()])
    if inactive_days:
        cutoff = timezone.localdate() - timedelta(days=int(inactive_days))
        qs = qs.annotate(_last_purchase=Max("revenue_entries__date")).filter(
            _last_purchase__lt=cutoff
        )
    if top_ltv:
        qs = qs.annotate(_ltv=Sum("revenue_entries__amount")).filter(_ltv__gt=0)
        qs = qs.order_by("-_ltv")[: int(top_ltv)]
    return qs


def send_doi_email(customer, *, base_url: str) -> None:
    """Письмо Double-Opt-In со ссылкой подтверждения (UWG §7)."""
    link = f"{base_url}{reverse('storefront-newsletter-confirm', args=[doi_token(customer)])}"
    body = (
        "Bitte bestätigen Sie Ihre Anmeldung zum Newsletter:\n\n"
        f"{link}\n\n"
        "Wenn Sie sich nicht angemeldet haben, ignorieren Sie diese E-Mail."
    )
    notify(
        dedupe_key=f"doi:{customer.id}:{timezone.localdate().isoformat()}",
        type="newsletter_doi",
        recipient=customer.email,
        subject="Bitte bestätigen Sie Ihre Newsletter-Anmeldung",
        body=body,
    )


def _coupon_terms(campaign) -> str:
    """Строка условий кода для письма («−10 % · gültig bis …»)."""
    parts = []
    if campaign.discount_percent:
        parts.append(f"−{campaign.discount_percent} %")
    elif campaign.discount_cents:
        parts.append(f"−{campaign.discount_cents / 100:.2f} €".replace(".", ","))
    if campaign.min_order_cents:
        parts.append(f"ab {campaign.min_order_cents / 100:.2f} € Bestellwert".replace(".", ","))
    if campaign.valid_days:
        parts.append(f"gültig {campaign.valid_days} Tage")
    return " · ".join(parts)


def send_coupon_campaign(campaign, *, base_url: str, customers=None) -> int:
    """B4/CM-9: разослать персональные коды сегменту. Идемпотентно: повторный
    вызов не дублирует ни коды (get-or-create по campaign+customer), ни письма
    (dedupe_key). customers — переопределение сегмента (beat передаёт свой
    отфильтрованный список); по умолчанию segment_customers() из полей кампании.
    Возвращает число адресатов."""
    from datetime import timedelta

    from apps.promotions.services import generate_vouchers

    if campaign.kind == campaign.KIND_MANUAL and campaign.status == campaign.STATUS_SENT:
        return campaign.recipient_count
    if customers is None:
        customers = segment_customers(
            tag=campaign.tag,
            inactive_days=campaign.inactive_days,
            top_ltv=campaign.top_ltv,
        )
    count = 0
    for customer in customers:
        # Реюз кода — только у ручной кампании (идемпотентность одной отправки);
        # auto-winback выдаёт новый код каждое окно (дедуп окна — в beat-задаче).
        voucher = None
        if campaign.kind == campaign.KIND_MANUAL:
            voucher = campaign.vouchers.filter(customer=customer).order_by("-created_at").first()
        if voucher is None:
            voucher = generate_vouchers(
                label=campaign.name,
                count=1,
                max_uses=1,
                expires_at=timezone.now() + timedelta(days=campaign.valid_days or 30),
                customer=customer,
                discount_percent=campaign.discount_percent,
                discount_cents=campaign.discount_cents,
                min_order_cents=campaign.min_order_cents,
            )[0]
            voucher.campaign = campaign
            voucher.save(update_fields=["campaign", "updated_at"])
        unsub = f"{base_url}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
        terms = _coupon_terms(campaign)
        body_parts = [campaign.body.strip()] if campaign.body.strip() else []
        body_parts.append(f"Ihr persönlicher Code: {voucher.code}")
        if terms:
            body_parts.append(terms)
        body_parts.append(f"—\nAbmelden: {unsub}")
        notify(
            dedupe_key=f"coupon:{campaign.id}:{customer.id}:{voucher.code}",
            type="coupon_campaign",
            recipient=customer.email,
            subject=campaign.subject,
            body="\n\n".join(body_parts),
            headers={
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        count += 1
    if campaign.kind == campaign.KIND_MANUAL:
        campaign.status = campaign.STATUS_SENT
        campaign.sent_at = timezone.now()
        campaign.recipient_count = count
        campaign.save(update_fields=["status", "sent_at", "recipient_count", "updated_at"])
    else:
        campaign.recipient_count = (campaign.recipient_count or 0) + count
        campaign.sent_at = timezone.now()
        campaign.save(update_fields=["sent_at", "recipient_count", "updated_at"])
    return count


def send_campaign(campaign: NewsletterCampaign, *, base_url: str) -> int:
    """Разослать кампанию подтвердившим получателям. Идемпотентно: повторный вызов
    уже отправленной кампании — no-op. Возвращает число адресатов."""
    if campaign.status == NewsletterCampaign.STATUS_SENT:
        return campaign.recipient_count
    count = 0
    for customer in consented_customers():
        unsub = f"{base_url}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
        notify(
            dedupe_key=f"campaign:{campaign.id}:{customer.id}",
            type="newsletter_campaign",
            recipient=customer.email,
            subject=campaign.subject,
            body=f"{campaign.body}\n\n—\nAbmelden: {unsub}",
            headers={
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        count += 1
    campaign.status = NewsletterCampaign.STATUS_SENT
    campaign.sent_at = timezone.now()
    campaign.recipient_count = count
    campaign.save(update_fields=["status", "sent_at", "recipient_count", "updated_at"])
    return count
