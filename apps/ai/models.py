"""AI-0b: учёт вызовов ИИ — одна строка на запрос к провайдеру.

Только числа и коды: НИ текста запроса/ответа, ни их хешей, ни пользователя, ни IP.
SHARED (public): дневной бюджет платформы и сводка суперпользователя — одной таблицей."""

from django.db import models


class AIUsage(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    day = models.DateField()
    tenant_schema = models.CharField(max_length=63, blank=True, default="")  # "" = платформа
    task = models.CharField(max_length=40)
    route = models.CharField(max_length=20)
    model = models.CharField(max_length=100, blank=True, default="")
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    images = models.PositiveSmallIntegerField(default=0)
    # Центы с дробью: мелкие вызовы стоят доли цента, целые центы обнулили бы бюджет.
    cost_cents = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    ok = models.BooleanField(default=True)
    error_code = models.CharField(max_length=30, blank=True, default="")
    fallback_used = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "KI-Nutzung"
        verbose_name_plural = "KI-Nutzung"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["day", "tenant_schema"], name="ai_usage_day_tenant"),
        ]

    def __str__(self):
        return f"{self.day} {self.tenant_schema or 'platform'} {self.task} {self.route}"
