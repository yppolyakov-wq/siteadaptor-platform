from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    BUSINESS_TYPES = [
        ("bakery", "Bakery / Bäckerei"),
        ("butcher", "Butcher / Metzgerei"),
        ("grocery", "Grocery / Lebensmittel"),
        ("clothing", "Clothing / Bekleidung"),
        ("restaurant", "Restaurant"),
        ("cafe", "Cafe"),
        ("retail", "Retail / Einzelhandel"),
        ("tour_operator", "Tour Operator"),
        ("hotel", "Hotel"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES, default="other")

    # Location
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default="DE")
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Localization
    default_locale = models.CharField(max_length=10, default="de")
    enabled_locales = models.JSONField(default=list)  # ['de', 'en']
    default_currency = models.CharField(max_length=3, default="EUR")
    timezone = models.CharField(max_length=50, default="Europe/Berlin")

    # Region (multi-region future-proofing)
    data_region = models.CharField(max_length=10, default="EU")

    # Modules (для billing tiers)
    enabled_modules = models.JSONField(default=list)
    # ['catalog', 'promotions', 'publishing', 'aggregator']
    # Выбор владельца (Track D / D0a): какие модули он сам выключил. Храним
    # «выключенное», а не «включённое» — новый модуль реестра появляется у всех
    # без правки каждого тенанта. Формула активности — apps.core.modules.
    disabled_modules = models.JSONField(default=list, blank=True)

    # Branding
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default="#000000")

    # Billing (Stripe)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    subscription_status = models.CharField(max_length=20, default="trial")
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_ends_at = models.DateTimeField(null=True, blank=True)

    # P2.5 Stripe Connect: connected account бизнеса (Standard, OAuth) для приёма
    # оплаты от его клиентов напрямую. payments_enabled = charges_enabled (ставит
    # вебхук account.updated). application fee — apps.billing.connect (пока 0).
    stripe_connect_id = models.CharField(max_length=100, blank=True)
    payments_enabled = models.BooleanField(default=False)
    # P2.5c: онлайн-предоплата Click&Collect (иначе — оплата при получении).
    orders_prepay = models.BooleanField(default=False)

    # G4: доставка/Versand для заказов (иначе только самовывоз). Плоский тариф +
    # бесплатно-от + Mindestbestellwert + текст зоны.
    delivery_enabled = models.BooleanField(default=False)
    delivery_fee_cents = models.PositiveIntegerField(default=0)  # плоский тариф
    delivery_free_cents = models.PositiveIntegerField(default=0)  # бесплатно от суммы; 0=нет
    delivery_min_cents = models.PositiveIntegerField(default=0)  # мин. сумма заказа; 0=нет
    delivery_area = models.TextField(blank=True)  # зона/PLZ — текст для клиента
    # A2a: зоны по PLZ — переопределяют плоский тариф для совпавшего индекса.
    # [{"plz": "40,41", "fee_cents": int, "free_cents": int, "min_cents": int}]
    delivery_zones = models.JSONField(default=list, blank=True)
    # Доставлять только в перечисленные зоны (иначе зоны лишь уточняют тариф).
    delivery_restrict_to_zones = models.BooleanField(default=False)
    # Отдельный Mindestbestellwert для самовывоза (0=нет).
    pickup_min_cents = models.PositiveIntegerField(default=0)

    # Owner contact
    owner_email = models.EmailField(blank=True)
    owner_phone = models.CharField(max_length=30, blank=True)

    # Публичные контакты для витрины (могут отличаться от контактов владельца)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    website_url = models.URLField(blank=True)
    opening_hours = models.TextField(blank=True)  # свободный текст / по строкам
    # Структурные часы работы (P1b): {"0":["09:00","18:00"], …} по дням недели
    # (0=Пн … 6=Вс, как date.weekday()); один интервал на день в v1. Источник
    # для live-статуса «Jetzt geöffnet» и JSON-LD openingHoursSpecification.
    opening_hours_structured = models.JSONField(default=dict, blank=True)
    map_url = models.URLField(blank=True)  # ссылка на карту (Google/OSM)

    # Если включено — залогиненный сотрудник, открыв QR-ссылку погашения,
    # гасит бронь/ваучер сразу (без кнопки подтверждения).
    auto_redeem_on_scan = models.BooleanField(default=False)

    # Конструктор витрины v1 (Track C2): порядок/видимость секций главной +
    # тексты hero/about. Схема и нормализация — apps.tenants.siteconfig.
    site_config = models.JSONField(default=dict, blank=True)

    # Правовые данные (DACH/EU). Свободный текст имеет приоритет; если пусто —
    # генерируем из структурированных полей (см. *_text()).
    vat_id = models.CharField(max_length=30, blank=True)  # USt-IdNr.
    # Light-Finance (D4b): Steuernummer (если нет USt-IdNr.) и режим
    # Kleinunternehmer §19 UStG — счета без НДС, с обязательным Hinweis.
    tax_number = models.CharField(max_length=30, blank=True)
    small_business = models.BooleanField(default=False)
    register_entry = models.CharField(max_length=120, blank=True)  # Handelsregister
    legal_responsible = models.CharField(max_length=200, blank=True)  # Verantwortlich i.S.d.
    impressum = models.TextField(blank=True)
    privacy_policy = models.TextField(blank=True)
    withdrawal_policy = models.TextField(blank=True)

    # Фоновый провижининг (создание PG-схемы ~1 мин — выносится в Celery,
    # решение владельца 2026-06-12): pending → ready/failed. Существующие
    # тенанты — ready (default). Витрина/кабинет до ready не работают (схемы
    # ещё нет), страница ожидания — tenants.views.signup_waiting.
    PROVISIONING_PENDING = "pending"
    PROVISIONING_READY = "ready"
    PROVISIONING_FAILED = "failed"
    PROVISIONING_STATUSES = [
        (PROVISIONING_PENDING, "Pending"),
        (PROVISIONING_READY, "Ready"),
        (PROVISIONING_FAILED, "Failed"),
    ]
    provisioning_status = models.CharField(
        max_length=10, choices=PROVISIONING_STATUSES, default=PROVISIONING_READY
    )

    # Meta
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # django-tenants
    auto_create_schema = True
    auto_drop_schema = False  # для безопасности — не удалять автоматически

    class Meta:
        indexes = [
            # Агрегатор: подбор активных арендаторов по городу.
            models.Index(fields=["city", "is_active"], name="tenant_city_active_idx"),
            # Вертикальные порталы (baeckerei.de и т.п.): выборка по типу
            # бизнеса в городе.
            models.Index(fields=["business_type", "city"], name="tenant_btype_city_idx"),
            # Биллинг-cron: «у кого истекает триал / подписка».
            models.Index(
                fields=["subscription_status", "trial_ends_at"],
                name="tenant_substatus_trial_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.schema_name})"

    # --- модули кабинета (Track D / D0a, реестр — apps.core.modules) ------

    def is_module_active(self, key: str) -> bool:
        from apps.core import modules

        return modules.is_module_active(self, key)

    def active_modules(self) -> list:
        from apps.core import modules

        return modules.active_modules(self)

    # --- публичные контакты / право (для витрины) -----------------------

    @property
    def public_email(self) -> str:
        return self.contact_email or self.owner_email

    @property
    def public_phone(self) -> str:
        return self.contact_phone or self.owner_phone

    def open_status(self) -> dict | None:
        """Live-статус «открыто сейчас» из структурных часов (P1b). None — не заданы."""
        from django.utils import timezone

        from . import openinghours

        return openinghours.open_status(self.opening_hours_structured, timezone.localtime())

    def todays_hours(self) -> str:
        from django.utils import timezone

        from . import openinghours

        return openinghours.today_label(self.opening_hours_structured, timezone.localtime())

    def impressum_text(self) -> str:
        """Свободный Impressum или сгенерированный из структурированных полей."""
        if self.impressum.strip():
            return self.impressum
        lines = [self.name]
        if self.address:
            lines.append(self.address)
        if self.public_email:
            lines.append(f"E-Mail: {self.public_email}")
        if self.public_phone:
            lines.append(f"Telefon: {self.public_phone}")
        if self.legal_responsible:
            lines.append(f"Verantwortlich i.S.d. § 18 Abs. 2 MStV: {self.legal_responsible}")
        if self.register_entry:
            lines.append(f"Registereintrag: {self.register_entry}")
        if self.vat_id:
            lines.append(f"USt-IdNr.: {self.vat_id}")
        return "\n".join(lines)

    def privacy_text(self) -> str:
        """Свободная политика конфиденциальности или базовый шаблон (DSGVO)."""
        if self.privacy_policy.strip():
            return self.privacy_policy
        contact = self.public_email or self.name
        return (
            "Datenschutzerklärung\n\n"
            "Verantwortlich für die Datenverarbeitung auf dieser Website ist "
            f"{self.name}.\n\n"
            "Wir verarbeiten personenbezogene Daten (Name, E-Mail, Telefon) "
            "ausschließlich zur Bearbeitung Ihrer Reservierung gemäß Art. 6 Abs. 1 "
            "lit. b DSGVO. Die Daten werden nicht an Dritte weitergegeben und nach "
            "Ablauf der gesetzlichen Fristen gelöscht bzw. anonymisiert.\n\n"
            "Sie haben das Recht auf Auskunft, Berichtigung, Löschung und "
            "Widerspruch. Wenden Sie sich dazu an: "
            f"{contact}.\n\n"
            "Hinweis: Bitte passen Sie diesen Text an Ihr Geschäft an."
        )

    def withdrawal_text(self) -> str:
        """Свободная информация об отмене или базовый шаблон."""
        if self.withdrawal_policy.strip():
            return self.withdrawal_policy
        return (
            "Stornierung / Widerruf\n\n"
            "Eine Reservierung ist unverbindlich und kann jederzeit storniert "
            "werden. Bei Fragen kontaktieren Sie uns bitte unter "
            f"{self.public_email or self.name}.\n\n"
            "Hinweis: Bitte passen Sie diesen Text an Ihr Geschäft an."
        )


class Domain(DomainMixin):
    pass


class CustomDomain(models.Model):
    """Заявка бизнеса на собственный домен (self-service, SHARED/public).

    Жизненный цикл заявки отдельно от django-tenants `Domain`: `Domain` = живой
    роутинг + авторизация TLS (Caddy on-demand), поэтому его строку создаём
    только ПОСЛЕ подтверждения владения (A-запись домена указывает на наш IP —
    см. apps.tenants.domains.verify). Пока pending — домен никуда не маршрутизи-
    руется и сертификат не выпускается, так что чужой домен «занять» нельзя.
    """

    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"
    STATUSES = [(PENDING, "Pending"), (ACTIVE, "Active"), (FAILED, "Failed")]

    domain = models.CharField(max_length=253, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="custom_domains")
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    last_check_error = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.domain} → {self.tenant.schema_name} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status == self.ACTIVE
