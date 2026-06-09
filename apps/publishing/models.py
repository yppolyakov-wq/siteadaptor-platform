"""Каналы публикации и публикации акций (TENANT-схема).

Channel — настраиваемый канал бизнеса (тип задаёт адаптер; config — параметры).
Publication — факт публикации акции в канал (статус через PublicationSM). Сейчас
встроен только адаптер `log` (внутренний); внешние (Instagram/GBP) — Phase 2.
"""

from django.db import models

from apps.core.models import TimestampedModel


class Channel(TimestampedModel):
    LOG = "log"
    GOOGLE_BUSINESS = "google_business"
    CHANNEL_TYPES = [
        (LOG, "Log (internal)"),
        # Track B1: Google Posts; настройка — docs/gbp-setup.md
        (GOOGLE_BUSINESS, "Google Business Profile"),
    ]

    type = models.CharField(max_length=30, choices=CHANNEL_TYPES, default=LOG)
    name = models.CharField(max_length=100, blank=True)
    is_enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["type"], name="channel_type_uniq"),
        ]

    def __str__(self):
        return self.name or self.get_type_display()


class Publication(TimestampedModel):
    promotion = models.ForeignKey(
        "promotions.Promotion", on_delete=models.CASCADE, related_name="publications"
    )
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="publications")

    status = models.CharField(max_length=20, default="queued", db_index=True)
    external_ref = models.CharField(max_length=200, blank=True)
    # dedupe_key=publish:{promo}:{channel} — гарантия отсутствия дублей публикаций.
    dedupe_key = models.CharField(max_length=200, unique=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "channel"], name="publication_promo_channel_uniq"
            ),
        ]

    def __str__(self):
        return f"{self.promotion_id}→{self.channel_id}: {self.status}"
