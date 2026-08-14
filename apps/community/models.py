"""Пространство поездки: лента и чат группы одного заезда (MT-3, TENANT).

Заменяет практику «отдельная Telegram-группа на каждый тур»: объявления гида,
фото дня, файлы и вопросы участников живут у бизнеса, а не у мессенджера.
При этом Telegram остаётся — как канал доставки и (MT-3b) двусторонний мост.

Ключевые решения:
* **Пространство привязано к ЗАЕЗДУ** (`ref_kind="event"` + `ref_id`), потому что
  вместе едет группа конкретной даты. Привязка мягкая (паттерн inbox) — история
  переживает удаление события.
* **Лента и чат — одна модель** (`FeedPost.kind`): у них общий доступ, общая
  модерация и общий мост в Telegram; разница только в подаче.
* **Автор — либо сотрудник, либо участник, либо имя из Telegram.** Три поля, а не
  строка-роль: по FK строятся права («свой пост можно удалить»), а `author_name`
  нужен для сообщений из группы, где отправитель не привязывал бота.
* `source` + `external_ref` гасят эхо-петлю моста: пришедшее из Telegram обратно
  не пересылается, а повторный апдейт того же message_id не создаёт дубль.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class FeedSpace(TimestampedModel):
    """Группа поездки. Одно пространство на заезд."""

    ref_kind = models.CharField(max_length=20, default="event")
    ref_id = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=200, blank=True)
    # Закрытое пространство доступно на чтение, но новые записи не принимает
    # (гид закрывает его, когда поездка отжила своё).
    is_open = models.BooleanField(default=True)
    # Могут ли участники писать сами (иначе лента = только объявления гида).
    members_can_post = models.BooleanField(default=True)
    # MT-3b: привязанная Telegram-группа и код для команды /link в ней.
    tg_chat_id = models.CharField(max_length=40, blank=True)
    tg_link_code = models.CharField(max_length=20, blank=True, db_index=True)
    # Ссылка-приглашение для сопровождающих без билета (партнёр, механик).
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["ref_kind", "ref_id"], name="feedspace_ref_uniq"),
        ]

    def __str__(self):
        return self.title or f"{self.ref_kind}:{self.ref_id}"

    @property
    def tg_connected(self) -> bool:
        return bool(self.tg_chat_id)


class FeedPost(TimestampedModel):
    KIND_POST = "post"  # запись ленты (объявление, фото дня)
    KIND_MESSAGE = "message"  # реплика чата
    KINDS = [(KIND_POST, _("Beitrag")), (KIND_MESSAGE, _("Nachricht"))]

    SOURCE_WEB = "web"
    SOURCE_TELEGRAM = "telegram"
    SOURCES = [(SOURCE_WEB, "Web"), (SOURCE_TELEGRAM, "Telegram")]

    space = models.ForeignKey(FeedSpace, on_delete=models.CASCADE, related_name="posts")
    kind = models.CharField(max_length=10, choices=KINDS, default=KIND_POST)
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    author_customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="feed_posts"
    )
    # Имя отправителя из Telegram, если его не удалось сопоставить с клиентом.
    author_name = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    # Фото — обычные FileRef (публикуются внутри группы, не документы).
    images = models.JSONField(default=list, blank=True)
    # Шов под приватное вложение (досье MT-2). UI пока НЕТ намеренно: показывать
    # ссылку было бы нечестно — `can_access` пускает владельца и гида, а остальные
    # участники получили бы 404. Правило доступа «члены пространства видят файл,
    # приложенный гидом» — отдельное решение (v2), а не побочный эффект вёрстки.
    document = models.ForeignKey(
        "documents.SecureDocument", null=True, blank=True, on_delete=models.SET_NULL
    )
    source = models.CharField(max_length=10, choices=SOURCES, default=SOURCE_WEB)
    # message_id Telegram — идемпотентность входящих (повтор апдейта не дублирует).
    external_ref = models.CharField(max_length=64, blank=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["space", "kind", "created_at"], name="feedpost_space_kind_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["space", "external_ref"],
                condition=models.Q(external_ref__gt=""),
                name="feedpost_external_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.author_label}"

    @property
    def author_label(self) -> str:
        """Кем подписан пост: сотрудник → участник → имя из Telegram → «Gast»."""
        if self.author_user_id:
            user = self.author_user
            return (user.get_full_name() or user.username) if user else ""
        if self.author_customer_id and self.author_customer:
            return self.author_customer.name or self.author_customer.email
        return self.author_name or str(_("Gast"))

    @property
    def by_staff(self) -> bool:
        return bool(self.author_user_id)


class FeedComment(TimestampedModel):
    """Плоский комментарий к записи ленты (ответ гида выделяется по by_staff)."""

    post = models.ForeignKey(FeedPost, on_delete=models.CASCADE, related_name="comments")
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    author_customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="feed_comments"
    )
    author_name = models.CharField(max_length=120, blank=True)
    body = models.TextField()
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author_label}: {self.body[:40]}"

    @property
    def author_label(self) -> str:
        if self.author_user_id:
            user = self.author_user
            return (user.get_full_name() or user.username) if user else ""
        if self.author_customer_id and self.author_customer:
            return self.author_customer.name or self.author_customer.email
        return self.author_name or str(_("Gast"))

    @property
    def by_staff(self) -> bool:
        return bool(self.author_user_id)
