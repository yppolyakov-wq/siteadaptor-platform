"""Сервис импорта с сайта (T-8.27b): старт прогона с согласием, выполнение, черновик."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from datetime import timedelta
from urllib.parse import urlsplit

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
# Прогон в queued/crawling дольше этого — задача умерла (OOM, рестарт, брокер): помечаем
# failed, иначе «Ein Import läuft bereits» блокировал бы импорт навсегда. Бюджет обхода
# 120 с + ИИ + запас.
STALE_AFTER = timedelta(minutes=15)


class StartError(ValueError):
    pass


def fingerprint(data: dict) -> str:
    payload = {k: data.get(k) or "" for k in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def identity_key(identity: str) -> str:
    return hashlib.sha256(identity.encode()).hexdigest()


def _host_error(host: str):
    """IP-литерал или хост платформы как «свой сайт» не принимаем."""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return _("Bitte die Adresse Ihrer Website angeben, keine IP-Adresse.")
    except ValueError:
        pass
    base = (getattr(settings, "TENANT_DOMAIN_BASE", "") or "").lower()
    if base and (host == base or host.endswith("." + base)):
        return _("Diese Adresse gehört zu unserer Plattform. Bitte Ihre eigene Website angeben.")
    return None


def _reap_stale(SiteImportRun) -> None:
    cutoff = timezone.now() - STALE_AFTER
    SiteImportRun.objects.filter(status__in=SiteImportRun.ACTIVE, updated_at__lt=cutoff).update(
        status=SiteImportRun.STATUS_FAILED,
        error_code="stale",
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )


def _lock_schema() -> None:
    """Advisory-lock на схему: два параллельных старта не создадут два прогона."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [f"site-import-start:{connection.schema_name}"],
        )


def start_run(*, user, url: str):
    """Проверить и создать прогон; задача ставится после коммита. Бросает StartError."""
    from ..models import SiteImportRun

    normalized = crawl_mod.normalize(url)
    if not normalized:
        raise StartError(_("Bitte eine gültige Website-Adresse (https://…) angeben."))
    host = (urlsplit(normalized).hostname or "").lower()
    problem = _host_error(host)
    if problem:
        raise StartError(problem)
    with transaction.atomic():
        _lock_schema()
        _reap_stale(SiteImportRun)
        if SiteImportRun.objects.filter(status__in=SiteImportRun.ACTIVE).exists():
            raise StartError(_("Ein Import läuft bereits. Bitte warten Sie, bis er fertig ist."))
        since = timezone.now() - timedelta(days=1)
        if (
            SiteImportRun.objects.filter(created_at__gte=since).count()
            >= settings.SITE_IMPORT_DAILY_RUNS
        ):
            raise StartError(
                _("Für heute sind keine weiteren Importe möglich. Bitte morgen erneut.")
            )
        previous = SiteImportRun.objects.filter(status=SiteImportRun.STATUS_APPLIED).first()
        run = SiteImportRun.objects.create(
            start_url=normalized[:500],
            host=host[:255],
            consent_at=timezone.now(),
            consent_by_id=getattr(user, "pk", None),
            consent_version=CONSENT_VERSION,
            previous_run=previous,
        )
        schema = connection.schema_name
        transaction.on_commit(lambda: _enqueue(schema, run.pk))
    return run


def _enqueue(schema: str, run_id) -> None:
    from ..models import SiteImportRun
    from ..tasks import run_site_import

    try:
        run_site_import.delay(
            dedupe_key=f"site-import:{schema}:{run_id}", schema_name=schema, run_id=str(run_id)
        )
    except Exception:  # noqa: BLE001 — брокер недоступен: прогон не висит в queued
        logger.exception("site import enqueue failed: %s", run_id)
        SiteImportRun.objects.filter(pk=run_id, status=SiteImportRun.STATUS_QUEUED).update(
            status=SiteImportRun.STATUS_FAILED, error_code="queue", finished_at=timezone.now()
        )


def execute(run, *, fetch=None) -> None:
    """Обход + разбор + черновик. Вызывается из Celery внутри schema_context."""
    from ..models import SiteImportItem, SiteImportRun

    run.status = SiteImportRun.STATUS_CRAWLING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])
    result = crawl_mod.crawl(run.start_url, fetch=fetch)
    run.pages = result.log[:100]
    from . import verify

    verified = verify.ensure(run, fetch=fetch)
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
    added = []
    for item in ai_items:  # ИИ-двойники между собой тоже склеиваются
        if item["identity"] not in known:
            known.add(item["identity"])
            added.append(item)
    if added:
        extracted["items"] += added
        run.ai_used = True
        run.method = "mixed" if len(added) < len(extracted["items"]) else "ai"
    candidates, keys = [], set()
    for item in extracted["items"]:
        key = identity_key(item["identity"])
        if key in keys:  # одна позиция на нескольких страницах — одна строка прогона
            continue
        keys.add(key)
        candidates.append({"identity_key": key, "fingerprint": fingerprint(item), "data": item})
    compared, removed = diff_mod.compare(candidates, applied_state(exclude_run=run))
    if result.partial:
        # Обход неполный: «не нашли» ≠ «удалено с сайта» — не предлагаем скрывать.
        removed = []
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
            "items": len(candidates),
            "ai": ai_code or ("used" if added else ""),
            "partial": result.partial,
        }
        run.status = SiteImportRun.STATUS_READY
        run.finished_at = timezone.now()
        run.save()
    if verified:
        _adopt_website(run)


def _adopt_website(run) -> None:
    """Подтверждённый сайт становится сайтом бизнеса, если тот ещё не задан."""
    from apps.tenants.models import Tenant

    Tenant.objects.filter(schema_name=connection.schema_name, website_url="").update(
        website_url=f"{urlsplit(run.start_url).scheme}://{urlsplit(run.start_url).netloc}"[:200]
    )


def applied_state(*, exclude_run=None) -> dict:
    """Последнее применённое состояние каждой позиции: {identity_key: {...}}. Позиция,
    которую владелец отключил как пропавшую, в состояние не входит — вернётся «новой»."""
    from ..models import SiteImportItem

    qs = SiteImportItem.objects.filter(applied_at__isnull=False).exclude(target_id="")
    if exclude_run is not None:
        qs = qs.exclude(run=exclude_run)
    state = {}
    fields = ("identity_key", "fingerprint", "data", "target_kind", "target_id", "diff")
    for item in qs.order_by("applied_at").only(*fields):
        state[item.identity_key] = {
            "fingerprint": item.fingerprint,
            "data": item.data,
            "target_kind": item.target_kind,
            "target_id": item.target_id,
            "removed": item.diff == SiteImportItem.DIFF_REMOVED,
        }
    state = {k: v for k, v in state.items() if not v.pop("removed")}
    # Цель, удалённую владельцем, в состоянии не держим: позиция вернётся «новой», а
    # лимит бесплатной ступени не занят мёртвым товаром (ревью Г1).
    alive = _alive_targets(state.values())
    return {k: v for k, v in state.items() if (v["target_kind"], v["target_id"]) in alive}


def _alive_targets(entries) -> set:
    from apps.booking.models import Service
    from apps.catalog.models import Product

    ids = {"product": set(), "service": set()}
    for entry in entries:
        if entry["target_kind"] in ids:
            ids[entry["target_kind"]].add(entry["target_id"])
    alive = set()
    for kind, model in (("product", Product), ("service", Service)):
        if not ids[kind]:
            continue
        valid = []
        for raw in ids[kind]:
            try:
                valid.append(model._meta.pk.to_python(raw))
            except Exception:  # noqa: BLE001 — битый id: цели нет
                continue
        for pk in model.objects.filter(pk__in=valid).values_list("pk", flat=True):
            alive.add((kind, str(pk)))
    return alive
