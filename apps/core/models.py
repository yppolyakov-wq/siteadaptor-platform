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
from django.utils.translation import gettext_lazy as _


class TimestampedModel(models.Model):
    """UUID-PK + created_at/updated_at. База для большинства tenant-моделей."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def resolve_overlay(base: str, overlay, locale: str | None = None) -> str:
    """Значение «база + оверлей» БЕЗ объекта модели.

    Та же семантика, что у `I18nMixin.get_overlay` (который сюда и делегирует):
    базовая локаль всегда из плоского значения, прочие — из `overlay[locale]`
    с фолбэком на базу. Нужна отдельно там, где строки читаются пачкой через
    `values_list` (напр. метки групп акций) и объектов модели просто нет.
    """
    locale = locale or get_language() or settings.LANGUAGE_CODE
    if locale != settings.LANGUAGE_CODE and isinstance(overlay, dict) and overlay.get(locale):
        return overlay[locale]
    return base or ""


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
        return resolve_overlay(
            getattr(self, base_field, ""), getattr(self, overlay_field, None), locale
        )

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
    ROLES = [(ROLE_OWNER, _("Owner")), (ROLE_ADMIN, _("Admin")), (ROLE_STAFF, _("Staff"))]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    role = models.CharField(max_length=20, choices=ROLES, default=ROLE_OWNER)

    class Meta:
        ordering = ["role"]

    def __str__(self):
        return f"{self.user} · {self.role}"


class Extra(I18nMixin, TimestampedModel):
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
        (SCOPE_ALL, _("Alle")),
        (SCOPE_STAYS, _("Übernachtung")),
        (SCOPE_BOOKING, _("Termin")),
        (SCOPE_EVENTS, _("Event")),
    ]

    # MX-2 (план mx2-options-trackers-plan-2026-08-21.md): вид ТРЕКЕРА — как опция
    # обрабатывается за кулисами (§5b стратегии: опция = цена + трекер). "" = чистая
    # надбавка (поведение как раньше). v1: pool/stock — заявленный вид (информативно,
    # enforcement — слайс 2e); purchase — подсказка закупки (MX-4).
    TRACKER_NONE = ""
    TRACKER_POOL = "pool"
    TRACKER_STOCK = "stock"
    TRACKER_PURCHASE = "purchase"
    TRACKERS = [
        (TRACKER_NONE, _("Aufpreis")),
        (TRACKER_POOL, _("Eigener Bestand (Pool)")),
        (TRACKER_STOCK, _("Lagerartikel")),
        (TRACKER_PURCHASE, _("Beim Anbieter zu buchen")),
    ]

    label = models.CharField(max_length=120)
    label_i18n = models.JSONField(default=dict, blank=True)  # I18N-12: показ на локали
    price_cents = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=10, choices=SCOPES, default=SCOPE_ALL)
    # MX-2: адресность — опция КОНКРЕТНОЙ сущности (пусто = scope-wide, как раньше).
    # Строки, не FK: kind живут в разных аппах (прецедент DealLink).
    entity_kind = models.CharField(max_length=20, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="")
    tracker = models.CharField(max_length=12, choices=TRACKERS, blank=True, default="")
    # Размер собственного пула (tracker=pool): «8 прокатных мотоциклов».
    pool_size = models.PositiveSmallIntegerField(default=0)
    # Поставщик закупаемой опции (tracker=purchase) — префилл Anbieter-Buchung (MX-4).
    supplier = models.ForeignKey(
        "inventory.Lieferant", null=True, blank=True, on_delete=models.SET_NULL
    )
    # Складская Вещь расходуемой опции (tracker=stock; рецепт — слайс 2e).
    product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.SET_NULL)
    # v2-рецепт: сколько единиц Вещи расходует ОДНА продажа опции (×ночи у
    # per_night-stay — как множатся деньги снимка). 1 = прежнее поведение.
    consume_qty = models.PositiveSmallIntegerField(default=1)
    # Своя ставка НДС опции (завтрак 19 % в брони 7 %); NULL = ставка сделки.
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
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

    def label_localized(self, locale: str | None = None) -> str:
        """I18N-12: показ доп-услуги в buy-box на локали (снимок в брони — базовый)."""
        return self.get_overlay("label", "label_i18n", locale)

    @property
    def price_eur(self):
        return Decimal(self.price_cents) / 100

    @property
    def image_url(self) -> str:
        """A5: URL фото доп-услуги (или ''), безопасно к не-dict значению."""
        return self.image.get("url", "") if isinstance(self.image, dict) else ""


class MediaAsset(TimestampedModel):
    """CM-4: индекс медиа-файлов тенанта ПОВЕРХ FileRef-копий в сущностях.

    Наполняется хуком в catalog.images.save_product_image (единственная точка
    входа всех FileRef-загрузок) + backfill-командой; удаляется вместе с файлом
    в delete_stored_image. Источник рендера — по-прежнему FileRef в сущностях;
    реестр — обзор/alt-редактор/поиск незанятых (кабинет «Medien»). Карта мест
    использования — apps/core/media_registry.py.
    """

    path = models.CharField(max_length=300, unique=True)  # ключ storage (folder/uuid.ext)
    url = models.CharField(max_length=500, blank=True)
    folder = models.CharField(max_length=40, blank=True, db_index=True)
    mime_type = models.CharField(max_length=40, blank=True)
    size = models.PositiveIntegerField(default=0)
    alt = models.JSONField(default=dict, blank=True)  # {локаль: str}

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.path


class LegalDoc(TimestampedModel):
    """L5/E-2: правовой документ витрины per-locale (TENANT-схема).

    Резолв — apps/core/legal.py: LegalDoc[текущая локаль] → LegalDoc[дефолт
    тенанта] → плоское Tenant-поле → генерённый фолбэк. Пустой text = строка
    не участвует в резолве (эквивалент отсутствия). AGB фолбэка не имеет:
    без текста страница /agb/ отдаёт 404, ссылка в футере скрыта.
    """

    KIND_CHOICES = [
        ("impressum", _("Impressum")),
        ("datenschutz", _("Datenschutz")),
        ("widerruf", _("Widerruf")),
        ("agb", _("AGB")),
    ]
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    locale = models.CharField(max_length=8)
    text = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "locale"], name="legaldoc_kind_locale_uniq")
        ]

    def __str__(self):
        return f"{self.kind}/{self.locale}"


class DealLink(TimestampedModel):
    """VS-3: связь «якорь → прикреплённая сделка» (план vs3-deal-links-plan-2026-08-20).

    Запрос владельца: «к номеру/брони привязываются услуги… они должны двигаться по
    колонкам отдельно». Спутник (велопрокат, трансфер, предзаказ) остаётся
    САМОСТОЯТЕЛЬНОЙ сделкой со своим статусом, ценой и вкладкой; связь лишь
    показывает, к чему он относится.

    Почему таблица, а не поля на шести моделях: одна аддитивная миграция вместо
    шести, симметричные запросы в обе стороны и ноль правок в движках сделок.
    Почему не FK/GenericForeignKey: якорь и спутник — РАЗНЫЕ модели, а GFK тянул бы
    джойн `contenttypes` на каждую карточку доски. Приём в проекте уже принят —
    `reviews.Review(entity_kind, entity_id)`, `inbox.Conversation(ref_kind, ref_id)`;
    сироты (объект удалён) отсекаются при чтении.

    `unique(child_kind, child_id)` — у спутника ровно ОДИН якорь: иначе «+1 услуга»
    показывалась бы у двух разных броней про один и тот же прокат. Перепривязка =
    обновление той же строки.
    """

    anchor_kind = models.CharField(max_length=16)
    anchor_id = models.UUIDField()
    child_kind = models.CharField(max_length=16)
    child_id = models.UUIDField()
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["child_kind", "child_id"], name="deallink_one_anchor_per_child"
            )
        ]
        indexes = [
            models.Index(fields=["anchor_kind", "anchor_id"], name="deallink_anchor_idx"),
            models.Index(fields=["child_kind", "child_id"], name="deallink_child_idx"),
        ]

    def __str__(self):
        return f"{self.anchor_kind}:{self.anchor_id} → {self.child_kind}:{self.child_id}"
