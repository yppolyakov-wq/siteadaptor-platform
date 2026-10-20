from django.core.cache import cache

from apps.core.jobs import idempotent_task


def dedupe_key(update_id) -> str:
    return f"tgplat:{update_id}"


# T-8.10h: апдейт общего бота. Дедуп по update_id (Telegram повторяет доставку); сутки.
@idempotent_task(lock_timeout=86400)
def platform_bot_update(*, update):
    from . import handler

    try:
        return {"result": handler.handle(update)}
    except Exception:
        # Сбой обработки (БД, сеть) не должен на сутки «съесть» апдейт: повтор Celery или
        # Telegram обязан пройти мимо дедупа. Обработчики идемпотентны (bind/mark_*).
        cache.delete(f"job_lock:{dedupe_key(update.get('update_id'))}")
        raise


def enqueue_connected_email(link, payload: dict) -> None:
    """Письмо «Telegram verbunden» владельцу — страховка от утёкшей ссылки."""
    email = (payload.get("email") or "").strip() or (link.tenant.owner_email or "").strip()
    if not email:
        return
    stamp = int(link.selected_at.timestamp()) if link.selected_at else 0
    send_connected_email.delay(
        dedupe_key=f"tgplat-mail:{link.pk}:{stamp}",
        schema=link.tenant.schema_name,
        email=email,
        lang=payload.get("lang") or "",
    )


@idempotent_task(lock_timeout=86400)
def send_connected_email(*, schema, email, lang=""):
    from django.conf import settings
    from django.core.mail import send_mail
    from django.urls import reverse
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.core import owner_login
    from apps.telegram import bots
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(schema_name=schema).first()
    if tenant is None:
        return {"skipped": "no tenant"}
    bot = bots.platform_bot()
    username = f"@{bot.username}" if bot and bot.username else "Telegram"
    url = owner_login.tenant_url(tenant) + reverse(
        "notifications-settings", urlconf=owner_login.TENANT_URLCONF
    )
    langs = getattr(settings, "CABINET_LANGUAGES", ())
    locale = lang if lang in langs else (tenant.default_locale or "de")
    with translation.override(locale):
        subject = _("Telegram verbunden — %(name)s") % {"name": tenant.name}
        body = _(
            "Hallo,\n\nIhr Geschäft ist jetzt mit dem Telegram-Bot %(bot)s verbunden. "
            "Benachrichtigungen kommen ab jetzt dort an.\n\n"
            "Das waren nicht Sie? Trennen Sie die Verbindung hier:\n%(url)s"
        ) % {"bot": username, "url": url}
    send_mail(subject, body, None, [email], fail_silently=True)
    return {"sent": True}


@idempotent_task(lock_timeout=7 * 86400)
def notify_signup_bound(*, tenant_pk, uid, result, lang=""):
    """H-5b: почта подтверждена — сообщить в чат регистрации итог привязки."""
    from apps.tenants.models import Tenant

    from . import signup

    tenant = Tenant.objects.filter(pk=tenant_pk).first()
    if tenant is None:
        return {"skipped": "no tenant"}
    return {"result": signup.bound_message(tenant, int(uid), result, lang)}
