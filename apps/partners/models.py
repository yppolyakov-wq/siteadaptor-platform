"""D3: партнёрка веб-студий/фрилансеров (SHARED, public-схема).

Партнёр ведёт много тенантов-клиентов: реф-код атрибуцирует онбординг
(Tenant.partner), кабинет /partner/ — read-only список (v1). Учётка —
public-`auth_user` (allauth на основном домене): auth per-схемный, поэтому
owner-аккаунты клиентов не пересекаются с партнёрскими. Вознаграждение —
per-partner (решение владельца «несколько вариантов»): скидка клиенту
Stripe-купоном ИЛИ ревшара (сводка, выплата вне Stripe). Вход в кабинеты
клиентов — этап 2 (D3.5, отдельный план).
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel


class Partner(TimestampedModel):
    REWARD_NONE = ""
    REWARD_CLIENT_DISCOUNT = "client_discount"
    REWARD_REVSHARE = "revshare"
    REWARDS = [
        (REWARD_NONE, "—"),
        (REWARD_CLIENT_DISCOUNT, "Rabatt für Kunden (Stripe-Coupon)"),
        (REWARD_REVSHARE, "Revenue-Share (Auszahlung manuell)"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_profile"
    )
    name = models.CharField(max_length=200)
    # Реф-код в ссылке ?ref=<code> на странице регистрации бизнеса.
    code = models.SlugField(max_length=40, unique=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    reward_kind = models.CharField(max_length=20, choices=REWARDS, default="", blank=True)
    # client_discount: сам купон живёт в Stripe (id сюда), percent — справочно.
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    stripe_coupon_id = models.CharField(max_length=100, blank=True, default="")
    revshare_percent = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"
