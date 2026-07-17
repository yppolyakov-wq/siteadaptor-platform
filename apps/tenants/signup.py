"""AB5.1: double-opt-in регистрации бизнеса.

Флоу (план `docs/signup-confirm-wizard-plan-2026-07-17.md §1`): POST /registrieren/
→ SignupRequest (тенант НЕ создаётся) → письмо со ссылкой подтверждения →
GET /registrieren/bestaetigen/<token>/ → start_business_provisioning (прежний
фоновый провижининг). Письмо шлём синхронно `send_mail` — notify() тенант-скоупен,
а здесь public-схема без тенанта.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation

from .models import SignupRequest, Tenant


def confirmation_enabled() -> bool:
    return bool(getattr(settings, "SIGNUP_EMAIL_CONFIRMATION", True))


def show_direct_link() -> bool:
    """Console-бэкенд (dev или прод без Resend/SMTP): письмо никуда не уходит —
    показываем confirm-ссылку прямо на странице «проверьте почту», чтобы
    регистрация не брикалась. С реальным бэкендом ссылка не светится."""
    return "console" in getattr(settings, "EMAIL_BACKEND", "")


def create_request(*, cleaned_data, partner_code="", locale="de") -> SignupRequest:
    """Создать заявку: pending-дубли того же email заменяются (новый токен),
    просроченный мусор чистится оппортунистически (без beat-задачи)."""
    from django.contrib.auth.hashers import make_password

    stale = timezone.now() - SignupRequest.CONFIRM_TTL * 2
    SignupRequest.objects.filter(confirmed_at__isnull=True, created_at__lt=stale).delete()
    SignupRequest.objects.filter(confirmed_at__isnull=True, email=cleaned_data["email"]).delete()
    return SignupRequest.objects.create(
        email=cleaned_data["email"],
        password_hash=make_password(cleaned_data["password1"]),
        business_name=cleaned_data["business_name"],
        slug=cleaned_data["slug"],
        business_type=cleaned_data["business_type"],
        city=cleaned_data["city"],
        partner_code=partner_code,
        locale=locale or "de",
    )


def confirm_url(request, signup) -> str:
    """Абсолютная ссылка подтверждения — от public-хоста запроса."""
    return request.build_absolute_uri(reverse("business-signup-confirm", args=[signup.token]))


def send_confirmation_email(request, signup) -> None:
    """Письмо подтверждения на языке страницы регистрации в момент POST
    (L4-манера: немецкие msgid + translation.override; переводы — .po)."""
    with translation.override(signup.locale or "de"):
        ctx = {"signup": signup, "confirm_url": confirm_url(request, signup)}
        subject = " ".join(render_to_string("emails/signup_confirm_subject.txt", ctx).split())
        body = render_to_string("emails/signup_confirm.txt", ctx)
    send_mail(
        subject=subject,
        message=body,
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[signup.email],
        # Ошибка отправки не должна ронять регистрацию — на странице есть resend.
        fail_silently=True,
    )


def slug_taken(slug: str) -> bool:
    """Slug/schema могли занять между POST и подтверждением (заявка не резервирует)."""
    return (
        Tenant.objects.filter(slug=slug).exists()
        or Tenant.objects.filter(schema_name=slug.replace("-", "_")).exists()
    )
