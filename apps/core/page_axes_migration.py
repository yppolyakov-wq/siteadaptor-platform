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


def _listing_code(cfg: dict, surface: str) -> str:
    styles = cfg.get("page_styles") if isinstance(cfg, dict) else None
    code = styles.get(surface, "") if isinstance(styles, dict) else ""
    return code if isinstance(code, str) else ""


def migrate_listings(raw: dict) -> tuple[dict, Report]:
    """Коды девяти листингов (`page_styles[surface]`) → строки хоста листинга."""
    from apps.core import listing_parts
    from apps.core import page_parts as pp
    from apps.tenants import siteconfig

    report = Report()
    out = copy.deepcopy(raw if isinstance(raw, dict) else {})
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
        candidate = copy.deepcopy(out)
        blocks = dict(candidate.get("page_blocks") or {})
        blocks[host] = new_rows
        candidate["page_blocks"] = blocks
        after = siteconfig.normalize(candidate)
        # проверка «без кода» и «с кодом» (пока старый ключ на месте, витрина читает оба)
        if pp.effective(s, after, host) != before or listing_parts.effective(after, surface) != (
            before
        ):
            report.surfaces[surface] = MISMATCH
            continue
        out = candidate
        report.surfaces[surface] = DONE
    return out, report


def migrate(raw: dict) -> tuple[dict, Report]:
    """Все перенесённые поверхности (B1a — листинги)."""
    return migrate_listings(raw)


# ───────── запись в базу (команда `materialize_page_axes`) ─────────

REASON = "fb31.7-page-axes"


def config_hash(cfg) -> str:
    import hashlib
    import json

    raw = json.dumps(cfg or {}, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def apply_tenant(tenant, *, dry_run: bool = False) -> Report:
    """Перенести коды одного сайта: блокировка строки, снимок до правки, одна запись."""
    from django.db import transaction

    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
        if SiteConfigSnapshot.objects.filter(
            tenant=locked, reason=REASON, undone_at__isnull=False
        ).exists():
            # владелец откатил перенос этого сайта — следующий деплой его не повторяет
            return Report(surfaces={"*": SKIP})
        before = locked.site_config or {}
        new, report = migrate(before)
        if report.changed and not dry_run:
            SiteConfigSnapshot.objects.create(
                tenant=locked, reason=REASON, before=before, after_hash=config_hash(new)
            )
            locked.site_config = new
            locked.save(update_fields=["site_config"])
            schema = locked.schema_name
            transaction.on_commit(lambda: bump_storefront_cache(schema))
    return report


def undo_tenant(tenant) -> str:
    """Откат последнего переноса: "undone" | "none" (нечего) | "changed" (настройки с тех пор
    меняли — не трогаем, решает владелец)."""
    from django.db import transaction
    from django.utils import timezone

    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import SiteConfigSnapshot, Tenant

    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
        snap = (
            SiteConfigSnapshot.objects.select_for_update()
            .filter(tenant=locked, reason=REASON, undone_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if snap is None:
            return "none"
        if config_hash(locked.site_config or {}) != snap.after_hash:
            return "changed"
        locked.site_config = snap.before
        locked.save(update_fields=["site_config"])
        snap.undone_at = timezone.now()
        snap.save(update_fields=["undone_at"])
        schema = locked.schema_name
        transaction.on_commit(lambda: bump_storefront_cache(schema))
    return "undone"
