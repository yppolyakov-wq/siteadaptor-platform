from django.conf import settings
from django.core.management.base import BaseCommand

from apps.tenants.models import Domain, Tenant

# Базовый домен dev-сервера. Wildcard A-запись *.siteadaptor.de → IP сервера.
# Переопределяется через --base-domain.
DEFAULT_BASE_DOMAIN = "siteadaptor.de"


class Command(BaseCommand):
    help = "Create the public tenant (if missing) and a baeckerei-test tenant in Hilden."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-domain",
            default=DEFAULT_BASE_DOMAIN,
            help=f"Base domain for tenants (default: {DEFAULT_BASE_DOMAIN}).",
        )

    def handle(self, *args, **options):
        base_domain = options["base_domain"]
        port_suffix = ":8000" if settings.DEBUG else ""

        # Public tenant (admin, агрегатор) — должен существовать.
        if not Tenant.objects.filter(schema_name="public").exists():
            public = Tenant(
                schema_name="public",
                name="Public",
                slug="public",
            )
            public.auto_create_schema = False
            public.save()
            Domain.objects.create(
                domain=base_domain,
                tenant=public,
                is_primary=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created public tenant on {base_domain}"))

        # Тестовый tenant
        if not Tenant.objects.filter(schema_name="baeckerei_test").exists():
            tenant = Tenant(
                schema_name="baeckerei_test",
                name="Bäckerei Test",
                slug="baeckerei-test",
                business_type="bakery",
                city="Hilden",
                country="DE",
                default_locale="de",
                enabled_locales=["de", "en"],
                enabled_modules=["catalog", "promotions", "publishing"],
                subscription_status="trial",
            )
            tenant.save()
            tenant_domain = f"baeckerei-test.{base_domain}"
            Domain.objects.create(
                domain=tenant_domain,
                tenant=tenant,
                is_primary=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Created tenant: http://{tenant_domain}{port_suffix}")
            )
        else:
            self.stdout.write("Tenant baeckerei_test already exists, skipping.")
