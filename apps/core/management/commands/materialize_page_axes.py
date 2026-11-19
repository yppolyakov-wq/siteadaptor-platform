"""FB-31.7: перенос прежних кодов шаблонов страниц в строки-оси «Seitenaufbau».

Шаг `deploy.sh` (решение владельца). По всем сайтам (или --schema): для каждой поверхности
вид после переноса сверяется с прежним; не совпал — поверхность не трогается и попадает в
отчёт (SKIP/MISMATCH). Перед записью — снимок настроек в базе (`SiteConfigSnapshot`);
`--undo` возвращает снимок, если настройки с тех пор не меняли. Повтор — 0 изменений.
Сбой одного сайта не останавливает остальные; команда завершается ошибкой со списком.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.core import page_axes_migration as pam
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "FB-31.7: перенести старые коды шаблонов страниц в строки схемы"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все)")
        parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи")
        parser.add_argument("--undo", action="store_true", help="откат последнего переноса")
        parser.add_argument(
            "--residue",
            action="store_true",
            help="B3a: что сменит вид, если старые коды перестать читать (ничего не пишет)",
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
            return self._residue(tenants)
        done = skipped = would = 0
        skipped_sites: list[str] = []
        failed = []
        for tenant in tenants.only("pk", "schema_name"):
            try:
                if options["undo"]:
                    result = pam.undo_tenant(tenant)
                    if result == "undone":
                        self.stdout.write(f"{tenant.schema_name}: undone")
                    elif result == "changed":
                        self.stderr.write(
                            f"{tenant.schema_name}: changed — настройки меняли после переноса, "
                            "откат не выполнен"
                        )
                    done += result == "undone"
                    skipped += result == "changed"
                    continue
                report = pam.apply_tenant(tenant, dry_run=options["dry_run"])
                if report.surfaces and "*" not in report.surfaces:
                    word = {"done": "would-move"} if options["dry_run"] else {}
                    parts = ", ".join(
                        f"{k}={word.get(v, v)}" for k, v in sorted(report.surfaces.items())
                    )
                    self.stdout.write(f"{tenant.schema_name}: {parts}")
                if report.notes:
                    # B1b-2: отвязанные копии (D1), группы без акций, чистка хостов удалённых
                    self.stdout.write(f"{tenant.schema_name}: {'; '.join(report.notes)}")
                done += report.changed and not options["dry_run"]
                would += report.changed and options["dry_run"]
                if report.busy:
                    self.stderr.write(f"{tenant.schema_name}: занят — повтор на следующем деплое")
                if report.mismatches:
                    skipped_sites.append(tenant.schema_name)
                    skipped += 1
                    self.stderr.write(
                        f"{tenant.schema_name}: ПРОПУЩЕНО {', '.join(report.mismatches)} "
                        "(вид изменился бы — оставлено как есть)"
                    )
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                # (в т.ч. lock_timeout: строка занята — повтор на следующем деплое)
                logger.exception("materialize_page_axes: %s failed", tenant.schema_name)
                failed.append(tenant.schema_name)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}: {exc}")
        label = "Откат" if options["undo"] else ("Проверка" if options["dry_run"] else "Перенос")
        if options["dry_run"]:
            self.stdout.write(f"{label}: изменилось бы сайтов {would}, пропущено {skipped}")
        else:
            self.stdout.write(f"{label}: сайтов изменено {done}, пропущено {skipped}")
        if skipped_sites:
            self.stderr.write(
                "ПРОПУЩЕНЫ (вид изменился бы, сайт не тронут): " + ", ".join(skipped_sites)
            )
        if failed:
            raise CommandError(f"не обработаны сайты: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS("Готово"))

    def _residue(self, tenants):
        """B3a: остаток по каждому сайту; итог — строкой `residue: N` (N сайтов с остатком)."""
        from apps.core import page_axes_residue

        dirty = 0
        failed = []
        for tenant in tenants.only("pk", "schema_name", "site_config"):
            try:
                reasons = page_axes_residue.tenant_residue(tenant)
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                logger.exception("materialize_page_axes --residue: %s", tenant.schema_name)
                failed.append(tenant.schema_name)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}: {exc}")
                continue
            if reasons:
                dirty += 1
                self.stderr.write(f"{tenant.schema_name}: ОСТАТОК {', '.join(reasons)}")
        self.stdout.write(f"residue: {dirty + len(failed)}")
        if failed:
            raise CommandError(f"не проверены сайты: {', '.join(failed)}")
