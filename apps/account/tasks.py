"""Celery-задачи ЛК клиента (CA1): письмо magic-link."""

from apps.core.jobs import idempotent_task


@idempotent_task()
def send_customer_magic_link(*, email, url, business_name=""):
    """Письмо со ссылкой входа в ЛК бизнеса. dedupe_key — хэш токена (в .delay)."""
    from django.conf import settings
    from django.core.mail import send_mail

    shop = business_name or "Ihrem Shop"
    send_mail(
        subject=f"Ihr Anmelde-Link – {business_name}".strip(" –"),
        message=(
            "Guten Tag,\n\n"
            f"mit diesem Link melden Sie sich bei {shop} an: {url}\n\n"
            "Der Link ist 15 Minuten gültig und kann nur einmal verwendet werden.\n"
            "Falls Sie keine Anmeldung angefordert haben, ignorieren Sie diese E-Mail."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return {"sent": email}
