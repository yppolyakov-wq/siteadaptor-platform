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
