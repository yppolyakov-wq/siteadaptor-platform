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
    with transaction.atomic():
        run.items.all().delete()
        SiteImportItem.objects.bulk_create(
            [
                SiteImportItem(
                    run=run,
                    kind=item["kind"],
                    source_url=(item.get("page_url") or "")[:500],
                    data=item,
                    fingerprint=fingerprint(item),
                    identity_key=identity_key(item["identity"]),
                    ai_generated=item.get("method") == "ai",
                )
                for item in extracted["items"]
            ]
        )
        run.stats = {"pages": len(result.pages), "items": len(extracted["items"])}
        run.status = SiteImportRun.STATUS_READY
        run.finished_at = timezone.now()
        run.save()
