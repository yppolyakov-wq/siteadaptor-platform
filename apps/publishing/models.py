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
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    PINTEREST = "pinterest"
    CHANNEL_TYPES = [
        (LOG, "Log (internal)"),
        # Track B1: Google Posts; настройка — docs/gbp-setup.md
        (GOOGLE_BUSINESS, "Google Business Profile"),
        # M23a: соц-постинг (Meta Graph API); настройка — docs/meta-social-setup.md
        (FACEBOOK, "Facebook"),
        (INSTAGRAM, "Instagram"),
        # M23 доп.каналы: постинг в Telegram-канал бизнеса и Pinterest
        (TELEGRAM, "Telegram"),
        (PINTEREST, "Pinterest"),
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


class SocialPost(TimestampedModel):
    """CM-2: собственный пост контент-календаря — ЧТО постим (текст/фото/ссылка)
    и КОГДА (`scheduled_at`; NULL у черновика). Доставка в каналы — прежняя
    механика `Publication` (FSM/dedupe/adapters), по одной на включённый канал.
    `source_kind`/`source_id` — шов CM-3 (авто-посты из сущностей платформы:
    blog/event/product), пока пустые. Статусы — SocialPostSM (draft/scheduled/
    sent); доставка per-канал отслеживается на Publication, не здесь."""

    DRAFT, SCHEDULED, SENT = "draft", "scheduled", "sent"

    text = models.TextField()
    # Фото поста (FileRef-конверт {url,…}, как у товара/акции); пусто = текстовый пост.
    image = models.JSONField(default=dict, blank=True)
    link_url = models.URLField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default=DRAFT, db_index=True)
    source_kind = models.CharField(max_length=20, blank=True)
    source_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"], name="socialpost_due_idx")]

    def __str__(self):
        return (
            f"{self.text[:40]}… [{self.status}]"
            if len(self.text) > 40
            else f"{self.text} [{self.status}]"
        )

    @property
    def image_url(self) -> str:
        return self.image.get("url", "") if isinstance(self.image, dict) else ""


class Publication(TimestampedModel):
    # CM-2: источник — акция ИЛИ собственный пост (ровно один, CheckConstraint).
    promotion = models.ForeignKey(
        "promotions.Promotion",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="publications",
    )
    post = models.ForeignKey(
        SocialPost,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="publications",
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
            # CM-2: у поста — тоже не более одной публикации на канал.
            models.UniqueConstraint(
                fields=["post", "channel"],
                condition=models.Q(post__isnull=False),
                name="publication_post_channel_uniq",
            ),
            # Ровно один источник: акция XOR пост.
            models.CheckConstraint(
                condition=(
                    models.Q(promotion__isnull=False, post__isnull=True)
                    | models.Q(promotion__isnull=True, post__isnull=False)
                ),
                name="publication_source_xor",
            ),
        ]

    def __str__(self):
        src = self.promotion_id or self.post_id
        return f"{src}→{self.channel_id}: {self.status}"
