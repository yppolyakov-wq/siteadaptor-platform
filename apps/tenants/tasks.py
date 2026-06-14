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
    send_mail(
        subject=f"Ihre Website ist bereit — {tenant.name}",
        message=(
            f"Hallo,\n\n"
            f"Ihre Website für „{tenant.name}“ ist fertig eingerichtet!\n\n"
            f"Hier anmelden: {login_url}\n"
            f"Benutzername: {email}\n\n"
            f"Viel Erfolg!\nIhr siteadaptor-Team"
        ),
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
