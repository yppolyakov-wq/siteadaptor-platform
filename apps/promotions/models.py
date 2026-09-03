"""Акции и резервирование (TENANT-схема).

Спецификация: phase1-plan-additions.md §3 + паттерны:
- state-machine.md — смена статусов только через PromotionSM/ReservationSM
- anti-oversell.md — атомарное списание остатка (см. services.py)

Прямые присваивания obj.status = ... запрещены — двигаем через FSM.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import I18nMixin, SoftDeleteMixin, TimestampedModel

_CENTS = Decimal("0.01")


class Customer(TimestampedModel):
    """Покупатель. Создаётся при первой брони, переиспользуется по email.

    CRM-минимум (Track C3): клиентов можно заводить и вручную (без брони),
    вешать теги и заметки (apps.crm) — «клиент» не привязан к товару/заказу.
    """

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)  # ["stammkunde", "vip", …]
    # CO-1 (корпоративный контур v1): привязка гостя к компании-справочнику.
    # Строковая ссылка — crm импортирует promotions, не наоборот.
    company = models.ForeignKey(
        "crm.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customers",
    )

    # CRM-lite (Track D / D1): откуда появилась запись и явное согласие на
    # маркетинг (UWG §7: рассылать можно только при opt-in; one-click отписка
    # unsubscribed — отдельный флаг и работает поверх).
    SOURCE_RESERVATION = "reservation"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"
    SOURCE_ORDER = "order"  # Click & Collect (Track D / D2)
    CREATED_SOURCES = [
        (SOURCE_RESERVATION, _("Reservation")),
        (SOURCE_MANUAL, _("Manual")),
        (SOURCE_IMPORT, _("Import")),
        (SOURCE_ORDER, _("Order")),
    ]
    created_source = models.CharField(
        max_length=20, choices=CREATED_SOURCES, default=SOURCE_RESERVATION
    )
    marketing_opt_in = models.BooleanField(default=False)
    # G3: момент подтверждения согласия (Double-Opt-In, UWG §7) — доказательство.
    marketing_opt_in_at = models.DateTimeField(null=True, blank=True)
    # PMS-B2: день рождения (опционально, гость/владелец заполняют сами) —
    # питает «Geburtstagsgruß»-кампанию; DSGVO-purge обнуляет вместе с PII.
    birthday = models.DateField(null=True, blank=True)

    # быстрая отписка от писем (one-click): токен в ссылке + флаг
    unsubscribed = models.BooleanField(default=False)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="customer_email_idx"),
        ]

    def __str__(self):
        return self.name or self.email or str(self.pk)


class NewsletterCampaign(TimestampedModel):
    """G3: e-mail-рассылка гостям (UWG §7 — только подтвердившим opt-in).

    Владелец пишет тему/текст → отправка всем согласившимся (marketing_opt_in,
    не unsubscribed, с e-mail) через notifications (idempotent по кампании+клиенту).
    one-click отписка — в каждом письме (RFC 8058)."""

    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUSES = [(STATUS_DRAFT, _("Draft")), (STATUS_SENT, _("Sent"))]

    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class CouponCampaign(TimestampedModel):
    """B4/CM-9: купон-кампания по сегменту CRM-базы.

    Каждому клиенту сегмента — персональный одноразовый код (Voucher.campaign)
    + письмо. Получатели строятся ПОВЕРХ consented_customers() (UWG §7) —
    не-opt-in недостижим по построению. kind=auto_winback: настройки
    авто-триггера живут на самой кампании (beat читает active/paused —
    без SHARED-миграции Tenant).
    """

    KIND_MANUAL = "manual"
    KIND_AUTO_WINBACK = "auto_winback"
    # PMS-B2: авто-поздравление в день рождения (настройки на кампании-синглтоне).
    KIND_BIRTHDAY = "birthday"
    KINDS = [
        (KIND_MANUAL, _("Manuell")),
        (KIND_AUTO_WINBACK, _("Auto Win-back")),
        (KIND_BIRTHDAY, _("Geburtstag")),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_ACTIVE = "active"  # только auto_winback
    STATUS_PAUSED = "paused"  # только auto_winback
    STATUSES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_SENT, _("Sent")),
        (STATUS_ACTIVE, _("Active")),
        (STATUS_PAUSED, _("Paused")),
    ]

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=KINDS, default=KIND_MANUAL)

    # Сегмент (AND-комбинация; всё пустое = вся opt-in-база).
    tag = models.CharField(max_length=50, blank=True, default="")
    inactive_days = models.PositiveIntegerField(null=True, blank=True)
    top_ltv = models.PositiveIntegerField(null=True, blank=True)

    # Параметры персонального кода (percent ИЛИ cents, как у Voucher).
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    discount_cents = models.PositiveIntegerField(null=True, blank=True)
    min_order_cents = models.PositiveIntegerField(default=0)
    valid_days = models.PositiveIntegerField(default=30)  # срок кода от выдачи

    # Письмо (DE, авторский текст владельца — как NewsletterCampaign).
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def discount_eur(self):
        return (self.discount_cents or 0) / 100


class Promotion(SoftDeleteMixin, I18nMixin):
    DISCOUNT = "discount"
    RESERVATION = "reservation"
    PROMO_TYPES = [(DISCOUNT, _("Discount")), (RESERVATION, _("Reservation"))]

    title = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    description = models.JSONField(default=dict)

    product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotions",
    )
    # P1 «ценовой слой» (план promo-price-layer-plan-2026-08-03): цель акции —
    # ровно ОДНА из сущностей (product выше — исторический первый FK). Акция без
    # цели остаётся законной («свободная», чекаут custom_lines-заказом).
    service = models.ForeignKey(
        "booking.Service",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotions",
    )
    stay_unit = models.ForeignKey(
        "stays.StayUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotions",
    )
    combo = models.ForeignKey(
        "catalog.Combo",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotions",
    )
    # Условия применения к услуге (паттерн StaySettings.auto_discount_rules):
    # {"weekdays": [0..6], "hour_from": 10, "hour_to": 14, "resource_id": "..."}
    # — «счастливые часы»/конкретный мастер. Пусто = без ограничений.
    target_rules = models.JSONField(default=dict, blank=True)

    promo_type = models.CharField(max_length=20, choices=PROMO_TYPES, default=RESERVATION)
    # Скидку владелец задаёт ЛИБО в %, ЛИБО новой ценой (price_override) —
    # остальное считаем (см. свойства old_price/new_price/discount_*).
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Старая (зачёркнутая) цена: если пусто — фолбэк на base_price товара.
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Картинки акции (FileRef-envelope, как у товара). Если пусто — фолбэк на фото товара.
    images = models.JSONField(default=list, blank=True)

    # null = без лимита (для discount); для reservation задаёт остаток
    available_quantity = models.IntegerField(null=True, blank=True)
    max_per_customer = models.PositiveSmallIntegerField(default=1)

    # настройки брони
    reservation_ttl_hours = models.PositiveIntegerField(default=24)
    auto_confirm = models.BooleanField(default=False)

    # витрина: показывать обратный отсчёт и зачёркивать старую цену
    show_countdown = models.BooleanField(default=False)
    strikethrough_old_price = models.BooleanField(default=True)

    # «Überraschungstüte» / анти-waste: сюрприз-пакет уценённых остатков (Track B2).
    # Поверх обычной брони — отдельная механика не нужна, только пресет + бейдж.
    is_surprise = models.BooleanField(default=False)

    # UE2-2: стиль вывода скидки на витрине (ветвление в _discount_display.html).
    # "" = автоматически (легаси-вид: %-бейдж, иначе −€; цена по флагам) — default
    # сохраняет вид существующих акций. Только презентация: свойства цены/
    # has_discount/анти-оверселл не зависят от стиля.
    DISCOUNT_STYLES = [
        ("", _("Automatisch")),
        ("percent", _("Prozent-Badge (−30 %)")),
        ("badge", _("Betrag-Badge (−5 €)")),
        ("strikethrough", _("Nur durchgestrichener Preis")),
        ("festpreis", _("Nur neuer Preis (Festpreis)")),
        ("ab", _("Ab-Preis („ab 7,50 €“)")),
        ("countdown", _("Countdown-Akzent")),
        ("surprise", _("Überraschung im Fokus")),
        # UE2-3: цена/фото скрыты до клика-раскрытия (чистая презентация,
        # бронь/остаток не зависят). AlterField choices — без изменения БД.
        ("mystery", _("Mystery — Preis bis Klick versteckt")),
    ]
    discount_style = models.CharField(
        max_length=20, choices=DISCOUNT_STYLES, default="", blank=True
    )

    # DL-19: ФОРМА карточки этой акции (реестр core.card_forms). Пусто = форма из
    # настроек сайта (site_defaults.promo_card); своя побеждает общую. Только
    # презентация — цена/лимит/бронь от формы не зависят.
    card_style = models.CharField(max_length=16, blank=True, default="")

    # Авто-повтор акции (Track B3b): beat клонирует завершившуюся со сдвигом окна
    # на интервал. Наследник один (recurrence уходит к нему, у родителя гасится),
    # поэтому цепочка не ветвится.
    NO_RECUR, DAILY, WEEKLY = "", "daily", "weekly"
    RECURRENCE = [(NO_RECUR, "—"), (DAILY, _("Täglich")), (WEEKLY, _("Wöchentlich"))]
    recurrence = models.CharField(max_length=10, choices=RECURRENCE, default=NO_RECUR, blank=True)

    # S6: группа/направление акции («Fastfood», «Fertiggerichte»…) — для отдельных
    # подразделов витрины (/aktionen/?gruppe=…) и целей меню (promo_group).
    # Свободный текст: набор групп определяет владелец, фильтр — по точному значению.
    group = models.CharField(max_length=50, blank=True, default="", db_index=True)
    # Переводим только МЕТКУ группы; ключ фасета (?gruppe=) остаётся плоским
    # значением, иначе ссылки на подраздел разъехались бы между локалями.
    group_i18n = models.JSONField(default=dict, blank=True)

    # Ревью 2026-08-19: подписи статуса жили СЛОВАРЁМ во вьюхе (X6-3), поэтому
    # каждый новый экран печатал сырой код, пока ключ не прокинут руками (так и
    # случилось с аналитикой). Источник подписей — модель: `get_status_display`
    # работает везде по умолчанию. AlterField choices-only → DDL не порождает.
    STATUSES = [
        ("draft", _("Entwurf")),
        ("scheduled", _("Geplant")),
        ("active", _("Aktiv")),
        ("paused", _("Pausiert")),
        ("ended", _("Beendet")),
        ("archived", _("Archiviert")),
    ]

    status = models.CharField(max_length=20, choices=STATUSES, default="draft", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    # аналитика: счётчик просмотров публичной страницы акции
    views = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # планировщик статусов (scheduled→active, active→ended) ходит по ним
            models.Index(fields=["status", "starts_at"], name="promo_status_starts_idx"),
            models.Index(fields=["status", "ends_at"], name="promo_status_ends_idx"),
        ]

    def __str__(self):
        return self.get_i18n("title") or str(self.pk)

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def description_text(self) -> str:
        return self.get_i18n("description")

    @property
    def group_localized(self) -> str:
        """Метка группы на текущей локали (ключ фильтра — плоский `group`)."""
        return self.get_overlay("group", "group_i18n")

    # --- цена и скидка --------------------------------------------------

    @staticmethod
    def _dec(value):
        return None if value is None else Decimal(str(value))

    @property
    def currency(self) -> str:
        return self.product.currency if self.product_id and self.product else "EUR"

    @property
    def old_price(self):
        """Старая цена: compare_at_price, иначе base_price товара, иначе None."""
        if self.compare_at_price is not None:
            return self._dec(self.compare_at_price)
        if self.product_id and self.product:
            return self._dec(self.product.base_price)
        return None

    @property
    def new_price(self):
        """Новая цена: price_override, иначе old_price со скидкой %, иначе old_price."""
        old = self.old_price
        if self.price_override is not None:
            return self._dec(self.price_override)
        if self.discount_percent and old is not None:
            factor = (Decimal(100) - Decimal(int(self.discount_percent))) / Decimal(100)
            return (old * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return old

    @property
    def has_discount(self) -> bool:
        old, new = self.old_price, self.new_price
        return old is not None and new is not None and new < old

    @property
    def discount_amount(self):
        if not self.has_discount:
            return None
        return (self.old_price - self.new_price).quantize(_CENTS)

    @property
    def grundpreis(self):
        """DL-13 C5 (PAngV, аудит DL-12 P3): Grundpreis по ПРОМО-цене — у акции на
        весовой/объёмный товар без вариантов (кг/л как у карточки товара);
        иначе None (свободная акция, услуга, номер, товар с вариантами)."""
        if not (self.product_id and self.product) or self.product.has_variants:
            return None
        from apps.catalog.pricing import grundpreis

        return grundpreis(self.new_price, self.product.unit, self.product.content_amount)

    @property
    def discount_percent_display(self):
        """Целый процент скидки для бейджа (−XX %)."""
        if self.discount_percent:
            return int(self.discount_percent)
        if self.has_discount and self.old_price > 0:
            pct = (Decimal(1) - (self.new_price / self.old_price)) * Decimal(100)
            return int(pct.to_integral_value(rounding=ROUND_HALF_UP))
        return None

    # --- витрина: медиа и таймер ---------------------------------------

    @property
    def primary_image(self):
        """Главное фото акции; фолбэк на главное фото привязанного товара."""
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        if imgs:
            return imgs[0]
        if self.product_id and self.product:
            return self.product.primary_image
        return None

    @property
    def target(self):
        """P1: базовая сущность акции (product/service/stay_unit/combo) или None
        («свободная» акция). Ровно одна — гарантирует clean()/форма."""
        return self.product or self.service or self.stay_unit or self.combo

    @property
    def target_kind(self) -> str:
        """Kind цели в терминах SellableEntity ('' у свободной акции)."""
        if self.product_id:
            return "product"
        if self.service_id:
            return "service"
        if self.stay_unit_id:
            return "stay"
        if self.combo_id:
            return "combo"
        return ""

    @property
    def gallery_images(self) -> list:
        """Фото для галереи детальной: своя галерея акции, иначе фото товара
        (фидбэк 2026-07-29 — миниатюры под главным фото)."""
        if self.images:
            return list(self.images)
        if self.product_id and self.product:
            return list(self.product.images or [])
        return []

    @property
    def seconds_left(self):
        """Секунд до ends_at (для обратного отсчёта). None если конца нет."""
        if not self.ends_at:
            return None
        delta = (self.ends_at - timezone.now()).total_seconds()
        return int(delta) if delta > 0 else 0

    @property
    def is_sold_out(self) -> bool:
        """Лимитированная акция распродана (остаток 0)."""
        return self.available_quantity is not None and self.available_quantity <= 0

    @property
    def is_new(self) -> bool:
        """Стартовала в последние 7 дней — чип «Neu» на карточке (Prospekt-культура:
        покупатель ищет новинки недели). Повторяющиеся акции новыми не считаем."""
        if self.recurrence:
            return False
        start = self.starts_at or self.created_at
        return bool(start) and (timezone.now() - start).days < 7


class Reservation(TimestampedModel):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="reservations")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="reservations")

    # короткий человекочитаемый код для выдачи (R-XXXXXX)
    reference_code = models.CharField(max_length=12, unique=True)
    quantity = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=20, default="pending", db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    note = models.TextField(blank=True)

    # канал привлечения (?ch= в ссылке/QR): instagram, flyer, schaufenster…
    source_channel = models.CharField(max_length=50, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="resv_status_expires_idx"),
            models.Index(fields=["promotion", "status"], name="resv_promo_status_idx"),
        ]

    def __str__(self):
        return self.reference_code


class WaitlistEntry(TimestampedModel):
    """Запись в лист ожидания, когда акция распродана.

    Контакт берём с согласия для одного уведомления о наличии (DSGVO).
    """

    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="waitlist")
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    notified = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # один email в листе ожидания на акцию
            models.UniqueConstraint(fields=["promotion", "email"], name="uniq_waitlist_promo_email")
        ]

    def __str__(self):
        return f"{self.email} → {self.promotion_id}"
