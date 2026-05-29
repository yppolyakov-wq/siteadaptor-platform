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


class Domain(DomainMixin):
    pass
