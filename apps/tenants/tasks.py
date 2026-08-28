"""Фоновый провижининг бизнеса (решение владельца 2026-06-12).

Создание PG-схемы гоняет миграции всех TENANT-приложений (~1 мин и растёт) —
поэтому регистрация отвечает мгновенно, а схему строит Celery. Пользователь
ждёт на странице tenants.views.signup_waiting (автообновление); по готовности
уходит письмо со ссылкой для входа (console-бэкенд до Resend-ключа).
Идемпотентно: повторный запуск для ready-тенанта — no-op, схема создаётся с
check_if_exists.
"""

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django_tenants.utils import tenant_context

from .models import Tenant


def _send_ready_email(tenant, email):
    from .services import login_url_for

    login_url = login_url_for(tenant)
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale

    with translation.override(email_locale()):  # I18N-13: локаль получателя
        subject = _("Ihre Website ist bereit — %(name)s") % {"name": tenant.name}
        message = _(
            "Hallo,\n\n"
            "Ihre Website für „%(name)s“ ist fertig eingerichtet!\n\n"
            "Hier anmelden: %(url)s\n"
            "Benutzername: %(email)s\n\n"
            "Viel Erfolg!\nIhr siteadaptor-Team"
        ) % {"name": tenant.name, "url": login_url, "email": email}
    send_mail(
        subject=subject,
        message=message,
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[email],
        fail_silently=True,  # письмо — бонус, не условие готовности
    )


def provision(tenant_id, email, password_hash) -> str:
    """Чистая логика: создать схему + владельца, проставить статус. → статус."""
    tenant = Tenant.objects.get(pk=tenant_id)
    if tenant.provisioning_status == Tenant.PROVISIONING_READY:
        return Tenant.PROVISIONING_READY  # идемпотентный повтор
    try:
        tenant.auto_create_schema = True
        tenant.create_schema(check_if_exists=True, verbosity=0)
        User = get_user_model()
        with tenant_context(tenant):
            if not User.objects.filter(username=email).exists():
                owner = User(username=email, email=email, password=password_hash)
                owner.save()
            # Роль владельца (M6-шов): идемпотентно, переживает повторный провижининг.
            from apps.core.models import Membership

            Membership.objects.get_or_create(
                user=User.objects.get(username=email),
                defaults={"role": Membership.ROLE_OWNER},
            )
        tenant.provisioning_status = Tenant.PROVISIONING_READY
        tenant.save(update_fields=["provisioning_status", "updated_at"])
    except Exception:
        tenant.provisioning_status = Tenant.PROVISIONING_FAILED
        tenant.save(update_fields=["provisioning_status", "updated_at"])
        raise
    _send_ready_email(tenant, email)
    return Tenant.PROVISIONING_READY


@shared_task
def provision_business(tenant_id, email, password_hash):
    return provision(tenant_id, email, password_hash)


@shared_task
def recheck_pending_custom_domains():
    """Авто-подтверждение кастомных доменов (beat): для каждой PENDING-заявки
    перепроверяем A-запись и активируем при совпадении — владельцу не нужно жать
    «Verify» вручную. CustomDomain — SHARED (public), один проход по всем тенантам.
    Возвращает число активированных доменов."""
    from . import domains
    from .models import CustomDomain

    activated = 0
    for custom in CustomDomain.objects.filter(status=CustomDomain.PENDING):
        if domains.verify(custom):
            activated += 1
    return activated


@shared_task
def refresh_google_ratings():
    """GK-11 (beat): обновить кэш Google-рейтингов. Tenant — SHARED (public),
    один проход без schema_context (прецедент recheck_pending_custom_domains).
    Берём тенантов с place_id и кэшем старше GOOGLE_RATING_REFRESH_DAYS;
    ошибка одного тенанта (сеть/квота/битый id) не роняет проход — кэш просто
    остаётся прежним. Возвращает число обновлённых."""
    from datetime import timedelta

    from django.conf import settings
    from django.db.models import Q
    from django.utils import timezone

    from . import google_places
    from .models import Tenant

    if not google_places.api_key():
        return 0  # ключ не настроен — фича молчит (external-integrations-backlog)

    stale_before = timezone.now() - timedelta(days=settings.GOOGLE_RATING_REFRESH_DAYS)
    tenants = (
        Tenant.objects.exclude(schema_name="public")
        .exclude(google_place_id="")
        .filter(
            Q(google_rating_updated_at__isnull=True) | Q(google_rating_updated_at__lt=stale_before)
        )
    )
    updated = 0
    for tenant in tenants:
        try:
            rating, count = google_places.fetch_rating(tenant.google_place_id)
        except Exception:
            continue  # держим прежний кэш; следующий проход попробует снова
        tenant.google_rating = rating
        tenant.google_rating_count = count
        tenant.google_rating_updated_at = timezone.now()
        tenant.save(
            update_fields=[
                "google_rating",
                "google_rating_count",
                "google_rating_updated_at",
                "updated_at",
            ]
        )
        updated += 1
    return updated
