"""Локальный агрегатор (SHARED): материализованные активные акции для городских
страниц на основном домене.

Акции живут в TENANT-схемах; здесь — денормализованный снимок в public-схеме
(см. tasks.sync_listing), чтобы выдавать предложения по городу/типу бизнеса без
кросс-схемных запросов. Phase 2 расширит до мульти-доменных порталов
(AggregatorPortal).
"""

from django.db import models

from apps.core.models import I18nMixin
from apps.tenants.models import Tenant


class AggregatorListing(I18nMixin, models.Model):
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

    is_surprise = models.BooleanField(default=False)  # Überraschungstüte (Track B2)
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

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def teaser_text(self) -> str:
        return self.get_i18n("teaser")


class AggregatorPortal(I18nMixin, models.Model):
    """Брендированный мульти-доменный портал над пулом AggregatorListing (P2.1).

    Привязан к своему хосту (поддомен *.siteadaptor.de или custom-домен) и сужает
    выдачу по городу и/или типу бизнеса. Резолвер (apps.aggregator.middleware)
    сопоставляет request.get_host() → портал: кладёт его в request.portal и
    подменяет request.urlconf на config.urls_portal (страницы — portal_views).
    SHARED (public-схема), как и листинги.
    """

    KIND_CITY = "city"
    KIND_VERTICAL = "vertical"
    KIND_COMBO = "combo"
    KINDS = [
        (KIND_CITY, "City"),
        (KIND_VERTICAL, "Vertical"),
        (KIND_COMBO, "City + type"),
    ]

    host = models.CharField(max_length=253, unique=True)  # полный хост — ключ резолвера
    kind = models.CharField(max_length=20, choices=KINDS, default=KIND_CITY)

    # Фильтры выдачи. Любой может быть пустым (тогда портал шире по этой оси).
    city = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=50, blank=True, choices=Tenant.BUSINESS_TYPES)

    # Брендинг (i18n-JSON {"de": "...", "en": "..."}).
    title = models.JSONField(default=dict)
    tagline = models.JSONField(default=dict, blank=True)
    intro = models.JSONField(default=dict, blank=True)
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default="#111827")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["host"]
        indexes = [
            models.Index(fields=["is_active"], name="agg_portal_active_idx"),
        ]

    def __str__(self):
        scope = self.city or (self.get_business_type_display() if self.business_type else "") or "—"
        return f"{self.host} ({scope})"

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def tagline_text(self) -> str:
        return self.get_i18n("tagline")

    @property
    def intro_text(self) -> str:
        return self.get_i18n("intro")
