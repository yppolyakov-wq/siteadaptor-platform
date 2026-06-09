"""Локальный агрегатор (SHARED): материализованные активные акции для городских
страниц на основном домене.

Акции живут в TENANT-схемах; здесь — денормализованный снимок в public-схеме
(см. tasks.sync_listing), чтобы выдавать предложения по городу/типу бизнеса без
кросс-схемных запросов. Phase 2 расширит до мульти-доменных порталов
(AggregatorPortal).
"""

from django.db import models


class AggregatorListing(models.Model):
    # --- источник (тенант + акция) ---
    tenant_schema = models.CharField(max_length=63)
    tenant_slug = models.SlugField(max_length=100)
    business_name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100, blank=True)
    promo_uuid = models.UUIDField()

    # --- денормализованная карточка ---
    title = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    teaser = models.JSONField(default=dict)
    image = models.JSONField(default=dict, blank=True)  # FileRef-envelope
    currency = models.CharField(max_length=3, default="EUR")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    detail_url = models.URLField()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_schema", "promo_uuid"], name="agg_listing_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["city", "is_active"], name="agg_city_active_idx"),
            models.Index(fields=["business_type", "city"], name="agg_btype_city_idx"),
        ]

    def __str__(self):
        return f"{self.business_name}: {(self.title or {}).get('de') or self.promo_uuid}"
