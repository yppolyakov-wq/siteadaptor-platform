"""FB-33 M2i-5b: старые позиционные переводы вариантов «Art der Veranstaltung» — ключом по
тексту (шаг `deploy.sh` после миграций, до подъёма нового web).

До среза варианты переводились оверлеем `i18n.<язык>.anfrage.event_types` по ПОЗИЦИИ; теперь —
`form_fields.anfrage.event_types_i18n` {вариант: {язык: текст}} (`form_spec`). Команда переносит
старые переводы (ключевой перевод главнее) и чистит `i18n.*.anfrage` — тем же
`form_spec.absorb_legacy_event_i18n`, что и запись вкладки «Felder» и старый POST панели.
Перед записью — снимок ключей в базе (`config_migration`), `--undo` возвращает его, если
настройки с тех пор не меняли. Повтор — 0 изменений. Сбой одного сайта не останавливает
остальные. Позиционное чтение у витрины — ВРЕМЕННЫЙ запасной путь до этого прогона.

`--dry-run` — только отчёт (схем, сайтов с позиционным переводом) и предупреждение: перенос по
позиции неточен у сайтов, где варианты переставляли во вкладке «Felder» (M2i-5) — там перевод
мог уже показываться у чужого варианта; владелец проверяет такие сайты на «ru/en» после.
"""

import copy
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.core import form_spec
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

REASON = "form_i18n_realign"
TOUCHED = ("i18n", "form_fields")
ATTEMPTS = 3
WARNING = (
    "ВНИМАНИЕ: перенос по позиции неточен у сайтов, где варианты «Art der Veranstaltung» "
    "переставляли или удаляли во вкладке «Felder» (M2i-5): перевод мог уже стоять у чужого "
    "варианта. После переноса проверьте выбор события на витрине на других языках."
)


def apply_tenant(tenant_pk, *, dry_run: bool = False) -> str:
    """ "moved" | "would-move" | "none" | "busy" | "rolled-back" для одного сайта."""
    from django.db import OperationalError, transaction

    from apps.core import config_migration as cm

    if cm.rolled_back(tenant_pk, REASON):
        return "rolled-back"
    for _attempt in range(ATTEMPTS):
        row = Tenant.objects.filter(pk=tenant_pk).values_list("site_config", flat=True).first()
        if not isinstance(row, dict) or not form_spec.has_legacy(row):
            return "none"
        new = copy.deepcopy(row)
        form_spec.absorb_legacy_event_i18n(new)
        if dry_run:
            return "would-move"
        try:
            with transaction.atomic():
                written = cm.write_with_snapshot(
                    tenant_pk, row, new, reason=REASON, touched=TOUCHED
                )
        except OperationalError as exc:
            if getattr(exc.__cause__, "pgcode", None) != "55P03":
                raise
            return "busy"
        if written is None:
            continue  # кабинет успел сохранить — считаем заново
        cm.bump(written, label=REASON)
        return "moved"
    return "busy"


class Command(BaseCommand):
    help = "FB-33 M2i-5b: позиционные переводы вариантов формы заявки -> ключом по тексту"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все)")
        parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи")
        parser.add_argument("--undo", action="store_true", help="откат последнего переноса")

    def handle(self, *args, **options):
        from apps.core import config_migration as cm

        if options["schema"] == "public":
            raise CommandError("public — платформа, а не сайт бизнеса")
        if options["undo"] and options["dry_run"]:
            raise CommandError("--undo не поддерживает --dry-run")
        tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if options["schema"]:
            tenants = tenants.filter(schema_name=options["schema"])
            if not tenants.exists():
                raise CommandError(f"нет такого сайта: {options['schema']}")
        counts = {
            "moved": 0,
            "would-move": 0,
            "busy": 0,
            "undone": 0,
            "changed": 0,
            "rolled-back": 0,
        }
        failed, doubtful, total = [], [], 0
        for tenant in tenants.only("pk", "schema_name"):
            total += 1
            try:
                if options["undo"]:
                    result = cm.undo(tenant.pk, reason=REASON, touched=TOUCHED, label=REASON)
                else:
                    result = apply_tenant(tenant.pk, dry_run=options["dry_run"])
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                logger.exception("form_i18n_realign: %s failed", tenant.schema_name)
                failed.append(tenant.schema_name)
                # ревью: в вывод — только тип (текст исключения может нести данные сайта)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}")
                continue
            if result in counts:
                counts[result] += 1
                self.stdout.write(f"{tenant.schema_name}: {result}")
            if result == "would-move" and form_spec.legacy_mismatch(
                Tenant.objects.filter(pk=tenant.pk).values_list("site_config", flat=True).first()
            ):
                doubtful.append(tenant.schema_name)
        if options["dry_run"]:
            self.stdout.write(
                f"Проверка: схем {total}, сайтов с позиционным переводом {counts['would-move']}, "
                f"откачено владельцем {counts['rolled-back']}"
            )
            for name in doubtful:
                self.stderr.write(f"{name}: длина перевода не равна списку вариантов или дубли")
            self.stderr.write(WARNING)
        elif options["undo"]:
            self.stdout.write(f"Откат: сайтов {counts['undone']}, менялись {counts['changed']}")
        else:
            self.stdout.write(
                f"Перенос: схем {total}, сайтов изменено {counts['moved']}, занято "
                f"{counts['busy']}, откачено владельцем {counts['rolled-back']}"
            )
        if failed:
            raise CommandError(f"не обработаны сайты: {', '.join(failed)}")
        if counts["busy"]:
            raise CommandError(f"занято сайтов: {counts['busy']} — повторите команду")
        self.stdout.write(self.style.SUCCESS("Готово"))
