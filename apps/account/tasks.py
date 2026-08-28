"""Celery-задачи ЛК клиента (CA1): письмо magic-link."""

from apps.core.jobs import idempotent_task


@idempotent_task()
def send_customer_magic_link(*, email, url, business_name=""):
    """Письмо со ссылкой входа в ЛК бизнеса. dedupe_key — хэш токена (в .delay)."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale

    with translation.override(email_locale()):  # I18N-13: локаль получателя
        shop = business_name or _("Ihrem Shop")
        subject = (_("Ihr Anmelde-Link – %(shop)s") % {"shop": business_name}).strip(" –")
        message = _(
            "Guten Tag,\n\n"
            "mit diesem Link melden Sie sich bei %(shop)s an: %(url)s\n\n"
            "Der Link ist 15 Minuten gültig und kann nur einmal verwendet werden.\n"
            "Falls Sie keine Anmeldung angefordert haben, ignorieren Sie diese E-Mail."
        ) % {"shop": shop, "url": url}
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return {"sent": email}
