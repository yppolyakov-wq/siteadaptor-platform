"""Провижининг мульти-доменного портала (P2.1d).

Портал отвечает по своему хосту только если TenantMainMiddleware резолвит этот
хост на public-схему — для этого нужна строка Domain(host → public tenant).
Команда атомарно создаёт AggregatorPortal + Domain:

    python manage.py create_portal \\
        --host muenchen.siteadaptor.de --kind city --city "München" \\
        --title-de "Angebote München"

DNS/TLS/custom-домены — docs/portal-setup.md.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import get_public_schema_name

from apps.aggregator.models import AggregatorPortal
from apps.tenants.models import Domain, Tenant

_BTYPES = dict(Tenant.BUSINESS_TYPES)


def _i18n(de: str, en: str) -> dict:
    data = {"de": de}
    if en:
        data["en"] = en
    return data


class Command(BaseCommand):
    help = "Создать AggregatorPortal + строку Domain(host → public) для портального хоста."

    def add_arguments(self, parser):
        parser.add_argument("--host", required=True, help="Полный хост портала")
        parser.add_argument(
            "--kind",
            choices=[k for k, _ in AggregatorPortal.KINDS],
            default=AggregatorPortal.KIND_CITY,
        )
        parser.add_argument("--city", default="")
        parser.add_argument("--business-type", dest="business_type", default="")
        parser.add_argument("--title-de", dest="title_de", required=True)
        parser.add_argument("--title-en", dest="title_en", default="")
        parser.add_argument("--tagline-de", dest="tagline_de", default="")
        parser.add_argument("--tagline-en", dest="tagline_en", default="")
        parser.add_argument("--intro-de", dest="intro_de", default="")
        parser.add_argument("--intro-en", dest="intro_en", default="")
        parser.add_argument("--logo-url", dest="logo_url", default="")
        parser.add_argument("--primary-color", dest="primary_color", default="#111827")

    def handle(self, *args, **options):
        host = options["host"].lower().strip()
        kind = options["kind"]
        city = options["city"]
        business_type = options["business_type"]

        if business_type and business_type not in _BTYPES:
            raise CommandError(
                f"Неизвестный --business-type {business_type!r}; допустимо: {', '.join(_BTYPES)}"
            )
        if kind == AggregatorPortal.KIND_CITY and not city:
            raise CommandError("--city обязателен для kind=city")
        if kind == AggregatorPortal.KIND_VERTICAL and not business_type:
            raise CommandError("--business-type обязателен для kind=vertical")
        if kind == AggregatorPortal.KIND_COMBO and not (city and business_type):
            raise CommandError("--city и --business-type обязательны для kind=combo")

        if AggregatorPortal.objects.filter(host=host).exists():
            raise CommandError(f"Портал с хостом {host} уже существует")

        try:
            public = Tenant.objects.get(schema_name=get_public_schema_name())
        except Tenant.DoesNotExist:
            raise CommandError(
                "Public tenant не найден — сначала инициализируйте платформу"
            ) from None

        # Хост мог быть заведён заранее (например, custom-домен) — переиспользуем,
        # но чужой тенант не трогаем: его субдомен нельзя превращать в портал.
        existing_domain = Domain.objects.filter(domain=host).select_related("tenant").first()
        if existing_domain and existing_domain.tenant_id != public.id:
            raise CommandError(
                f"Домен {host} уже привязан к тенанту {existing_domain.tenant.schema_name}"
            )

        with transaction.atomic():
            AggregatorPortal.objects.create(
                host=host,
                kind=kind,
                city=city,
                business_type=business_type,
                title=_i18n(options["title_de"], options["title_en"]),
                tagline=_i18n(options["tagline_de"], options["tagline_en"])
                if options["tagline_de"]
                else {},
                intro=_i18n(options["intro_de"], options["intro_en"])
                if options["intro_de"]
                else {},
                logo_url=options["logo_url"],
                primary_color=options["primary_color"],
            )
            if existing_domain is None:
                Domain.objects.create(domain=host, tenant=public, is_primary=False)

        scope = " ".join(filter(None, [city, business_type])) or "—"
        self.stdout.write(self.style.SUCCESS(f"Portal {host} создан (kind={kind}, {scope})"))
