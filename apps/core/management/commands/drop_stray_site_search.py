"""FB-33 стопка 15 E8c (S14-E8-cleanup): разовая чистка блока «Suche» вне страницы 404.

С стопки 14 E8 `site_search` живёт только на 404 (`siteconfig.banned_blocks`); старые конфиги
с ним на других страницах снимают его при чтении (`normalize`, лог `info` на каждый запрос).
Команда (шаг `deploy.sh` после `form_i18n_realign`) снимает такие блоки из хранимых `sections`
и `page_blocks[<хост>]` — только их: остальные байты конфига не трогаются, `normalize` не
зовётся. Переводы по позиции (`i18n[<язык>]["sections" | "page_blocks"][<хост>][i]`) до замены
списков выравниваются за своими блоками (`realign_block_overlays`, A5 плана) — только у
изменённых списков. Хост, где поиск был единственным, остаётся `[]` (строка «ПУСТО» в выводе).
Каждый сайт — в своей транзакции под `select_for_update`; кэш витрины — после коммита.
Повтор — 0 изменений. `--dry-run` — только отчёт.
"""

import copy
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.tenants import siteconfig
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

REASON = "drop_stray_site_search"
HOME = "home"  # хост `sections` для `banned_blocks`


def _stray(host: str) -> frozenset:
    """Что чистим на хосте: запрещённое там и «только для 404» (блоки с формами на
    подтверждении не наша забота — их по-прежнему снимает normalize)."""
    return siteconfig.banned_blocks(host) & siteconfig.NOT_FOUND_ONLY_BLOCKS


def _strip(items: list, host: str) -> tuple[list, int]:
    banned = _stray(host)
    kept = [
        i
        for i in items
        if not (isinstance(i, dict) and siteconfig.cblock_type(i.get("key")) in banned)
    ]
    return kept, len(items) - len(kept)


def clean(cfg: dict) -> tuple[dict | None, list[tuple[str, int, bool]]]:
    """(новый конфиг | None, [(хост, снято, стал пустым)]). Вход не мутируется."""
    changes = []
    new_sections = None
    sections = cfg.get("sections")
    if isinstance(sections, list):
        kept, dropped = _strip(sections, HOME)
        if dropped:
            new_sections = kept
            changes.append((HOME, dropped, not kept))
    pages = cfg.get("page_blocks")
    new_pages = {}
    if isinstance(pages, dict):
        for host, rows in pages.items():
            if not isinstance(rows, list):
                continue
            kept, dropped = _strip(rows, host)
            if dropped:
                new_pages[host] = kept
                changes.append((host, dropped, not kept))
    if not changes:
        return None, []
    new = copy.deepcopy(cfg)
    _realign(new, new_sections, new_pages)
    if new_sections is not None:
        new["sections"] = new_sections
    for host, rows in new_pages.items():
        new["page_blocks"][host] = rows
    return new, changes


def _realign(new: dict, new_sections, new_pages: dict) -> None:
    """A5: переводы снятых списков — за своими блоками; прочие переводы — байт в байт.

    `realign_block_overlays` пересчитывает все хосты; считаем на копии и переносим только
    изменённые списки, чтобы не переписать переводы хостов, где поиска не было."""
    overlay = new.get("i18n")
    if not isinstance(overlay, dict) or not overlay:
        return
    scratch = copy.deepcopy(new)
    all_pages = None
    if new_pages:
        all_pages = {**new["page_blocks"], **new_pages}
    siteconfig.realign_block_overlays(scratch, new_sections=new_sections, new_page_blocks=all_pages)
    for loc, node in overlay.items():
        done = scratch["i18n"].get(loc)
        if not isinstance(node, dict) or not isinstance(done, dict):
            continue
        if new_sections is not None and isinstance(node.get("sections"), list):
            _put(node, "sections", done.get("sections"))
        if new_pages and isinstance(node.get("page_blocks"), dict):
            done_pages = done.get("page_blocks") or {}
            for host in new_pages:
                if host in node["page_blocks"]:
                    _put(node["page_blocks"], host, done_pages.get(host))
            if not node["page_blocks"]:
                node.pop("page_blocks")


def _put(node: dict, key: str, value) -> None:
    if value:
        node[key] = value
    else:
        node.pop(key, None)


def apply_tenant(tenant_pk, *, dry_run: bool = False) -> tuple[str, list]:
    """("dropped" | "would-drop" | "none" | "busy", изменения) для одного сайта."""
    from django.db import OperationalError, transaction

    from apps.core import config_migration as cm

    if dry_run:
        row = Tenant.objects.filter(pk=tenant_pk).values_list("site_config", flat=True).first()
        _new, changes = clean(row) if isinstance(row, dict) else (None, [])
        return ("would-drop" if changes else "none"), changes
    try:
        with transaction.atomic():
            locked = cm.lock(Tenant, tenant_pk)
            cfg = locked.site_config
            new, changes = clean(cfg) if isinstance(cfg, dict) else (None, [])
            if new is None:
                return "none", []
            # `.update`, а не `save(update_fields=…)`: сигнал SE-5a сбросил бы кэш витрины
            # ДО коммита — гонка, при которой читатель кладёт старый конфиг под новую версию
            Tenant.objects.filter(pk=locked.pk).update(site_config=new)
            schema = locked.schema_name
            transaction.on_commit(lambda: cm.bump(schema, label=REASON))
    except OperationalError as exc:
        if getattr(exc.__cause__, "pgcode", None) != "55P03":
            raise
        return "busy", []
    return "dropped", changes


def _describe(changes) -> str:
    return ", ".join(
        f"{host} -{count}" + (" ПУСТО" if empty else "") for host, count, empty in changes
    )


class Command(BaseCommand):
    help = "FB-33 стопка 15 E8c: снять блок «Suche» (site_search) вне страницы 404"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все)")
        parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи")

    def handle(self, *args, **options):
        if options["schema"] == "public":
            raise CommandError("public — платформа, а не сайт бизнеса")
        tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        if options["schema"]:
            tenants = tenants.filter(schema_name=options["schema"])
            if not tenants.exists():
                raise CommandError(f"нет такого сайта: {options['schema']}")
        counts = {"dropped": 0, "would-drop": 0, "busy": 0, "none": 0}
        failed, total, blocks, empty = [], 0, 0, 0
        for tenant in tenants.only("pk", "schema_name"):
            total += 1
            try:
                result, changes = apply_tenant(tenant.pk, dry_run=options["dry_run"])
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                logger.exception("%s: %s failed", REASON, tenant.schema_name)
                failed.append(tenant.schema_name)
                # в вывод — только тип (текст исключения может нести данные сайта)
                self.stderr.write(f"{tenant.schema_name}: ОШИБКА {type(exc).__name__}")
                continue
            counts[result] += 1
            if result == "busy":
                self.stderr.write(f"{tenant.schema_name}: занято")
            elif changes:
                blocks += sum(c for _h, c, _e in changes)
                empty += sum(1 for _h, _c, e in changes if e)
                self.stdout.write(f"{tenant.schema_name}: {result} {_describe(changes)}")
        if options["dry_run"]:
            self.stdout.write(
                f"Проверка: схем {total}, сайтов к чистке {counts['would-drop']}, "
                f"блоков {blocks}, страниц станет пустыми {empty}"
            )
        else:
            self.stdout.write(
                f"Чистка: схем {total}, сайтов изменено {counts['dropped']}, блоков снято "
                f"{blocks}, страниц пустых {empty}, занято {counts['busy']}"
            )
        if failed:
            raise CommandError(f"не обработаны сайты: {', '.join(failed)}")
        if counts["busy"]:
            raise CommandError(f"занято сайтов: {counts['busy']} — повторите команду")
        self.stdout.write(self.style.SUCCESS("Готово"))
