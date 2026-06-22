"""Провижининг отдельных showcase-демо-тенантов по китам (M20 demo).

Каждый кит (apps.tenants.demo_kits) → отдельный демо-сайт на субдомене
``<kit>-demo.<base>`` с полным наполнением (apply_kit). Запуск на сервере:

    python manage.py seed_demo_tenants                 # все киты
    python manage.py seed_demo_tenants --kit restaurant
    python manage.py seed_demo_tenants --kit pranasy    # → pranasy.<base>
    python manage.py seed_demo_tenants --kit hotel      # → hotel.<base> (stays)
    python manage.py seed_demo_tenants --kit aktionsmarkt  # все типы акций
    python manage.py seed_demo_tenants --kit friseur    # → friseur.<base> (booking-услуги)
    python manage.py seed_demo_tenants --kit werkstatt  # → werkstatt.<base> (booking+jobs)
    python manage.py seed_demo_tenants --kit retreat    # → retreat.<base> (events/Tickets)
    python manage.py seed_demo_tenants --kit shop       # → shop.<base> (Retail: варианты/Grundpreis/остаток/Versand)
    python manage.py seed_demo_tenants --recreate      # пересоздать
    python manage.py seed_demo_tenants --delete        # удалить демо-тенанты

Поддомен = kit.subdomain или «<kit>-demo». Долго (миграции схемы на тенант
~1 мин). Демо одноразовы — удаляются дропом схемы.
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.tenants import demo_kits, services
from apps.tenants.models import Domain, Tenant

DEMO_PASSWORD = "demo-12345678"  # витрина публична; логин владельца — для показа кабинета


class Command(BaseCommand):
    help = "Создать/обновить отдельные демо-тенанты по китам (apps.tenants.demo_kits)."

    def add_arguments(self, parser):
        parser.add_argument("--kit", help="ключ одного кита (иначе все)")
        parser.add_argument("--recreate", action="store_true", help="пересоздать существующие")
        parser.add_argument("--delete", action="store_true", help="удалить демо-тенанты китов")

    def handle(self, *args, **options):
        keys = [options["kit"]] if options.get("kit") else list(demo_kits.KITS)
        for key in keys:
            if key not in demo_kits.KITS:
                # Заметное предупреждение: при запуске в Docker частая причина —
                # контейнер на старом образе (нужен ./scripts/deploy.sh single
                # для пересборки) ИЛИ опечатка в ключе. Не теряем среди логов.
                available = ", ".join(demo_kits.KITS)
                self.stderr.write(
                    self.style.ERROR(
                        f"\n  ✗ Unbekannter Kit: «{key}» — wird übersprungen.\n"
                        f"    Verfügbare Kits: {available}\n"
                        f"    Fehlt Ihr Kit? Der Container läuft evtl. auf einem alten "
                        f"Image — erst neu bauen:\n"
                        f"      ./scripts/deploy.sh single   "
                        f"(git pull + docker compose build + up -d)\n"
                    )
                )
                continue
            slug = demo_kits.KITS[key].subdomain or f"{key}-demo"
            existing = Tenant.objects.filter(slug=slug).first()

            if options["delete"]:
                self._drop(existing, slug)
                continue
            if existing and options["recreate"]:
                self._drop(existing, slug)
                existing = None
            if existing:
                self.stdout.write(f"{slug}: уже есть — пропуск (--recreate для пересоздания)")
                continue

            kit = demo_kits.KITS[key]
            tenant, login_url = services.create_business(
                business_name=kit.label,
                slug=slug,
                business_type=kit.business_type,
                city="Hilden",
                email=f"{slug}@example.de",
                password=DEMO_PASSWORD,
            )
            with schema_context(tenant.schema_name):
                demo_kits.apply_kit(tenant, key)
            host = (
                Domain.objects.filter(tenant=tenant, is_primary=True)
                .values_list("domain", flat=True)
                .first()
            )
            self.stdout.write(
                self.style.SUCCESS(f"{slug}: создан → https://{host}/  (login: {login_url})")
            )

    def _drop(self, tenant, slug):
        if tenant is None:
            self.stdout.write(f"{slug}: нет — нечего удалять")
            return
        tenant.delete(force_drop=True)  # django-tenants: дроп схемы + каскад Domain
        self.stdout.write(self.style.WARNING(f"{slug}: удалён (схема сброшена)"))
