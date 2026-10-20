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
    python manage.py seed_demo_tenants --kit handwerker · catering # → handwerker.<base> (A7: Angebot/Festpreis)
    python manage.py seed_demo_tenants --kit retreat    # → retreat.<base> (events/Tickets)
    python manage.py seed_demo_tenants --kit shop       # → shop.<base> (Retail: варианты/Grundpreis/остаток/Versand)
    python manage.py seed_demo_tenants --kit klingenbrot  # T-8.1 «Nur Aktionen» (Solingen;
                                                          # + ohligser_eck walder_faden wupperhof brueckenblick
                                                          # graefrather_markt; портал → solingen.<base>)
    python manage.py seed_demo_tenants --recreate      # пересоздать
    python manage.py seed_demo_tenants --delete        # удалить демо-тенанты

Несколько китов и группы (2026-10-11) — одной командой:

    python manage.py seed_demo_tenants --list                       # киты и группы
    python manage.py seed_demo_tenants --kit hotel friseur cafe     # или через запятую
    python manage.py seed_demo_tenants --group solingen --recreate  # все демо Золингена
    python manage.py seed_demo_tenants --group solingen-dcc --jobs 3   # волна DCC, 3 параллельно
    python manage.py seed_demo_tenants --group all --recreate       # пересоздать всё

Группы — KIT_GROUPS ниже (solingen, lite, solingen-shops, showcase, food, shop, services,
travel, all). Без ``--recreate`` существующие демо пропускаются (создаются недостающие).
Ошибка одного кита не останавливает остальные — в конце сводка.

Поддомен = kit.subdomain или «<kit>-demo». Долго (миграции схемы на тенант
~1 мин). Демо одноразовы — удаляются дропом схемы.
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.tenants import demo_kits, services
from apps.tenants.models import Domain, Tenant

DEMO_PASSWORD = "demo-12345678"

_FOOD = {"bakery", "butcher", "cafe", "catering", "restaurant", "grocery"}
_SHOP = {"retail", "clothing", "online_shop"}
_SERVICES = {"friseur", "handwerker", "werkstatt", "other"}
_TRAVEL = {"hotel", "events", "tour_operator"}

# Группы китов: имя → (описание, условие). Состав считается по полям кита, поэтому
# новый кит сам попадает в свои группы.
KIT_GROUPS = {
    "all": ("все киты", lambda k: True),
    "solingen": ("все демо Золингена (портал города)", lambda k: k.city == "Solingen"),
    "lite": ("демо «Nur Aktionen»", lambda k: k.profile == "aktionen"),
    "solingen-shops": (
        "Золинген с товарами/услугами (T-8.22)",
        lambda k: k.city == "Solingen" and k.profile != "aktionen",
    ),
    "showcase": ("отраслевые демо (кроме Золингена)", lambda k: k.city != "Solingen"),
    "food": ("еда и гастрономия", lambda k: k.business_type in _FOOD),
    "shop": ("торговля и мода", lambda k: k.business_type in _SHOP),
    "services": ("услуги и ремесло", lambda k: k.business_type in _SERVICES),
    "travel": ("отель, события и туры", lambda k: k.business_type in _TRAVEL),
    # DCC (2026-10-15): киты, собранные генератором demo_city, и по разделам справочника.
    "solingen-dcc": ("Золинген, волна DCC (demo_city)", lambda k: k.origin == "city:solingen"),
}


def _dcc_section_groups() -> dict:
    """`sg:<раздел>` → киты DCC этого раздела (ленивая сборка — реестр разделов из demo_city)."""
    from apps.tenants.demo_city.solingen import SECTIONS

    out = {}
    for mod in SECTIONS:
        keys = {b.key for b in mod.BUSINESSES}
        out[f"sg:{mod.SECTION}"] = (
            f"DCC: раздел {mod.SECTION}",
            lambda k, keys=keys: k.key in keys,
        )
    return out


KIT_GROUPS.update(_dcc_section_groups())


def kits_for_group(name: str) -> list[str]:
    _label, cond = KIT_GROUPS[name]
    return [key for key, kit in demo_kits.KITS.items() if cond(kit)]


def _split(values) -> list[str]:
    """«a b», «a,b», «a, b» — одинаково."""
    if isinstance(values, str):  # call_command(kit="hotel") — строка, не список
        values = [values]
    out: list[str] = []
    for v in values or []:
        out += [x for x in str(v).replace(",", " ").split() if x]
    return out  # витрина публична; логин владельца — для показа кабинета


# T-8.14: демо тематического портала (город и признаки темы).
THEME_PORTAL_CITY_KEY = "solingen"
THEME_PORTAL_TAGS = ("vegan", "vegetarisch", "bio", "regional")


class Command(BaseCommand):
    help = "Создать/обновить отдельные демо-тенанты по китам (apps.tenants.demo_kits)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kit", nargs="+", help="один или несколько китов (пробел или запятая)"
        )
        parser.add_argument(
            "--group",
            nargs="+",
            help=f"группы китов: {', '.join(KIT_GROUPS)}",
        )
        parser.add_argument("--list", action="store_true", help="показать киты и группы")
        parser.add_argument("--recreate", action="store_true", help="пересоздать существующие")
        parser.add_argument("--delete", action="store_true", help="удалить демо-тенанты китов")
        parser.add_argument(
            "--jobs",
            type=int,
            default=1,
            help="DCC: параллельно N китов (каждый — отдельный подпроцесс manage.py; "
            "свои соединения с БД). 1 = последовательно, как раньше.",
        )

    def _keys(self, options) -> list[str]:
        keys = _split(options.get("kit"))
        for group in _split(options.get("group")):
            if group not in KIT_GROUPS:
                self.stderr.write(
                    self.style.ERROR(
                        f"  ✗ неизвестная группа: «{group}». Есть: {', '.join(KIT_GROUPS)}"
                    )
                )
                continue
            keys += kits_for_group(group)
        if not options.get("kit") and not options.get("group"):
            keys = list(demo_kits.KITS)
        return list(dict.fromkeys(keys))  # порядок первого упоминания, без повторов

    def _print_list(self):
        for name, (label, _cond) in KIT_GROUPS.items():
            keys = kits_for_group(name)
            self.stdout.write(f"{name:15} {len(keys):3}  {label}")
            if name != "all":
                self.stdout.write(f"{'':20}{' '.join(keys)}")

    def handle(self, *args, **options):
        if options.get("list"):
            self._print_list()
            return
        keys = self._keys(options)
        done, failed = [], []
        total = len(keys)
        jobs = max(1, int(options.get("jobs") or 1))
        if jobs > 1 and total > 1:
            done, failed = self._seed_parallel(keys, options, jobs)
            self.stdout.write(
                self.style.SUCCESS(f"Готово: {len(done)} из {total}")
                + (self.style.ERROR(f" · ошибки: {', '.join(failed)}") if failed else "")
            )
            return
        for n, key in enumerate(keys, 1):
            if total > 1:
                self.stdout.write(f"[{n}/{total}] {key}")
            try:
                if self._seed_one(key, options):
                    done.append(key)
            except Exception as exc:  # noqa: BLE001 — один кит не останавливает пачку
                failed.append(key)
                self.stderr.write(self.style.ERROR(f"  ✗ {key}: {exc}"))
        if total > 1:
            self.stdout.write(
                self.style.SUCCESS(f"Готово: {len(done)} из {total}")
                + (self.style.ERROR(f" · ошибки: {', '.join(failed)}") if failed else "")
            )

    def _seed_parallel(self, keys, options, jobs):
        """DCC §5.2: по подпроцессу `manage.py seed_demo_tenants --kit X` на кит (не fork —
        у Django/psycopg свои соединения в каждом процессе); вывод с префиксом кита по
        завершении подпроцесса, общая сводка — в родителе. Порталы городов заводит
        каждый подпроцесс сам (идемпотентно, get_or_create)."""
        import subprocess
        import sys
        from concurrent.futures import ThreadPoolExecutor, as_completed

        flags = [f for f in ("--recreate", "--delete") if options.get(f.lstrip("-"))]
        self.stdout.write(
            f"Параллельно (--jobs {jobs}): {len(keys)} китов. Каждый кит — миграция своей "
            f"схемы (1–3 мин), вывод кита печатается по его завершении."
        )
        self.stdout.flush()

        def run(key):
            self.stdout.write(f"[{key}] старт…")
            self.stdout.flush()
            proc = subprocess.run(  # noqa: S603 — argv фиксирован, без shell
                [sys.executable, sys.argv[0], "seed_demo_tenants", "--kit", key, *flags],
                capture_output=True,
                text=True,
                check=False,
            )
            return key, proc.returncode, proc.stdout, proc.stderr

        done, failed = [], []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(run, key) for key in keys]
            for n, fut in enumerate(as_completed(futures), 1):
                key, code, out, err = fut.result()
                for line in (out or "").splitlines():
                    self.stdout.write(f"[{key}] {line}")
                for line in (err or "").splitlines():
                    self.stderr.write(f"[{key}] {line}")
                ok = code == 0 and "✗" not in (out or "") + (err or "")
                (done if ok else failed).append(key)
                self.stdout.write(f"[{n}/{len(keys)}] {key}: {'ok' if ok else 'ошибка'}")
                self.stdout.flush()
        return done, failed

    def _seed_one(self, key, options) -> bool:
        """Один кит. True — что-то сделано (создан/удалён), False — пропущен."""
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
            return False
        slug = demo_kits.KITS[key].subdomain or f"{key}-demo"
        existing = Tenant.objects.filter(slug=slug).first()

        if options["delete"]:
            self._drop(existing, slug)
            return True
        if existing and options["recreate"]:
            self._drop(existing, slug)
            existing = None
        if existing:
            self.stdout.write(f"{slug}: уже есть — пропуск (--recreate для пересоздания)")
            return False

        kit = demo_kits.KITS[key]
        tenant, login_url = services.create_business(
            business_name=kit.label,
            slug=slug,
            business_type=kit.business_type,
            city="Hilden",
            email=f"{slug}@example.com",
            password=DEMO_PASSWORD,
        )
        with schema_context(tenant.schema_name):
            demo_kits.apply_kit(tenant, key)
        # Материализовать листинги в общий пул агрегатора (акции/номера/события).
        from apps.aggregator.tasks import reconcile_schema

        reconcile_schema(tenant.schema_name)
        # H8a: для отеля — вертикальный портал-поиск «Hotelsuche» (свой агрегатор
        # на архетип) поверх KIND_STAY + kind=vertical.
        if key == "hotel":
            self._ensure_hotel_portal()
        # T-8.18: лёгкие демо «Nur Aktionen» — городской портал на нашем субдомене
        # (превью для партнёров: show_demo=True, полоса «Vorschau» на портале).
        kit = demo_kits.KITS[key]
        # DCC: портал города — для ЛЮБОГО кита города из реестра районов (раньше только
        # лёгкие: `--group solingen-dcc` на чистом сервере остался бы без портала).
        from apps.core import districts

        if kit.city and districts.city_key(kit.city):
            self._ensure_city_portal(kit.city)
            if districts.city_key(kit.city) == THEME_PORTAL_CITY_KEY:
                self._ensure_theme_portal(kit.city)
        host = (
            Domain.objects.filter(tenant=tenant, is_primary=True)
            .values_list("domain", flat=True)
            .first()
        )
        self.stdout.write(
            self.style.SUCCESS(f"{slug}: создан → https://{host}/  (login: {login_url})")
        )
        return True

    def _ensure_hotel_portal(self):
        """H8a: вертикальный hotel-портал на ``hotels.<base>`` (идемпотентно).

        Создаёт И `AggregatorPortal`, И строку `Domain(host → public)` — без последней
        django-tenants не знает хост и отдаёт 404 ещё до портального middleware
        (как в `create_portal`; раньше Domain не заводился — отсюда «Not Found»).
        """
        from django.conf import settings
        from django_tenants.utils import get_public_schema_name

        from apps.aggregator.models import AggregatorPortal
        from apps.tenants.models import Domain, Tenant

        base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
        host = f"hotels.{base}"
        _portal, created = AggregatorPortal.objects.get_or_create(
            host=host,
            defaults={
                "kind": AggregatorPortal.KIND_VERTICAL,
                "business_type": "hotel",
                "title": {"de": "Hotels & Pensionen", "en": "Hotels & guesthouses"},
                "tagline": {"de": "Direkt buchen — ohne Provision."},
            },
        )
        # Domain(host → public): нужен django-tenants для роутинга хоста на public-схему.
        public = Tenant.objects.filter(schema_name=get_public_schema_name()).first()
        dom = Domain.objects.filter(domain=host).select_related("tenant").first()
        if public is not None and dom is None:
            Domain.objects.create(domain=host, tenant=public, is_primary=False)
            dom_note = "Domain → public erstellt"
        elif dom is not None and public is not None and dom.tenant_id != public.id:
            dom_note = f"⚠ Domain {host} gehört Tenant {dom.tenant.schema_name} — übersprungen"
        else:
            dom_note = "Domain vorhanden"
        self.stdout.write(
            self.style.SUCCESS(
                f"  hotel-Portal: {'erstellt' if created else 'vorhanden'} · {dom_note} → https://{host}/"
            )
        )

    def _ensure_theme_portal(self, city: str):
        """T-8.14: тематический портал «gesund-<город>.<base>» — vegan/bio/regional.

        Тот же пул, что у портала города, но только предложения с признаками темы
        (`portal_scope`). Превью с демо (show_demo=True), как портал города.
        """
        from django.conf import settings
        from django_tenants.utils import get_public_schema_name

        from apps.aggregator.models import AggregatorPortal
        from apps.core import districts
        from apps.tenants.models import Domain, Tenant

        base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
        key = districts.city_key(city) or city.strip().lower()
        host = f"gesund-{key}.{base}"
        dom = Domain.objects.filter(domain=host).select_related("tenant").first()
        public = Tenant.objects.filter(schema_name=get_public_schema_name()).first()
        if public is None or (dom is not None and dom.tenant_id != public.id):
            self.stdout.write(self.style.WARNING(f"  ⚠ {host}: kein Themenportal"))
            return
        _portal, created = AggregatorPortal.objects.get_or_create(
            host=host,
            defaults={
                "kind": AggregatorPortal.KIND_THEME,
                "city": city,
                "show_demo": True,
                "theme_tags": list(THEME_PORTAL_TAGS),
                "title": {
                    "de": f"Gesund in {city}",
                    "en": f"Healthy in {city}",
                    "ru": f"Здоровое в {city}",
                    "uk": f"Здорове в {city}",
                    "tr": f"{city}'de sağlıklı",
                },
                "tagline": {
                    "de": "Vegan, vegetarisch, bio und regional — aus allen Stadtteilen.",
                    "en": "Vegan, vegetarian, organic and local — from every district.",
                    "ru": "Веганское, вегетарианское, био и местное — из всех районов.",
                    "uk": "Веганське, вегетаріанське, біо та місцеве — з усіх районів.",
                    "tr": "Vegan, vejetaryen, organik ve yerel — tüm semtlerden.",
                },
            },
        )
        if dom is None:
            Domain.objects.create(domain=host, tenant=public, is_primary=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Themenportal: {'erstellt' if created else 'vorhanden'} → https://{host}/"
            )
        )

    def _ensure_city_portal(self, city: str):
        """T-8.18: городской портал ``<город>.<base>`` (идемпотентно, + Domain → public).

        До запуска показывает демо-бизнесы (show_demo=True) с полосой «Vorschau»;
        к запуску — снять «show_demo» в админке портала. Свой домен владельца — позже
        тем же порталом (create_portal / второй хост).
        """
        from django.conf import settings
        from django_tenants.utils import get_public_schema_name

        from apps.aggregator.models import AggregatorPortal
        from apps.core import districts
        from apps.tenants.models import Domain, Tenant

        base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
        key = districts.city_key(city) or city.strip().lower()
        host = f"{key}.{base}"
        dom = Domain.objects.filter(domain=host).select_related("tenant").first()
        public = Tenant.objects.filter(schema_name=get_public_schema_name()).first()
        if dom is not None and public is not None and dom.tenant_id != public.id:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ {host} gehört Tenant {dom.tenant.schema_name} — kein Portal"
                )
            )
            return
        _portal, created = AggregatorPortal.objects.get_or_create(
            host=host,
            defaults={
                "kind": AggregatorPortal.KIND_CITY,
                "city": city,
                "show_demo": True,
                "title": {
                    "de": f"Angebote in {city}",
                    "en": f"Offers in {city}",
                    "ru": f"Предложения в {city}",
                    "uk": f"Пропозиції в {city}",
                    "tr": f"{city} fırsatları",
                },
                "tagline": {
                    "de": "Aktionen, Neuheiten und Angebote aus allen Stadtteilen.",
                    "en": "Deals, new arrivals and offers from every district.",
                    "ru": "Акции, новинки и предложения из всех районов.",
                    "uk": "Акції, новинки та пропозиції з усіх районів.",
                    "tr": "Tüm semtlerden kampanyalar, yenilikler ve teklifler.",
                },
                "intro": {
                    "de": f"Was Geschäfte in {city} heute anbieten — vor Ort abholen, "
                    "reservieren oder anfragen.",
                    "en": f"What shops in {city} offer today — pick up, reserve or ask.",
                    "ru": f"Что сегодня предлагают магазины {city} — забрать, отложить "
                    "или спросить.",
                    "uk": f"Що сьогодні пропонують магазини {city} — забрати, відкласти "
                    "або запитати.",
                    "tr": f"{city} işletmelerinin bugünkü teklifleri — gelip alın, ayırtın "
                    "ya da sorun.",
                },
            },
        )
        if public is None:
            # Без public-тенанта хост некуда привязать — портал есть, но отдаёт 404.
            self.stdout.write(
                self.style.WARNING(f"  ⚠ Public-Tenant fehlt — {host} ohne Domain (404)")
            )
            return
        if dom is None:
            Domain.objects.create(domain=host, tenant=public, is_primary=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Stadtportal: {'erstellt' if created else 'vorhanden'} → https://{host}/"
            )
        )

    def _drop(self, tenant, slug):
        if tenant is None:
            self.stdout.write(f"{slug}: нет — нечего удалять")
            return
        tenant.delete(force_drop=True)  # django-tenants: дроп схемы + каскад Domain
        self.stdout.write(self.style.WARNING(f"{slug}: удалён (схема сброшена)"))
