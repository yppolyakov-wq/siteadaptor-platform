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

    # Branding
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default="#000000")

    # Billing (Stripe)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    subscription_status = models.CharField(max_length=20, default="trial")
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_ends_at = models.DateTimeField(null=True, blank=True)

    # Owner contact
    owner_email = models.EmailField(blank=True)
    owner_phone = models.CharField(max_length=30, blank=True)

    # Публичные контакты для витрины (могут отличаться от контактов владельца)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    website_url = models.URLField(blank=True)
    opening_hours = models.TextField(blank=True)  # свободный текст / по строкам
    map_url = models.URLField(blank=True)  # ссылка на карту (Google/OSM)

    # Правовые данные (DACH/EU). Свободный текст имеет приоритет; если пусто —
    # генерируем из структурированных полей (см. *_text()).
    vat_id = models.CharField(max_length=30, blank=True)  # USt-IdNr.
    register_entry = models.CharField(max_length=120, blank=True)  # Handelsregister
    legal_responsible = models.CharField(max_length=200, blank=True)  # Verantwortlich i.S.d.
    impressum = models.TextField(blank=True)
    privacy_policy = models.TextField(blank=True)
    withdrawal_policy = models.TextField(blank=True)

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

    # --- публичные контакты / право (для витрины) -----------------------

    @property
    def public_email(self) -> str:
        return self.contact_email or self.owner_email

    @property
    def public_phone(self) -> str:
        return self.contact_phone or self.owner_phone

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
