"""FB-31.7: перенос прежних кодов шаблонов страниц в строки-оси схемы «Seitenaufbau»
(`docs/fb31-7-materialize-plan-2026-11-16.md`).

Каждая поверхность переносится независимо и проверяется: вид страницы, вычисленный по
строкам БЕЗ кода, обязан совпасть с прежним видом (код + строки). Не совпал или перенос
невозможен (скрытая строка, которую сейчас заменяет код) — поверхность не трогается и
попадает в отчёт (решение владельца: допуск расхождений — ноль). Старые ключи остаются до
следующего релиза (решение владельца), поэтому витрина до сноса чтения кода видит то же.

Модуль чистый (без БД): на входе сырой `site_config`, на выходе новый и отчёт.
Срез B1a — девять страниц-списков (`page_styles`); остальные поверхности — следующими.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

#: итог одной поверхности
DONE, SAME, SKIP, MISMATCH = "done", "same", "skip", "mismatch"


@dataclass
class Report:
    surfaces: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return any(v == DONE for v in self.surfaces.values())

    @property
    def mismatches(self) -> list[str]:
        return [k for k, v in self.surfaces.items() if v in (SKIP, MISMATCH)]

    @property
    def busy(self) -> bool:
        return any(v == "busy" for v in self.surfaces.values())


def _listing_code(cfg: dict, surface: str) -> str:
    styles = cfg.get("page_styles") if isinstance(cfg, dict) else None
    code = styles.get(surface, "") if isinstance(styles, dict) else ""
    return code if isinstance(code, str) else ""


def _view(norm: dict, surface: str, host: str) -> tuple:
    """Всё, что видит посетитель от строк хоста листинга (ревью silent-failure B1a): свои
    блоки над и под ★, композиция страницы при всех гейтах данных (есть подразделы / нет,
    есть фото / нет), переводы своих блоков на каждом языке."""
    from apps.core import listing_composition
    from apps.tenants import siteconfig

    rows = (norm.get("page_blocks") or {}).get(host) or []
    above, below = siteconfig.split_at_main(rows)
    own = (
        tuple(r.get("id") for r in above if isinstance(r, dict) and r.get("id")),
        tuple(r.get("id") for r in below if isinstance(r, dict) and r.get("id")),
    )
    entry = [{"label": "x", "url": "?k=x", "active": False, "count": 1}]
    shelf = [{"label": "x", "slug": "x", "url": "?k=x", "total": 1, "items": []}]
    comps = []
    for entries in ([], entry):
        for photo in ("/media/x.jpg", ""):
            comps.append(
                listing_composition.context(
                    norm,
                    surface,
                    entries=entries,
                    shelves=shelf,
                    hero={"eyebrow": "", "text": "", "photo": photo},
                    carry="k",
                    kind="service",
                )
            )
    langs = []
    for loc in sorted((norm.get("i18n") or {}) if isinstance(norm.get("i18n"), dict) else {}):
        loc_rows = (siteconfig.localize(norm, loc).get("page_blocks") or {}).get(host) or []
        langs.append(
            (loc, tuple((r.get("id"), repr(r.get("data"))) for r in loc_rows if r.get("id")))
        )
    return own, repr(comps), tuple(langs)


def migrate_listings(raw: dict) -> tuple[dict, Report]:
    """Коды девяти листингов (`page_styles[surface]`) → строки хоста листинга. Сайт
    переносится целиком или не трогается (решение владельца: при любом расхождении)."""
    from apps.core import listing_parts
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    report = Report()
    src = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(src)
    for surface in sorted(listing_parts.LISTINGS):
        norm = siteconfig.normalize(out)
        code = _listing_code(norm, surface)
        if not code:
            continue
        s = listing_parts.LISTINGS[surface]
        host = listing_parts.HOST_OF[surface]
        before = listing_parts.effective(norm, surface)
        rows = (norm.get("page_blocks") or {}).get(host) or []
        if pp.effective(s, norm, host) == before:
            report.surfaces[surface] = SAME  # строки уже задают тот же вид
            continue
        new_rows = pp.materialize_rows(s, rows, code)
        if new_rows is None:
            report.surfaces[surface] = SKIP
            continue
        blocks = copy.deepcopy(norm.get("page_blocks") or {})
        blocks[host] = new_rows
        # переводы блоков лежат по позициям — едут за своими блоками (как в «Seitenaufbau»)
        aligned = copy.deepcopy(norm)
        siteconfig.realign_block_overlays(aligned, new_page_blocks=blocks)
        candidate = copy.deepcopy(out)
        candidate["page_blocks"] = blocks
        if "i18n" in aligned:
            candidate["i18n"] = aligned["i18n"]
        after = siteconfig.normalize(candidate)
        no_code = copy.deepcopy(after)
        styles = dict(no_code.get("page_styles") or {})
        styles.pop(surface, None)
        no_code["page_styles"] = styles
        if (
            pp.effective(s, after, host) != before
            or listing_parts.effective(after, surface) != before
            or _view(no_code, surface, host) != _view(norm, surface, host)
            or _view(after, surface, host) != _view(norm, surface, host)
        ):
            report.surfaces[surface] = MISMATCH
            continue
        out = candidate
        report.surfaces[surface] = DONE
    if report.mismatches:
        return copy.deepcopy(src), report  # сайт не трогается целиком
    return out, report


def migrate(raw: dict) -> tuple[dict, Report]:
    """Все перенесённые поверхности (B1a — листинги)."""
    return migrate_listings(raw)


# ───────── запись в базу (команда `materialize_page_axes`) ─────────

REASON = "fb31.7-page-axes"
#: ключи настроек, которые меняет перенос (их и хранит снимок)
_TOUCHED = ("page_blocks", "i18n")


def config_hash(cfg) -> str:
    import hashlib
    import json

    raw = json.dumps(cfg or {}, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


#: откаченный владельцем сайт — тихо, без «ПРОПУЩЕНО» на каждом деплое
ROLLED_BACK = "rolled_back"
#: строка сайта занята дольше `LOCK_TIMEOUT` или менялась во время переноса — повтор на
#: следующем деплое
BUSY = "busy"
LOCK_TIMEOUT = "2s"
_ATTEMPTS = 3


def _lock(model, pk):
    """Строка под блокировкой, но не дольше `LOCK_TIMEOUT` (деплой не висит на занятом сайте)."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
    return model.objects.select_for_update().get(pk=pk)


def apply_tenant(tenant, *, dry_run: bool = False) -> Report:
    """Перенести коды одного сайта. Перенос считается БЕЗ блокировки; под блокировкой —
    только сверка «настройки не менялись» (иначе — заново) и одна запись со снимком."""
    from django.db import transaction

    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    if SiteConfigSnapshot.objects.filter(
        tenant_id=tenant.pk, reason=REASON, undone_at__isnull=False
    ).exists():
        return Report(surfaces={"*": ROLLED_BACK})  # владелец откатил — не повторяем
    for _attempt in range(_ATTEMPTS):
        before = Tenant.objects.filter(pk=tenant.pk).values_list("site_config", flat=True).get()
        before = before or {}
        new, report = migrate(before)
        if not report.changed or dry_run:
            return report
        with transaction.atomic():
            locked = _lock(Tenant, tenant.pk)
            if config_hash(locked.site_config or {}) != config_hash(before):
                continue  # кабинет успел сохранить — считаем заново
            locked.site_config = new
            locked.save(update_fields=["site_config"])
            # хэш — после записи и чтения из базы (JSONB): откат сравнивает то же самое
            locked.refresh_from_db(fields=["site_config"])
            SiteConfigSnapshot.objects.create(
                tenant=locked,
                reason=REASON,
                # меняется только `page_blocks` — его и храним (снимок не раздувается)
                before={k: before.get(k) for k in _TOUCHED},
                after_hash=config_hash(locked.site_config or {}),
            )
            transaction.on_commit(lambda s=locked.schema_name: bump_storefront_cache(s))
        return report
    return Report(surfaces={"*": BUSY})


def undo_tenant(tenant) -> str:
    """Откат последнего переноса: "undone" | "none" (нечего) | "changed" (настройки с тех пор
    меняли — не трогаем, решает владелец)."""
    from django.db import transaction
    from django.utils import timezone

    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    with transaction.atomic():
        locked = _lock(Tenant, tenant.pk)
        snap = (
            SiteConfigSnapshot.objects.select_for_update()
            .filter(tenant=locked, reason=REASON, undone_at__isnull=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if snap is None:
            return "none"
        if config_hash(locked.site_config or {}) != snap.after_hash:
            return "changed"
        restored = dict(locked.site_config or {})
        for key in _TOUCHED:
            old = (snap.before or {}).get(key)
            if old is None:
                restored.pop(key, None)
            else:
                restored[key] = old
        locked.site_config = restored
        locked.save(update_fields=["site_config"])
        snap.undone_at = timezone.now()
        snap.save(update_fields=["undone_at"])
        schema = locked.schema_name
        transaction.on_commit(lambda: bump_storefront_cache(schema))
    return "undone"
