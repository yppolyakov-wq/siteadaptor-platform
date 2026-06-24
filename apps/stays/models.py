"""Date-range-Buchung / Übernachtung (Track E / E1, TENANT).

Движок «по ночам» — параллель apps.booking (по времени суток). Бронь = диапазон
дат ``[arrival, departure)`` (ночь выезда снова свободна); инвентарь = StayUnit с
``quantity`` идентичных юнитов (Ferienwohnung = 1, «Doppelzimmer» = N). Анти-
овербукинг — атомарная пер-ночная проверка занятости под блокировкой строки юнита
(services.book_stay, зеркало anti-oversell/booking). Переиспользуем Customer,
Stripe-Connect-оплату (P2.5b/c), finance, notifications и реестр модулей.
"""

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer

# H3: каталог удобств номера (key, метка DE, эмодзи) — чек-лист на юните,
# иконки на витрине. Узкий фиксированный список под малый отель DACH.
AMENITIES = [
    ("wifi", "WLAN", "📶"),
    ("tv", "TV", "📺"),
    ("bath", "Eigenes Bad", "🛁"),
    ("shower", "Dusche", "🚿"),
    ("balcony", "Balkon/Terrasse", "🌅"),
    ("aircon", "Klimaanlage", "❄️"),
    ("kitchen", "Küche/Kitchenette", "🍳"),
    ("minibar", "Minibar", "🧊"),
    ("safe", "Safe", "🔒"),
    ("desk", "Schreibtisch", "🖥️"),
    ("coffee", "Kaffee/Tee", "☕"),
    ("hairdryer", "Föhn", "💨"),
    ("parking", "Parkplatz", "🅿️"),
    ("petfriendly", "Haustiere erlaubt", "🐾"),
    ("wheelchair", "Barrierefrei", "♿"),
    ("nonsmoking", "Nichtraucher", "🚭"),
]
_AMENITY_LABELS = {key: (label, icon) for key, label, icon in AMENITIES}
_AMENITY_KEYS = {key for key, _l, _i in AMENITIES}


class StayUnit(TimestampedModel):
    """Тип размещения. ``quantity`` — сколько идентичных юнитов этого типа
    доступно за ночь (анти-овербукинг пускает, пока занятость ночи < quantity).
    Ferienwohnung/Ferienhaus = 1, «Doppelzimmer ×3» = 3."""

    TYPE_ROOM = "room"
    TYPE_APARTMENT = "apartment"
    TYPE_HOUSE = "house"
    TYPE_BED = "bed"
    TYPE_PITCH = "pitch"
    TYPES = [
        (TYPE_ROOM, "Zimmer"),
        (TYPE_APARTMENT, "Ferienwohnung"),
        (TYPE_HOUSE, "Ferienhaus"),
        (TYPE_BED, "Bett (Schlafsaal)"),
        (TYPE_PITCH, "Stellplatz"),
    ]

    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=TYPES, default=TYPE_ROOM)
    description = models.TextField(blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    # Цена за ночь (центы, брутто; Stripe-native). Итого = ночи × price_cents.
    price_cents = models.PositiveIntegerField(default=0)
    # A5a: цена за ночь в Fr/Sa, если задана (0 = как обычная). Сезонные окна —
    # в SeasonRate (перебивают и базу, и выходные).
    weekend_price_cents = models.PositiveIntegerField(default=0)
    min_nights = models.PositiveSmallIntegerField(default=1)
    max_guests = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    # P2.5b-аналог: депозит за бронь (центы; 0 = без депозита). Анти-no-show.
    deposit_cents = models.PositiveIntegerField(default=0)
    # Даже после оплаты держать бронь pending до ручного подтверждения бизнесом.
    require_manual_confirm = models.BooleanField(default=False)
    # Фото номера: список FileRef-конвертов (как catalog.Product.images):
    # {"id","url","alt","is_primary","sort_order"}. Первое/primary — обложка.
    images = models.JSONField(default=list, blank=True)
    # H3: богатая карточка номера. area_sqm — площадь, м² (0 = не указана);
    # bed_type — свободный текст («Doppelbett», «2 Einzelbetten», «Queensize»);
    # amenities — список ключей из AMENITIES (удобства, иконки на витрине).
    area_sqm = models.PositiveSmallIntegerField(default=0)
    bed_type = models.CharField(max_length=80, blank=True)
    amenities = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def amenity_badges(self) -> list:
        """[(label, icon), …] для активных удобств — в порядке каталога AMENITIES."""
        chosen = set(self.amenities or [])
        return [(label, icon) for key, label, icon in AMENITIES if key in chosen]

    @property
    def image_url(self) -> str:
        """URL обложки (primary или первое фото); пусто, если фото нет."""
        if not self.images:
            return ""
        primary = next((i for i in self.images if i.get("is_primary")), self.images[0])
        return primary.get("url", "")

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100

    @property
    def deposit_eur(self) -> float:
        return self.deposit_cents / 100

    @property
    def weekend_price_eur(self) -> float:
        return self.weekend_price_cents / 100


class RatePlan(TimestampedModel):
    """Тариф (Rate Plan, H1) — альтернативный способ продать те же номера: Basis,
    Nicht-stornierbar, mit Frühstück, Halbpension, Frühbucher, Flexibel. На тенанта
    (применяется ко всем юнитам). Цена = посуточная (база/сезон/выходные) с
    модификатором тарифа ``percent_adjust`` (%) + надбавкой за ночь ``surcharge_cents``
    (напр. завтрак +12 €/ночь). Условия отмены показываем гостю ДО оплаты."""

    MEAL_NONE = "none"
    MEAL_BREAKFAST = "breakfast"
    MEAL_HALF = "half_board"
    MEAL_FULL = "full_board"
    MEALS = [
        (MEAL_NONE, "Ohne Verpflegung"),
        (MEAL_BREAKFAST, "Frühstück"),
        (MEAL_HALF, "Halbpension"),
        (MEAL_FULL, "Vollpension"),
    ]

    CANCEL_FLEXIBLE = "flexible"
    CANCEL_NONREF = "non_refundable"
    CANCELLATIONS = [
        (CANCEL_FLEXIBLE, "Kostenlose Stornierung"),
        (CANCEL_NONREF, "Nicht erstattbar"),
    ]

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    # Модификатор посуточной цены, % со знаком: −10 = тариф дешевле на 10 %,
    # +5 = надбавка. 0 = базовая цена.
    percent_adjust = models.SmallIntegerField(default=0)
    # Надбавка за ночь (центы) — питание/сервис. Складывается после процента.
    surcharge_cents = models.PositiveIntegerField(default=0)
    meal_plan = models.CharField(max_length=20, choices=MEALS, default=MEAL_NONE)
    cancellation = models.CharField(max_length=20, choices=CANCELLATIONS, default=CANCEL_FLEXIBLE)
    # Бесплатная отмена до N дней до заезда (для flexible; 0 = до дня заезда).
    free_cancel_days = models.PositiveSmallIntegerField(default=0)
    # G7: предоплата по тарифу, % от итога (0 = без предоплаты / оплата на месте;
    # 100 = полная Vorkasse). Если задан и подключён Stripe Connect — гость платит
    # этот % онлайн при брони. 0 → фолбэк на депозит юнита (E4), если он задан.
    prepayment_percent = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def meal_included(self) -> bool:
        return self.meal_plan != self.MEAL_NONE

    @property
    def surcharge_eur(self) -> float:
        return self.surcharge_cents / 100


class SeasonRate(TimestampedModel):
    """Сезонный тариф юнита (A5a): цена за ночь на диапазон дат [start, end]
    включительно. Перебивает базовую и выходную цену. Окна не должны
    пересекаться (гард — на стороне кабинета); при пересечении берётся первое."""

    unit = models.ForeignKey(StayUnit, on_delete=models.CASCADE, related_name="season_rates")
    label = models.CharField(max_length=120, blank=True)  # «Hochsaison», «Weihnachten»
    start_date = models.DateField()
    end_date = models.DateField()  # включительно
    price_cents = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.unit}: {self.start_date}–{self.end_date}"

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100


class UnitBlock(TimestampedModel):
    """Блокировка дат юнита (ремонт/своё проживание/Wartung). Занимает ночи
    ``[start_date, end_date]`` ВКЛЮЧИТЕЛЬНО — считается как занятость при подборе
    (в отличие от брони, где departure — день выезда, уже свободный)."""

    unit = models.ForeignKey(StayUnit, on_delete=models.CASCADE, related_name="blocks")
    start_date = models.DateField()
    end_date = models.DateField()  # последняя заблокированная ночь (включительно)
    reason = models.CharField(max_length=120, blank=True)
    # A5b: источник блока. "" = ручной; иначе pk ICalSource (импортированные блоки
    # пересоздаются при синке, ручные не трогаем).
    source_id_ref = models.CharField(max_length=40, blank=True, db_index=True)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.unit}: {self.start_date}–{self.end_date}"


class StayBooking(TimestampedModel):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_NO_SHOW = "no_show"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_NO_SHOW, "No-show"),
    ]
    # Статусы, занимающие ночи (пересечения считаем только по ним).
    ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED)

    unit = models.ForeignKey(StayUnit, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="stays")
    reference_code = models.CharField(max_length=12, unique=True)  # "S-XXXXXX"
    arrival = models.DateField()
    departure = models.DateField()
    guests = models.PositiveSmallIntegerField(default=1)  # итого (adults + children)
    # G5: число забронированных номеров этого типа в одной брони (семьи/группы).
    # Бронь занимает ``rooms`` из quantity на каждую ночь; цена/депозит × rooms.
    rooms = models.PositiveSmallIntegerField(default=1)
    # H5: разбивка гостей (вместимость = adults + children ≤ max_guests). guests
    # держим как итог для совместимости; adults/children — для Kurtaxe и отображения.
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    # Напоминание перед заездом (beat, E3): чтобы слать ровно одно.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    # G2: post-stay письмо (благодарность + запрос отзыва) после выезда — ровно одно.
    post_stay_sent_at = models.DateTimeField(null=True, blank=True)
    # Снимок цены за ночь (центы) на момент брони — цена юнита может меняться.
    price_cents = models.PositiveIntegerField(default=0)
    # Снимок ИТОГА (центы) — с учётом сезонных/выходных тарифов (A5a). Считается
    # в services.book_stay/move_stay (pricing.quote_total); finance берёт его.
    total_cents = models.PositiveIntegerField(default=0)
    # #7: снимок выбранных Extras (Frühstück/Parkplatz …): [{label, price_cents}].
    # Сумма уже включена в total_cents. Переживает изменение/удаление Extra.
    extras = models.JSONField(default=list, blank=True)
    # H1: выбранный тариф (для статистики; SET_NULL — тариф можно удалить).
    rate_plan = models.ForeignKey(
        "RatePlan", null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    # H1: снимок тарифа на момент брони — переживает удаление/правку RatePlan и
    # несёт модификаторы для пересчёта при переносе (move_stay). Ключи: name,
    # meal_plan/meal_label, cancellation/cancellation_label, free_cancel_days,
    # percent_adjust, surcharge_cents. Сумма уже в total_cents.
    rate_snapshot = models.JSONField(default=dict, blank=True)

    # P2.5b/c reuse: депозит/предоплата через Stripe Connect (деньги → бизнесу).
    PAYMENT_NONE = "none"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_NONE, "None"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]
    deposit_cents = models.PositiveIntegerField(default=0)  # снимок с юнита
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_NONE)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # для refund
    # A5: выставленная Rechnung (finance.Invoice.id) — гард от двойного счёта.
    invoice_id = models.UUIDField(null=True, blank=True)
    # H9: снимок Kurtaxe (курортный сбор) на бронь, центы. Уже включён в total_cents;
    # хранится отдельно для отдельной строки счёта (часто без 7 % Beherbergung-НДС).
    kurtaxe_cents = models.PositiveIntegerField(default=0)
    # H4a: применённый промокод (Voucher) — снимок кода и суммы скидки (центы).
    # Скидка уже вычтена из total_cents; снимок переживает изменение/удаление ваучера.
    voucher_code = models.CharField(max_length=12, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)
    # G4: авто-скидка (LOS / Frühbucher / Last-Minute) на проживание — снимок суммы
    # (центы) и подписи. Уже вычтена из total_cents; считается в services по датам/
    # сроку до заезда и настройкам StaySettings. Отдельно от промокода (стыкуется).
    auto_discount_cents = models.PositiveIntegerField(default=0)
    auto_discount_label = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["arrival"]
        indexes = [
            # Поиск пересечений по юниту/дате и календарь загрузки.
            models.Index(fields=["unit", "arrival"], name="stay_unit_arrival_idx"),
            models.Index(fields=["status", "arrival"], name="stay_status_arrival_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.unit} {self.arrival:%d.%m}–{self.departure:%d.%m}"

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days

    @property
    def total_eur(self):
        from decimal import Decimal

        return Decimal(self.total_cents) / 100

    @property
    def kurtaxe_eur(self):
        from decimal import Decimal

        return Decimal(self.kurtaxe_cents) / 100

    @property
    def discount_eur(self):
        from decimal import Decimal

        return Decimal(self.discount_cents) / 100

    @property
    def auto_discount_eur(self):
        from decimal import Decimal

        return Decimal(self.auto_discount_cents) / 100


class ICalSource(TimestampedModel):
    """Внешний iCal-фид (Booking.com/Airbnb) для юнита (A5b). Синк заводит блоки
    на занятые диапазоны (UnitBlock с source_id_ref=pk), анти-двойная-бронь."""

    unit = models.ForeignKey(StayUnit, on_delete=models.CASCADE, related_name="ical_sources")
    label = models.CharField(max_length=80, blank=True)  # «Booking.com», «Airbnb»
    url = models.URLField(max_length=500)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.unit}: {self.label or self.url}"


class StaySettings(TimestampedModel):
    """Настройки размещения на тенанта (H9) — синглтон в схеме тенанта.

    Kurtaxe/Tourismusabgabe: сбор за взрослого за ночь (центы; 0 = выключено). Дети
    по умолчанию бесплатно (малый отель — без возрастных сеток). Сумма брони =
    adults × nights × kurtaxe_cents."""

    kurtaxe_cents = models.PositiveIntegerField(default=0)
    kurtaxe_label = models.CharField(max_length=80, default="Kurtaxe")
    kurtaxe_children_free = models.BooleanField(default=True)
    # H6: Hausordnung / правила проживания (свободный текст; пусто = страницы нет).
    house_rules = models.TextField(blank=True)
    # G4: авто-скидки на проживание — список правил (несколько на тип, многоступенчато).
    # Правило: {"kind": los|early_bird|last_minute, "threshold": int, "percent": int}.
    #   los: ночей ≥ threshold; early_bird: до заезда ≥ threshold дней;
    #   last_minute: до заезда ≤ threshold дней. Применяется к проживанию (без
    #   Extras/Kurtaxe); из подходящих берётся максимальный процент (не суммируются).
    auto_discount_rules = models.JSONField(default=list, blank=True)

    KIND_LOS = "los"
    KIND_EARLY = "early_bird"
    KIND_LAST = "last_minute"
    AUTO_DISCOUNT_KINDS = [
        (KIND_LOS, "Langzeit (ab N Nächten)"),
        (KIND_EARLY, "Frühbucher (ab N Tagen vorher)"),
        (KIND_LAST, "Last-Minute (bis N Tage vorher)"),
    ]

    def clean_auto_rules(self) -> list[dict]:
        """Очищенный список правил авто-скидок (валидные kind/threshold/percent)."""
        kinds = {k for k, _ in self.AUTO_DISCOUNT_KINDS}
        out = []
        for r in self.auto_discount_rules or []:
            if not isinstance(r, dict) or r.get("kind") not in kinds:
                continue
            try:
                threshold = max(0, int(r.get("threshold", 0)))
                percent = max(0, min(int(r.get("percent", 0)), 90))
            except (TypeError, ValueError):
                continue
            if threshold and percent:
                out.append({"kind": r["kind"], "threshold": threshold, "percent": percent})
        return out

    class Meta:
        verbose_name = "Stay settings"
        verbose_name_plural = "Stay settings"

    def __str__(self):
        return "Stay settings"

    @classmethod
    def load(cls):
        """Единственная строка настроек схемы (создаёт дефолтную при первом обращении)."""
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class GuestRegistration(TimestampedModel):
    """G6: цифровой Meldeschein (Bundesmeldegesetz §29–30) для Online-Checkin.

    Гость заполняет данные ведущего гостя при заезде по подписанной ссылке. По
    закону Meldeschein хранится 1 год после выезда, затем уничтожается — чистит
    beat-задача (tasks.purge_old_registrations). Простая электронная подпись:
    Ф.И.О. печатью + отметка времени и IP (eIDAS «einfache» для онлайн-чек-ина)."""

    booking = models.OneToOneField(
        StayBooking, on_delete=models.CASCADE, related_name="registration"
    )
    last_name = models.CharField(max_length=120)
    first_name = models.CharField(max_length=120)
    birth_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    street = models.CharField(max_length=200, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=80, blank=True)
    # Для иностранных гостей (по §30 BMG) — тип/номер документа, опционально.
    doc_type = models.CharField(max_length=40, blank=True)
    doc_number = models.CharField(max_length=60, blank=True)
    accompanying = models.PositiveSmallIntegerField(default=0)  # Mitreisende
    # Простая подпись: печатное Ф.И.О. + подтверждение, отметка времени/IP.
    signed_name = models.CharField(max_length=200)
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Meldeschein {self.booking.reference_code}"

    @property
    def kurtaxe_eur(self) -> float:
        return self.kurtaxe_cents / 100
