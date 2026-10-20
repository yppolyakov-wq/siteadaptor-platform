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
            # Индекс этого ограничения обслуживает и поиск по tg_user_id (префикс).
            models.UniqueConstraint(
                fields=["tg_user_id", "tenant"], name="platform_bot_link_user_tenant"
            ),
            # У бизнеса один владелец-чат общего бота — на уровне БД, не только кода.
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_active=True),
                name="platform_bot_one_active_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.tg_user_id} → {self.tenant_id}"


class OwnerBotPrefs(TimestampedModel):
    """T-8.10h H-7i: права субъекта данных в общем боте (Art. 16/18/21 DSGVO).

    Одна строка на пользователя Telegram; пишет её только `platform_bot/rights.py`.
    Флаг блокировки бота (`OwnerTelegramLink.blocked_at`) сюда НЕ годится: его снимает
    каждое сообщение пользователя, а ограничение обработки должно переживать сообщения.
    """

    tg_user_id = models.BigIntegerField(unique=True)
    # Язык ответов бота (Art. 16 — «исправить»); пусто = язык клиента Telegram.
    locale = models.CharField(max_length=8, blank=True)
    # Art. 18: сообщения не обрабатываются, доставка через общий бот молчит.
    restricted_at = models.DateTimeField(null=True, blank=True)
    # Art. 21: возражение против ИИ-разбора фото и против напоминаний.
    ai_objected_at = models.DateTimeField(null=True, blank=True)
    reminders_objected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Telegram-Einstellung (DSGVO)"
        verbose_name_plural = "Telegram-Einstellungen (DSGVO)"

    def __str__(self):
        return str(self.tg_user_id)
