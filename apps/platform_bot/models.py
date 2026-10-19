"""T-8.10h: привязка «пользователь Telegram → бизнес» для общего бота платформы.

SHARED (public-схема): вебхук общего бота приходит без тенанта, и бизнес находится по
этой таблице. Храним только числовой id Telegram и связь — без имени и username (DSGVO).
"""

from django.db import models

from apps.core.models import TimestampedModel


class OwnerTelegramLink(TimestampedModel):
    VIA_SIGNUP = "signup"
    VIA_CABINET = "cabinet"
    VIA_CHOICES = [(VIA_SIGNUP, "Registrierung im Bot"), (VIA_CABINET, "Kabinett")]

    # У личного чата chat.id == user.id; id Telegram больше 2³¹ — BigInteger.
    tg_user_id = models.BigIntegerField()
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="owner_tg_links"
    )
    is_active = models.BooleanField(default=True)
    via = models.CharField(max_length=16, choices=VIA_CHOICES, default=VIA_CABINET)
    # Текущий бизнес владельца нескольких бизнесов = последний выбранный.
    selected_at = models.DateTimeField(null=True, blank=True)
    # Пользователь заблокировал бот (my_chat_member) — доставка через общий бот прекращается.
    blocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Telegram-Verknüpfung"
        verbose_name_plural = "Telegram-Verknüpfungen"
        constraints = [
            models.UniqueConstraint(
                fields=["tg_user_id", "tenant"], name="platform_bot_link_user_tenant"
            )
        ]
        indexes = [
            models.Index(fields=["tg_user_id", "is_active"], name="platform_bot_link_user_idx")
        ]

    def __str__(self):
        return f"{self.tg_user_id} → {self.tenant_id}"
