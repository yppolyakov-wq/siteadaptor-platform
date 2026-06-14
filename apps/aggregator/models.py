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

    # Гео (G8c): denorm координат бизнеса из Tenant (для карты + «рядом»).
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    is_surprise = models.BooleanField(default=False)  # Überraschungstüte (Track B2)
    # Платное продвижение (P2.4a): до этого момента листинг закреплён сверху
    # выдачи с бейджем «Empfohlen». Срок ставит супер-админ (P2.4b добавит
    # самообслуживание через Stripe). sync_listing поле не трогает.
    featured_until = models.DateTimeField(null=True, blank=True, db_index=True)
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

    @property
    def is_featured_now(self) -> bool:
        from django.utils import timezone

        return bool(self.featured_until and self.featured_until > timezone.now())


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


class PortalBot(models.Model):
    """Telegram-бот портала агрегатора (TG4, SHARED/public).

    Один бот на портал; webhook на хосте портала /tg/<secret>/. На /start бот
    открывает выдачу портала как Telegram Mini App. Токен из @BotFather задаётся
    в unfold-админке (порталы — admin/команда-managed, кабинета у них нет).
    """

    portal = models.OneToOneField(
        AggregatorPortal, on_delete=models.CASCADE, related_name="telegram_bot"
    )
    token = models.CharField(max_length=100, blank=True)
    bot_username = models.CharField(max_length=64, blank=True)
    webhook_secret = models.CharField(max_length=48, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.portal.host}: {self.bot_username or 'bot'}"

    def save(self, *args, **kwargs):
        if not self.webhook_secret:
            import secrets

            self.webhook_secret = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class PortalUser(models.Model):
    """Клиентская идентичность на порталах (P2.3, SHARED/public).

    Конечный потребитель агрегатора — НЕ django.contrib.auth.User (те — владельцы
    бизнесов в tenant-схемах). Входит по magic-link (apps.aggregator.auth):
    пароля нет, переход по ссылке из письма = подтверждение email. Живёт в
    лёгкой сессии (request.session["portal_user_id"]). Cross-tenant: один
    аккаунт видит свои данные по всем бизнесам (брони подтянутся в P2.3c по
    email-связке с per-tenant Customer).
    """

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    # Центральная отписка от писем бизнесов (P2.3d): источник истины для
    # порталов; синхронизируется в per-tenant Customer.unsubscribed задачей
    # apply_marketing_opt_out. Транзакционные письма (бронь) идут всегда.
    marketing_opt_out = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class FavoriteListing(models.Model):
    """Избранное клиента портала (P2.3b, SHARED/public).

    CASCADE по листингу сознательно: листинг исчезает из агрегатора вместе с
    завершением акции — «сохранённое предложение» по природе временное.
    """

    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE, related_name="favorites")
    listing = models.ForeignKey(
        AggregatorListing, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "listing"], name="favorite_uniq"),
        ]

    def __str__(self):
        return f"{self.user.email} → {self.listing_id}"


class BusinessReview(models.Model):
    """Отзыв клиента портала о бизнесе (G8, SHARED/public).

    Привязан к бизнесу (tenant_schema), а не к отдельной акции — один автор
    (PortalUser) оставляет один отзыв на бизнес. Авто-публикация; супер-админ
    может скрыть (status=hidden, модерация). Агрегат — BusinessRating.
    """

    STATUS_PUBLISHED = "published"
    STATUS_HIDDEN = "hidden"
    STATUSES = [(STATUS_PUBLISHED, "Published"), (STATUS_HIDDEN, "Hidden")]

    tenant_schema = models.CharField(max_length=63)
    tenant_slug = models.SlugField(max_length=100)
    business_name = models.CharField(max_length=200, blank=True)  # снимок для админки
    author = models.ForeignKey(PortalUser, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()  # 1..5 (валидируется во вьюхе)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_PUBLISHED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["author", "tenant_schema"], name="review_author_business_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_schema", "status"], name="review_business_status_idx"),
        ]

    def __str__(self):
        return f"{self.business_name or self.tenant_slug}: {self.rating}★"

    @property
    def stars(self) -> str:
        return "★" * self.rating + "☆" * (5 - self.rating)


class BusinessRating(models.Model):
    """Денормализованный агрегат рейтинга бизнеса (G8) — быстрые звёзды в выдаче.

    Одна строка на tenant_schema; пересчитывается при создании/модерации отзыва
    (apps.aggregator.reviews.recompute_rating). Листинги джойнятся по схеме.
    """

    tenant_schema = models.CharField(max_length=63, unique=True)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)  # 0.00–5.00
    review_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant_schema}: {self.avg_rating} ({self.review_count})"
