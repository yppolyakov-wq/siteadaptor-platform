"""Сервис импорта с сайта (T-8.27b): старт прогона с согласием, выполнение, черновик."""

from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import crawl as crawl_mod
from . import diff as diff_mod
from . import structured

logger = logging.getLogger(__name__)

# Версия текста согласия: меняем вместе с формулировкой в шаблоне старта.
CONSENT_VERSION = "2026-10-17"
FINGERPRINT_FIELDS = ("kind", "name", "description", "price", "image_url", "category_hint")


class StartError(ValueError):
    pass


def fingerprint(data: dict) -> str:
    payload = {k: data.get(k) or "" for k in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def identity_key(identity: str) -> str:
    return hashlib.sha256(identity.encode()).hexdigest()


def start_run(*, user, url: str):
    """Проверить и создать прогон; задача ставится после коммита. Бросает StartError."""
    from ..models import SiteImportRun

    normalized = crawl_mod.normalize(url)
    if not normalized:
        raise StartError(_("Bitte eine gültige Website-Adresse (https://…) angeben."))
    if SiteImportRun.objects.filter(status__in=SiteImportRun.ACTIVE).exists():
        raise StartError(_("Ein Import läuft bereits. Bitte warten Sie, bis er fertig ist."))
    since = timezone.now() - timezone.timedelta(days=1)
    if (
        SiteImportRun.objects.filter(created_at__gte=since).count()
        >= settings.SITE_IMPORT_DAILY_RUNS
    ):
        raise StartError(_("Für heute sind keine weiteren Importe möglich. Bitte morgen erneut."))
    from urllib.parse import urlsplit

    previous = SiteImportRun.objects.filter(status=SiteImportRun.STATUS_APPLIED).first()
    run = SiteImportRun.objects.create(
        start_url=normalized[:500],
        host=(urlsplit(normalized).hostname or "")[:255],
        consent_at=timezone.now(),
        consent_by_id=getattr(user, "pk", None),
        consent_version=CONSENT_VERSION,
        previous_run=previous,
    )
    schema = connection.schema_name
    transaction.on_commit(lambda: _enqueue(schema, run.pk))
    return run


def _enqueue(schema: str, run_id) -> None:
    from ..tasks import run_site_import

    run_site_import.delay(
        dedupe_key=f"site-import:{schema}:{run_id}", schema_name=schema, run_id=str(run_id)
    )


def execute(run, *, fetch=None) -> None:
    """Обход + разбор + черновик. Вызывается из Celery внутри schema_context."""
    from ..models import SiteImportItem, SiteImportRun

    run.status = SiteImportRun.STATUS_CRAWLING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])
    result = crawl_mod.crawl(run.start_url, fetch=fetch)
    run.pages = result.log[:100]
    if result.robots_blocked or result.error or not result.pages:
        run.status = SiteImportRun.STATUS_FAILED
        run.error_code = "robots" if result.robots_blocked else result.error or "no_pages"
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_code", "pages", "finished_at", "updated_at"])
        return
    extracted = structured.extract(result.pages)
    run.html_lang = extracted["lang"][:8]
    run.profile = extracted["profile"]
    run.method = "structured"
    # T-8.27e: ИИ — только для страниц без структурированных позиций; вызов вне atomic.
    from . import ai_extract

    ai_items, ai_code = ai_extract.extract(result.pages)
    known = {i["identity"] for i in extracted["items"]}
    added = [i for i in ai_items if i["identity"] not in known]
    if added:
        extracted["items"] += added
        run.ai_used = True
        run.method = "mixed" if len(added) < len(extracted["items"]) else "ai"
    candidates = [
        {
            "identity_key": identity_key(item["identity"]),
            "fingerprint": fingerprint(item),
            "data": item,
        }
        for item in extracted["items"]
    ]
    compared, removed = diff_mod.compare(candidates, applied_state(exclude_run=run))
    with transaction.atomic():
        run.items.all().delete()
        rows = []
        for cand in compared:
            item = cand["data"]
            if cand["previous"]:
                item = {**item, "previous": cand["previous"]}
            rows.append(
                SiteImportItem(
                    run=run,
                    kind=item["kind"],
                    diff=cand["diff"],
                    source_url=(item.get("page_url") or "")[:500],
                    data=item,
                    fingerprint=cand["fingerprint"],
                    identity_key=cand["identity_key"],
                    ai_generated=item.get("method") == "ai",
                )
            )
        for gone in removed:
            rows.append(
                SiteImportItem(
                    run=run,
                    kind=gone["data"].get("kind", "product"),
                    diff=SiteImportItem.DIFF_REMOVED,
                    source_url=(gone["data"].get("page_url") or "")[:500],
                    data=gone["data"],
                    fingerprint=gone["fingerprint"],
                    identity_key=gone["identity_key"],
                    target_kind=gone["target_kind"],
                    target_id=gone["target_id"],
                )
            )
        SiteImportItem.objects.bulk_create(rows)
        run.stats = {
            "pages": len(result.pages),
            "items": len(extracted["items"]),
            "ai": ai_code or ("used" if added else ""),
        }
        run.status = SiteImportRun.STATUS_READY
        run.finished_at = timezone.now()
        run.save()


def applied_state(*, exclude_run=None) -> dict:
    """Последнее применённое состояние каждой позиции: {identity_key: {...}}. Позиция,
    которую владелец отключил как пропавшую, в состояние не входит — вернётся «новой»."""
    from ..models import SiteImportItem

    qs = SiteImportItem.objects.filter(applied_at__isnull=False).exclude(target_id="")
    if exclude_run is not None:
        qs = qs.exclude(run=exclude_run)
    state = {}
    for item in qs.order_by("applied_at"):
        state[item.identity_key] = {
            "fingerprint": item.fingerprint,
            "data": item.data,
            "target_kind": item.target_kind,
            "target_id": item.target_id,
            "removed": item.diff == SiteImportItem.DIFF_REMOVED,
        }
    return {k: v for k, v in state.items() if not v.pop("removed")}
