"""Базовые абстрактные модели и миксины для всех TENANT-приложений.

Спецификации:
- TimestampedModel / I18nMixin — phase1-implementation-guide.md, Часть 2
- SoftDeleteMixin            — docs/references/patterns/soft-delete.md

Миксины абстрактные; единственная конкретная таблица — Membership (шов ролей
multi-user, M6 / master-plan §7).
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language


class TimestampedModel(models.Model):
    """UUID-PK + created_at/updated_at. База для большинства tenant-моделей."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class I18nMixin:
    """Утилиты для переводимых JSONField вида {"de": "...", "en": "..."}.

    Фолбэк: запрошенный → default_locale (de) → en → первое доступное → ''.
    """

    def get_i18n(self, field_name: str, locale: str | None = None) -> str:
        locale = locale or get_language() or "de"
        value = getattr(self, field_name) or {}
        if not isinstance(value, dict):
            return ""
        if value.get(locale):
            return value[locale]
        if value.get("de"):
            return value["de"]
        if value.get("en"):
            return value["en"]
        # первое непустое значение из словаря
        for v in value.values():
            if v:
                return v
        return ""

    def get_overlay(self, base_field: str, overlay_field: str, locale: str | None = None) -> str:
        """L3 (Волна L): значение по схеме «база + оверлей» для моделей, где базовая
        локаль живёт в ПЛОСКОМ поле (`base_field`), а переводы неосновных локалей — в
        JSONField-оверлее (`overlay_field` = {locale: str}). Базовая локаль
        (`settings.LANGUAGE_CODE`) ВСЕГДА берётся из плоского поля (source of truth,
        без дрейфа); прочие — из оверлея, с фолбэком на базу. Так модель несёт i18n,
        не ломая существующий доступ к плоскому полю."""
        locale = locale or get_language() or settings.LANGUAGE_CODE
        if locale != settings.LANGUAGE_CODE:
            overlay = getattr(self, overlay_field, None)
            if isinstance(overlay, dict) and overlay.get(locale):
                return overlay[locale]
        return getattr(self, base_field, "") or ""

    def i18n_full(
        self, base_field: str, overlay_field: str, base_locale: str | None = None
    ) -> dict:
        """Полный словарь {locale: str} = база (плоское поле) + оверлей неосновных
        локалей. Единый вид для адаптера SellableEntity (U-A) — читать i18n всех kind
        единообразно. База всегда авторитетна из плоского поля."""
        base_locale = base_locale or settings.LANGUAGE_CODE
        overlay = getattr(self, overlay_field, None)
        out = {k: v for k, v in overlay.items() if v} if isinstance(overlay, dict) else {}
        out[base_locale] = getattr(self, base_field, "") or ""
        return out


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):  # bulk soft-delete
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class AliveManager(models.Manager):
    """Менеджер по умолчанию: отдаёт только не удалённые записи."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteMixin(TimestampedModel):
    """Мягкое удаление через deleted_at.

    objects     — только живые (default-менеджер, используется в related-доступе).
    all_objects — все записи, включая удалённые (для admin/корзины/восстановления).

    ВНИМАНИЕ про unique: удалённая строка продолжает занимать уникальное значение.
    Для уникальных полей используй partial constraint, см. soft-delete.md:
        UniqueConstraint(fields=[...], condition=Q(deleted_at__isnull=True), name=...)
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = AliveManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Membership(TimestampedModel):
    """Роль пользователя в тенанте (M6 / master-plan §7, шов multi-user).

    TENANT-scope: пользователи пер-тенантные (`django.contrib.auth` — TENANT_APP),
    поэтому членство живёт в схеме бизнеса. Сейчас ролевой гейтинг во вьюхах НЕ
    применяется (один владелец = owner); модель + `roles.role_of()` — точка
    централизации под будущее приглашение сотрудников (admin/staff), чтобы
    добавление прав было аддитивным, без ретрофита логики.
    """

    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_STAFF = "staff"
    ROLES = [(ROLE_OWNER, "Owner"), (ROLE_ADMIN, "Admin"), (ROLE_STAFF, "Staff")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    role = models.CharField(max_length=20, choices=ROLES, default=ROLE_OWNER)

    class Meta:
        ordering = ["role"]

    def __str__(self):
        return f"{self.user} · {self.role}"


class Extra(TimestampedModel):
    """Универсальная платная доп-услуга к брони (#7, TENANT).

    Одна механика на все движки записи: бизнес задаёт Extras (Frühstück, Parkplatz,
    Späte Abreise …), гость отмечает их при бронировании, цена идёт в total и
    finance. `scope` ограничивает, к какому архетипу применима (или ко всем).
    Привязки/цена снимаются в JSON-поле брони (StayBooking.extras и т.п.) —
    Extra может меняться/удаляться, исторические брони не затрагиваются."""

    SCOPE_ALL = "all"
    SCOPE_STAYS = "stays"
    SCOPE_BOOKING = "booking"
    SCOPE_EVENTS = "events"
    SCOPES = [
        (SCOPE_ALL, "Alle"),
        (SCOPE_STAYS, "Übernachtung"),
        (SCOPE_BOOKING, "Termin"),
        (SCOPE_EVENTS, "Event"),
    ]

    label = models.CharField(max_length=120)
    price_cents = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=10, choices=SCOPES, default=SCOPE_ALL)
    # Для stays: цена за ночь (× кол-во ночей), иначе разовая за бронь.
    per_night = models.BooleanField(default=False)
    # A5: фото доп-услуги (FileRef-конверт {url, …}, как у Service.image). Пусто =
    # без фото (как раньше). Показывается миниатюрой рядом с чекбоксом на витрине.
    image = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.label} (+{self.price_cents / 100:.2f})"

    @property
    def price_eur(self):
        return Decimal(self.price_cents) / 100

    @property
    def image_url(self) -> str:
        """A5: URL фото доп-услуги (или ''), безопасно к не-dict значению."""
        return self.image.get("url", "") if isinstance(self.image, dict) else ""
