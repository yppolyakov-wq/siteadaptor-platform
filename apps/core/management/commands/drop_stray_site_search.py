"""FB-33 стопка 15 E8c (S14-E8-cleanup): разовая чистка блока «Suche» вне страницы 404.

С стопки 14 E8 `site_search` живёт только на 404 (`siteconfig.banned_blocks`); старые конфиги
с ним на других страницах снимают его при чтении (`normalize`, лог `info` на каждый запрос).
Команда (шаг `deploy.sh` после `form_i18n_realign`) снимает такие блоки из хранимых `sections`
и `page_blocks[<хост>]` — только их: остальные байты конфига не трогаются, `normalize` не
зовётся. Хост, где поиск был единственным, остаётся `[]` (строка «ПУСТО» в выводе).

Переводы по позиции (`i18n[<язык>]["sections" | "page_blocks"][<хост>][i]`) до замены списков
выравниваются за своими блоками (`realign_block_overlays`, A5 плана) — только у изменённых
списков и только если хранимый список совпадает с нормализованным (тогда позиции переводов
однозначны). Иначе не угадываем: переводы этого списка не трогаем, строка «переводы не
выровнены» в выводе.

Запись — общим писателем переносов `config_migration.write_with_snapshot`: строка под
блокировкой, сверка «настройки не менялись», снимок тронутых ключей (`--undo` возвращает).
Пишем мимо `save()` (`send_signals=False`): кэш витрины сбрасываем сами в `on_commit`,
событие аудита `tenant.site_config_cleanup` — явно в той же транзакции. Повтор — 0 изменений;
`--dry-run` — тот же отчёт без записи. Сбой одного сайта не останавливает остальные.
"""

import copy
import logging
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand, CommandError

from apps.tenants import siteconfig
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

REASON = "drop_stray_site_search"
TOUCHED = ("sections", "page_blocks", "i18n")
ATTEMPTS = 3
HOME = "home"  # хост `sections` для `banned_blocks`
AUDIT_ACTION = "tenant.site_config_cleanup"


@dataclass
class Outcome:
    #: dropped | would-drop | none | busy | gone | rolled-back
    status: str
    changes: list = field(default_factory=list)  # [(хост, снято, стал пустым)]
    malformed: list = field(default_factory=list)  # где форма конфига кривая
    unaligned: list = field(default_factory=list)  # хосты, чьи переводы не выровнены
    cache: list = field(default_factory=list)  # итог сброса кэша (on_commit)


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


def _ids(items) -> list:
    return [siteconfig._item_identity(i, "title") for i in items]


def _aligned(host: str, kept: list) -> bool:
    """Позиции переводов однозначны: нормализованный хранимый список (поиск normalize уже
    снимает) — тот же, что хранимый без поиска; у главной normalize ещё дописывает
    недостающие фикс-секции В КОНЕЦ — позиций выше они не сдвигают."""
    if host == HOME:
        norm = _ids(siteconfig.normalize_sections(kept))
        return norm[: len(kept)] == _ids(kept)
    norm = siteconfig.normalize_page_blocks({host: kept}).get(host) or []
    return _ids(norm) == _ids(kept)


def _translated(overlay: dict, host: str) -> bool:
    """Есть ли у списка хоста переводы хоть в одном языке."""
    for node in overlay.values():
        if not isinstance(node, dict):
            continue
        if host == HOME:
            rows = node.get("sections")
        else:
            pages = node.get("page_blocks")
            rows = pages.get(host) if isinstance(pages, dict) else None
        if isinstance(rows, list) and rows:
            return True
    return False


def clean(cfg) -> tuple[dict | None, list, list, list]:
    """(новый конфиг | None, изменения, кривые места, невыровненные хосты). Вход не мутируется."""
    if not isinstance(cfg, dict):
        return None, [], ["site_config"], []
    changes, malformed = [], []
    new_sections = None
    sections = cfg.get("sections")
    if isinstance(sections, list):
        kept, dropped = _strip(sections, HOME)
        if dropped:
            new_sections = kept
            changes.append((HOME, dropped, not kept))
    elif sections is not None:
        malformed.append("sections")
    pages = cfg.get("page_blocks")
    new_pages = {}
    if isinstance(pages, dict):
        for host, rows in pages.items():
            if not isinstance(rows, list):
                malformed.append(f"page_blocks.{host}")
                continue
            kept, dropped = _strip(rows, host)
            if dropped:
                new_pages[host] = kept
                changes.append((host, dropped, not kept))
    elif pages is not None:
        malformed.append("page_blocks")
    if not changes:
        return None, [], malformed, []
    new = copy.deepcopy(cfg)
    unaligned = _realign(new, new_sections, new_pages)
    if new_sections is not None:
        new["sections"] = new_sections
    for host, rows in new_pages.items():
        new["page_blocks"][host] = rows
    return new, changes, malformed, unaligned


def _realign(new: dict, new_sections, new_pages: dict) -> list:
    """A5: переводы снятых списков — за своими блоками; прочие переводы — байт в байт.
    Возвращает хосты с переводами, которые однозначно выровнять нельзя (их не трогаем).

    `realign_block_overlays` пересчитывает все хосты; считаем на копии и переносим только
    изменённые и однозначные списки."""
    overlay = new.get("i18n")
    if not isinstance(overlay, dict) or not overlay:
        return []
    unaligned = []
    home_ok = new_sections is not None and _aligned(HOME, new_sections)
    if new_sections is not None and not home_ok and _translated(overlay, HOME):
        unaligned.append(HOME)
    hosts_ok = []
    for host, kept in new_pages.items():
        if _aligned(host, kept):
            hosts_ok.append(host)
        elif _translated(overlay, host):
            unaligned.append(host)
    scratch = copy.deepcopy(new)
    all_pages = {**new["page_blocks"], **new_pages} if hosts_ok else None
    siteconfig.realign_block_overlays(
        scratch, new_sections=new_sections if home_ok else None, new_page_blocks=all_pages
    )
    for loc, node in overlay.items():
        done = scratch["i18n"].get(loc)
        if not isinstance(node, dict) or not isinstance(done, dict):
            continue
        if home_ok and isinstance(node.get("sections"), list):
            _put(node, "sections", done.get("sections"))
        if hosts_ok and isinstance(node.get("page_blocks"), dict):
            done_pages = done.get("page_blocks") or {}
            for host in hosts_ok:
                if host in node["page_blocks"]:
                    _put(node["page_blocks"], host, done_pages.get(host))
            if not node["page_blocks"]:
                node.pop("page_blocks")
    return unaligned


def _put(node: dict, key: str, value) -> None:
    if value:
        node[key] = value
    else:
        node.pop(key, None)


def apply_tenant(tenant_pk, *, dry_run: bool = False) -> Outcome:
    """Чистка одного сайта (`Outcome.status` — см. класс)."""
    from django.db import OperationalError, transaction

    from apps.audit.services import audit_event
    from apps.core import config_migration as cm

    if not dry_run and cm.rolled_back(tenant_pk, REASON):
        return Outcome("rolled-back")
    for _attempt in range(ATTEMPTS):
        row = Tenant.objects.filter(pk=tenant_pk).values("site_config").first()
        if row is None:
            return Outcome("gone")
        before = row["site_config"]
        new, changes, malformed, unaligned = clean(before)
        found = Outcome("none", changes, malformed, unaligned)
        if new is None:
            return found
        found.status = "would-drop"
        if dry_run:
            return found
        try:
            with transaction.atomic():
                written = cm.write_with_snapshot(
                    tenant_pk, before, new, reason=REASON, touched=TOUCHED, send_signals=False
                )
                if written is not None:
                    # запись мимо save(): приёмник аудита `tenant.updated` молчит — своё событие
                    audit_event(
                        action=AUDIT_ACTION,
                        resource_type="tenant",
                        resource_id=tenant_pk,
                        tenant_schema=written,
                        context={"reason": REASON, "hosts": [h for h, _c, _e in changes]},
                    )
                    transaction.on_commit(
                        lambda schema=written, sink=found.cache: sink.append(
                            cm.bump(schema, label=REASON)
                        )
                    )
        except Tenant.DoesNotExist:
            return Outcome("gone")
        except OperationalError as exc:
            if not cm.is_lock_timeout(exc):
                raise
            return Outcome("busy")
        if written is None:
            continue  # кабинет успел сохранить — считаем заново
        found.status = "dropped"
        return found
    return Outcome("busy")


def _describe(changes) -> str:
    return ", ".join(
        f"{host} -{count}" + (" ПУСТО" if empty else "") for host, count, empty in changes
    )


class Command(BaseCommand):
    help = "FB-33 стопка 15 E8c: снять блок «Suche» (site_search) вне страницы 404"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="один сайт (иначе все)")
        parser.add_argument("--dry-run", action="store_true", help="только отчёт, без записи")
        parser.add_argument("--undo", action="store_true", help="откат последней чистки")

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
        if options["undo"]:
            self._undo(tenants, cm)
            return
        dry = options["dry_run"]
        keys = ("sites", "blocks", "empty", "unaligned", "malformed", "gone", "busy", "rb", "cache")
        n = dict.fromkeys(keys, 0)
        failed, total = [], 0
        for tenant in tenants.only("pk", "schema_name"):
            total += 1
            name = tenant.schema_name
            try:
                out = apply_tenant(tenant.pk, dry_run=dry)
            except Exception as exc:  # noqa: BLE001 — один сайт не останавливает остальные
                logger.exception("%s: %s failed", REASON, name)
                failed.append(name)
                # в вывод — только тип (текст исключения может нести данные сайта)
                self.stderr.write(f"{name}: ОШИБКА {type(exc).__name__}")
                continue
            self._report(name, out, n)
        self.stdout.write(
            f"{'Проверка' if dry else 'Чистка'}: схем {total}, сайтов с чисткой {n['sites']}, "
            f"блоков {n['blocks']}, страниц пустых {n['empty']}, переводов не выровнено "
            f"{n['unaligned']}, с ошибкой формы {n['malformed']}, исчезли {n['gone']}, занято "
            f"{n['busy']}, откачено владельцем {n['rb']}, кэш не сброшен {n['cache']}"
        )
        if failed:
            raise CommandError(f"не обработаны сайты: {', '.join(failed)}")
        if n["busy"]:
            raise CommandError(f"занято сайтов: {n['busy']} — повторите команду")
        if n["cache"]:
            raise CommandError(
                f"кэш витрины не сброшен у сайтов: {n['cache']} — данные записаны; витрина "
                "обновится по TTL кэша или после сохранения настроек сайта"
            )
        self.stdout.write(self.style.SUCCESS("Готово"))

    def _report(self, name: str, out: Outcome, n: dict) -> None:
        if out.malformed:
            n["malformed"] += 1
            self.stdout.write(f"{name}: ошибка формы: {', '.join(out.malformed)}")
        if out.status == "busy":
            n["busy"] += 1
            self.stderr.write(f"{name}: занято")
        elif out.status == "gone":
            n["gone"] += 1
            self.stdout.write(f"{name}: gone")
        elif out.status == "rolled-back":
            n["rb"] += 1
        elif out.status in ("dropped", "would-drop"):
            n["sites"] += 1
            n["blocks"] += sum(c for _h, c, _e in out.changes)
            n["empty"] += sum(1 for _h, _c, e in out.changes if e)
            self.stdout.write(f"{name}: {out.status} {_describe(out.changes)}")
            if out.unaligned:
                n["unaligned"] += 1
                self.stdout.write(f"{name}: переводы не выровнены: {', '.join(out.unaligned)}")
            if out.cache and not all(out.cache):
                n["cache"] += 1
                self.stderr.write(f"{name}: кэш витрины не сброшен")

    def _undo(self, tenants, cm) -> None:
        counts = {"undone": 0, "changed": 0, "none": 0}
        for tenant in tenants.only("pk", "schema_name"):
            result = cm.undo(tenant.pk, reason=REASON, touched=TOUCHED, label=REASON)
            counts[result] = counts.get(result, 0) + 1
            if result != "none":
                self.stdout.write(f"{tenant.schema_name}: {result}")
        self.stdout.write(f"Откат: сайтов {counts['undone']}, менялись {counts['changed']}")
        self.stdout.write(self.style.SUCCESS("Готово"))
