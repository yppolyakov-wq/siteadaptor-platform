"""Click & Collect / заказы-lite (Track D / D2, TENANT).

Клиент собирает товары витрины (/sortiment/) в корзину-сессию и оформляет
самовывоз; владелец ведёт заказ по FSM (state_machine.OrderSM). v1 сознательно
без жёсткого остатка (предзаказ) и без онлайн-оплаты (payment_state вручную,
оплата в магазине) — решения ТЗ docs/track-d-business-os-spec.md §D2.

UUID-pk и смена статусов только FSM-хуками — задел на будущий SHARED-граф
заказов (маркетплейс/дропшип пристёгиваются событиями без переделки).
"""

import uuid
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Order(TimestampedModel):
    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_READY = "ready"
    STATUS_PICKED_UP = "picked_up"
    STATUS_SHIPPED = "shipped"  # G4: versandt (для доставки)
    STATUS_CANCELLED = "cancelled"
    STATUS_RETURNED = "returned"  # A2c: возврат после выдачи/отправки (Widerruf)
    STATUSES = [
        (STATUS_NEW, _("New")),
        (STATUS_CONFIRMED, _("Confirmed")),
        (STATUS_READY, _("Ready")),
        (STATUS_PICKED_UP, _("Picked up")),
        (STATUS_SHIPPED, _("Shipped")),
        (STATUS_CANCELLED, _("Cancelled")),
        (STATUS_RETURNED, _("Returned")),
    ]
    # G4: способ получения. pickup — самовывоз (как раньше); delivery — доставка.
    FULFILLMENT_PICKUP = "pickup"
    FULFILLMENT_DELIVERY = "delivery"
    FULFILLMENTS = [(FULFILLMENT_PICKUP, _("Pickup")), (FULFILLMENT_DELIVERY, _("Delivery"))]
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_UNPAID, _("Unpaid")),
        (PAYMENT_PAID, _("Paid")),
        (PAYMENT_REFUNDED, _("Refunded")),
    ]
    # E-7: СПОСОБ оплаты (платёжный микс DACH) — ортогонален payment_state.
    # "" = легаси-заказы до введения поля. Реестр расширяем (paypal/klarna/sepa —
    # нативные провайдеры позже, через Stripe payment_method_types уже сейчас).
    METHOD_ON_SITE = "on_site"  # Barzahlung bei Abholung/Lieferung
    METHOD_STRIPE = "stripe"  # Online-Zahlung (Stripe Checkout, P2.5c)
    METHOD_VORKASSE = "vorkasse"  # Überweisung/Vorkasse (реквизиты в письме)
    PAYMENT_METHODS = [
        (METHOD_ON_SITE, _("Barzahlung bei Abholung")),
        (METHOD_STRIPE, _("Online-Zahlung")),
        (METHOD_VORKASSE, _("Vorkasse (Überweisung)")),
    ]

    # PROTECT, как у Reservation: клиента с заказами нельзя удалить молча
    # (DSGVO-стирание анонимизирует Customer, не удаляя записи).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    reference_code = models.CharField(max_length=12, unique=True)  # "O-XXXXXX"
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_NEW)
    # Желаемое время самовывоза (свободный выбор клиента); слоты/календарь — D3.
    pickup_slot = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    # T2a: номер стола для QR-заказа со стола (Dine-in). Пусто = самовывоз/доставка.
    table_number = models.CharField(max_length=20, blank=True)
    # Точка самовывоза (снимок, если у бизнеса их несколько). Пусто = единственный пункт.
    pickup_location = models.CharField(max_length=200, blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_UNPAID)
    # E-7: способ оплаты (см. PAYMENT_METHODS); "" = легаси до введения поля.
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHODS, blank=True, default=""
    )
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # P2.5c: для refund
    # Снимок суммы на момент заказа — цены каталога могут меняться.
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    # G4: доставка. fulfillment=pickup по умолчанию (обратная совместимость).
    fulfillment = models.CharField(max_length=10, choices=FULFILLMENTS, default=FULFILLMENT_PICKUP)
    shipping_address = models.TextField(blank=True)
    shipping_cents = models.PositiveIntegerField(default=0)  # снимок стоимости доставки
    # Промокод (A4): применённый код + скидка в центах (снимок, уже учтён в total).
    voucher_code = models.CharField(max_length=12, blank=True)
    # CM-6.4: post-purchase просьба об отзыве — дедуп «одно письмо на заказ».
    post_purchase_sent_at = models.DateTimeField(null=True, blank=True)
    # B2.1: напоминание о незавершённой Stripe-оплате — дедуп «одно на заказ».
    payment_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    # M3 Boutique (Click&Reserve, план m3-click-reserve-plan-2026-07-30):
    # дедлайн резерва «In der Anprobe» — задан ТОЛЬКО у Anprobe-резервов
    # (unverbindliche Reservierung, kein Kaufvertrag). Beat expire_due_anprobe
    # отменяет просроченные (restore стока — штатный путь cancelled).
    reserve_expires_at = models.DateTimeField(null=True, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)
    tracking_code = models.CharField(max_length=100, blank=True)  # номер DHL/Hermes
    # SH-8 (решение владельца 2026-08-20 «второй номер = ВНЕШНИЙ»): номер этого
    # заказа в чужой системе — касса, маркетплейс, бумажный журнал. Свободное
    # поле (форматы у всех разные), НЕ unique (внешние номера бывают повторными),
    # ищется поиском сделок наравне с reference_code.
    external_code = models.CharField(max_length=50, blank=True, db_index=True)
    # DC-9 (решение владельца 2026-08-26): на что действует скидка владельца —
    # вся сделка (дефолт, прежнее поведение), одна позиция или доставка. Сумма
    # скидки не меняется; меняется распределение базы НДС и показ.
    DISCOUNT_SCOPES = [
        ("deal", _("Ganze Bestellung")),
        ("position", _("Position")),
        ("delivery", _("Versand")),
    ]
    discount_scope = models.CharField(max_length=12, choices=DISCOUNT_SCOPES, default="deal")
    # SH-9: плательщик, если он не совпадает с получателем заказа (фирма платит
    # за сотрудника, родитель за ребёнка). Снимок для счёта — §14 UStG требует
    # реквизиты ПОЛУЧАТЕЛЯ счёта, а не того, кто забирает товар.
    billing_name = models.CharField(max_length=200, blank=True)
    billing_address = models.TextField(blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)

    # Швы под маркетплейс/dropshipping (M11→M14/M15, master-plan §7) — ПАССИВНЫЕ,
    # логики наследования пока нет. parent_order — дочерний заказ в цепочке (в этой
    # же схеме; кросс-тенантную привязку добавим с модулем); supplier_tenant_schema —
    # схема бизнеса-поставщика, исполняющего заказ (кросс-тенантно, как у aggregator).
    parent_order = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="child_orders"
    )
    supplier_tenant_schema = models.CharField(max_length=63, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="order_status_created_idx"),
        ]

    def __str__(self):
        return self.reference_code

    @property
    def is_delivery(self) -> bool:
        return self.fulfillment == self.FULFILLMENT_DELIVERY

    @property
    def is_anprobe(self) -> bool:
        """M3: заказ-резерв «In der Anprobe» (без оплаты, TTL, свои письма)."""
        return self.reserve_expires_at is not None

    @property
    def is_quote(self) -> bool:
        """MEN-9: заказ-ЗАПРОС на просчёт (кейтеринг): собран корзиной, но без
        платёжной обязанности — свои тексты подтверждения и письма."""
        return self.source_channel == "quote"

    @property
    def shipping_eur(self):
        from decimal import Decimal

        return Decimal(self.shipping_cents) / 100

    @property
    def discount_eur(self):
        from decimal import Decimal

        return Decimal(self.discount_cents) / 100


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # null = комбо-позиция (товара нет, есть combo). Иначе обычный товар.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Комбо-набор (A4): позиция-набор; состав — снимок в modifiers.
    combo = models.ForeignKey(
        "catalog.Combo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Вариант (R1): null = товар без вариантов. label — снимок (как title/price).
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    variant_label = models.CharField(max_length=100, blank=True)
    # Фидбэк 2026-08-04 «везде артикул»: снимок Art.-Nr. на момент покупки
    # (вариантный приоритетнее товарного; sku владелец может менять позже).
    sku = models.CharField(max_length=100, blank=True)
    qty = models.PositiveIntegerField(default=1)
    # Снимки цены/названия: заказ показывает то, что видел клиент.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # SH-4: СНИМОК ставки НДС позиции (как unit_price/title): смена ставки в
    # каталоге не переписывает уже выставленный документ. Цена брутто, поэтому
    # ставка нужна для разложения итога (нетто/НДС), а не для доначисления.
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("19.00"))
    # ERP-1: снимок себестоимости (EK netto) на момент продажи — как снимаются
    # цена/НДС/артикул. NULL = легаси-позиция или товар без EK; маржа по ТЕКУЩЕМУ
    # cost_price дрейфовала после смены закупочной цены.
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # SH-22 (фидбэк «при заказе товара со скидкой должна быть прописана скидка»):
    # снимок ЛИСТОВОЙ цены ЗА ЕДИНИЦУ на момент продажи. NULL = скидки не было
    # или легаси-строка — разницу не выдумываем: `old_price`/`title` акции живые
    # и переживают правку кампании (доктрина снимков SH-4/ERP-1). Храним цену за
    # единицу, а не сумму скидки: правка количества в кабинете масштабирует
    # `(list_price − unit_price) × qty` сама.
    list_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Акция-источник цены (SET_NULL: снимок переживает удаление кампании) и
    # снимок её названия на момент продажи.
    promotion = models.ForeignKey(
        "promotions.Promotion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    promo_label = models.CharField(max_length=200, blank=True)
    title_snapshot = models.CharField(max_length=200)
    # Снимок выбранных модификаторов/Extras (A4b): [{"label","delta"}]. Надбавка
    # уже включена в unit_price; список — для отображения в заказе/письмах.
    modifiers = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.qty}× {self.title_snapshot}"

    @property
    def image_url(self) -> str:
        """SH-21 (фидбэк «фото товара в строке заказа»): главное фото позиции —
        фото варианта (M4-A) → главное фото товара → фото комбо; свободная строка —
        пусто (плейсхолдер в шаблоне). Живые FK: удалённый товар → плейсхолдер."""
        if self.variant_id:
            url = self.variant.image_url
            if url:
                return url
        if self.product_id:
            img = self.product.primary_image
            if isinstance(img, dict):
                return img.get("url", "") or ""
        if self.combo_id:
            return self.combo.primary_image_url
        return ""

    @property
    def line_total(self):
        return self.unit_price * self.qty

    @property
    def discount_per_unit(self):
        """SH-22: выгода за единицу (листовая − уплаченная). Легаси-строка без
        снимка листовой цены → 0: «скидки не видно» честнее выдуманной."""
        if self.list_price is None:
            return Decimal("0")
        return max(Decimal(str(self.list_price)) - Decimal(str(self.unit_price)), Decimal("0"))

    @property
    def discount_total(self):
        """SH-22: выгода по строке — масштабируется правкой количества."""
        return self.discount_per_unit * self.qty

    @property
    def list_total(self):
        """SH-22: сумма строки по ЛИСТОВОЙ цене (Zwischensumme до скидок акций)."""
        base = self.list_price if self.list_price is not None else self.unit_price
        return Decimal(str(base)) * self.qty

    @property
    def promo_name(self) -> str:
        """Название акции для показа: снимок → живая кампания → пусто."""
        if self.promo_label:
            return self.promo_label
        if self.promotion_id and self.promotion is not None:
            title = self.promotion.title or {}
            return title.get("de") or next(iter(title.values()), "")
        return ""

    @property
    def modifiers_label(self) -> str:
        """«Pommes, Käse» — выбранные модификаторы для отображения (A4b).

        Фидбэк 2026-08-04: у опции с артикулом печатаем его рядом с меткой
        («Sirup [Art.-Nr. S-12]») — снимок пишет create_order."""
        parts = []
        for m in self.modifiers or []:
            # SH-22: служебный маркер {"promo": id} печатался как «Aktion» —
            # у строки со снимком акции это дублирует подпись «−X € · Aktion „…“».
            # У легаси-строк (снимка нет) маркер печатаем как раньше.
            if m.get("promo") and self.promo_label:
                continue
            label = m.get("label", "")
            if m.get("sku"):
                label = _("%(label)s [Art.-Nr. %(sku)s]") % {"label": label, "sku": m["sku"]}
            parts.append(label)
        return ", ".join(parts)


class Offer(TimestampedModel):
    """LS-3 «Sofort-Angebot»: персональное предложение из чата (inbox).

    Живёт ОТДЕЛЬНО от заказа: непринятое предложение не засоряет канбан.
    Принятие конвертирует его в обычный Order (offers.accept_offer) — оплата/
    статусы/письма дальше идут существующими путями orders. jobs (смета
    Handwerker, свой цикл net/VAT/Rechnung) сознательно не обобщён — план
    docs/ls3-sofort-angebot-plan-2026-07-19.md §1.
    """

    STATUS_OPEN = "open"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED = "cancelled"  # владелец отозвал
    STATUSES = [
        (STATUS_OPEN, _("Open")),
        (STATUS_ACCEPTED, _("Accepted")),
        (STATUS_DECLINED, _("Declined")),
        (STATUS_CANCELLED, _("Cancelled")),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Тред-источник (SET_NULL: удаление треда не трогает историю предложений).
    conversation = models.ForeignKey(
        "inbox.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offers",
    )
    # Снимок адресата на момент отправки; у анонимного треда может быть пусто —
    # тогда name/email спрашивает публичная страница при принятии.
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="offers"
    )
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    note = models.TextField(blank=True)  # личное сообщение на странице предложения
    valid_until = models.DateField(null=True, blank=True)  # пусто = бессрочно
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_OPEN)
    # Заказ, созданный при принятии (идемпотентность повторного POST).
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="offers"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Angebot {str(self.token)[:8]}"

    @property
    def total(self):
        from decimal import Decimal

        return sum((line.line_total for line in self.lines.all()), Decimal("0"))

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return bool(self.valid_until and self.valid_until < timezone.localdate())

    @property
    def is_open(self) -> bool:
        return self.status == self.STATUS_OPEN and not self.is_expired


class OfferLine(TimestampedModel):
    """Позиция предложения — снимок (цена/название заморожены при отправке).

    kind/ref_id — провенанс из пикера (product/service/stay/event/combo или
    ''=свободная строка); НЕ FK: источник может исчезнуть, предложение — нет.
    Цена БРУТТО как OrderItem.unit_price (PAngV) — без net/VAT-математики jobs.
    """

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=10, blank=True, default="")
    # str, не FK/int: pk источника бывает UUID (Product) — как Conversation.ref_id.
    ref_id = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=200)
    # SH-20 (фидбэк «артикул везде»): снимок Art.-Nr. источника (товар/вариант) —
    # ref_id не FK, товар может исчезнуть, а предложение обязано печатать артикул.
    sku = models.CharField(max_length=100, blank=True, default="")
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return f"{self.qty}× {self.title}"

    @property
    def line_total(self):
        return self.unit_price * self.qty
