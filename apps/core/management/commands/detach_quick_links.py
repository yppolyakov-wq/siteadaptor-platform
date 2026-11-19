"""FB-33 M2c-2: «Быстрые ссылки» из баннера главной — в отдельный блок (шаг `deploy.sh`).

По всем сайтам (или --schema). Набор-ссылки → блок «Schnellzugriff» сразу после баннера
(у «Bento» — скрытым); форма дат → секция «Suche»; топ услуг → секция или список из трёх.
Перед записью — снимок настроек в базе; `--undo` возвращает его, если настройки с тех пор не
меняли. Повтор — 0 изменений. Сбой одного сайта не останавливает остальные.
Порядок откатов: этот перенос идёт ПОСЛЕ `materialize_page_axes` — откатывать сначала его.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.core import quick_links_migration as qlm
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "FB-33 M2c: плитки баннера главной -> отдельный блок «Schnellzugriff»"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все)")
        parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи")
        parser.add_argument("--undo", action="store_true", help="откат последнего переноса")
        parser.add_argument(
            "--residue", action="store_true", help="у скольких сайтов ещё остался hero_widget"
        )

    def handle(self, *args, **options):
        if options["schema"] == "public":
            raise CommandError("public — платформа, а не сайт бизнеса")
        tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if options["schema"]:
            tenants = tenants.filter(schema_name=options["schema"])
            if not tenants.exists():
                raise CommandError(f"нет такого сайта: {options['schema']}")
        if options["residue"]:
            left = [
                t.schema_name for t in tenants.only("schema_name", "site_config") if qlm.residue(t)
            ]
            for name in left:
                self.stderr.write(f"{name}: ОСТАТОК hero_widget")
            self.stdout.write(f"quick_links residue: {len(left)}")
            return
        done = skipped = busy = nothing = 0
        failed = []
        for tenant in tenants.only("pk", "schema_name"):
            try:
                if options["undo"]:
                    result = qlm.undo_tenant(tenant)
                    if result == "undone":
                        done += 1
                        self.stdout.write(f"{tenant.schema_name}: undone")
                    elif result == "none":
                        nothing += 1
                    elif result == "changed":
                        skipped += 1
                        self.stderr.write(
                            f"{tenant.schema_name}: changed — настройки меняли после переноса, "
                            "откат не выполнен"
                        )
                    continue
                result = qlm.apply_tenant(tenant, dry_run=options["dry_run"])
                if result.action.startswith("skip:"):
                    skipped += 1
                    self.stderr.write(
                        f"{tenant.schema_name}: ПРОПУЩЕНО ({result.action[5:]}) — оставлено как есть"
                    )
                elif result.action == qlm.BUSY:
                    busy += 1
                    self.stderr.write(f"{tenant.schema_name}: занят — повтор на следующем деплое")
                elif result.changed:
                    done += 1
                    verb = "would-move" if options["dry_run"] else "moved"
                    self.stdout.write(f"{tenant.schema_name}: {verb} ({result.action})")
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                logger.exception("detach_quick_links: %s failed", tenant.schema_name)
                failed.append(tenant.schema_name)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}: {exc}")
        label = "Откат" if options["undo"] else ("Проверка" if options["dry_run"] else "Перенос")
        self.stdout.write(
            f"{label}: сайтов {'изменилось бы' if options['dry_run'] else 'изменено'} {done}, "
            f"пропущено {skipped}, занято {busy}"
            + (f", нечего откатывать {nothing}" if options["undo"] else "")
        )
        if failed:
            raise CommandError(f"не обработаны сайты: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS("Готово"))
