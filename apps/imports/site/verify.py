"""Подтверждение владения сайтом перед импортом (ревью Г1, H1/H2).

Галочка «согласия» не доказывает, что сайт принадлежит владельцу: без проверки можно
импортировать чужой каталог и направить листинги каталога города на чужой домен.
Владелец кладёт на сайт токен своего бизнеса — мета-тег на главной или файл
`/.well-known/siteadaptor-verify.txt`; проверка ходит туда через `safe_fetch`.

Токен детерминирован по схеме (HMAC от SECRET_KEY): показать его можно до первого
прогона, а перевыпуск не нужен. Подтверждённый сайт хранится в `SiteImportRun`
(схема тенанта), а не в `site_config` — туда владелец пишет сам."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.core.ssrf import SsrfError, safe_fetch

from . import htmlparse
from .crawl import _site, same_site

META_NAME = "siteadaptor-verify"
FILE_PATH = "/.well-known/siteadaptor-verify.txt"
_MAX_BYTES = 512 * 1024
_TIMEOUT = 6


def token(schema: str | None = None) -> str:
    schema = schema or connection.schema_name
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"site-verify:{schema}".encode(), hashlib.sha256).hexdigest()[:24]


def meta_tag(schema: str | None = None) -> str:
    return f'<meta name="{META_NAME}" content="{token(schema)}">'


def _root(start_url: str) -> str:
    parts = urlsplit(start_url)
    return f"{parts.scheme}://{parts.netloc}"


def check(start_url: str, *, schema: str | None = None, fetch=None) -> str:
    """Найти токен на сайте. Вернуть способ ('file' | 'meta') или ''."""
    fetch = fetch or safe_fetch
    expected = token(schema)
    root = _root(start_url)
    headers = {"User-Agent": settings.SITE_IMPORT_USER_AGENT}
    try:
        got = fetch(
            root + FILE_PATH, accept=None, max_bytes=4096, headers=headers, timeout=_TIMEOUT
        )
        if (
            got.ok
            and same_site(got.url, urlsplit(root).hostname or "")
            and (expected in got.text().split())
        ):
            return "file"
    except (SsrfError, requests.RequestException, ValueError):
        pass
    try:
        got = fetch(
            root + "/",
            accept=("text/html", "application/xhtml+xml"),
            max_bytes=_MAX_BYTES,
            headers=headers,
            timeout=_TIMEOUT,
        )
    except (SsrfError, requests.RequestException, ValueError):
        return ""
    if not got.ok or not same_site(got.url, urlsplit(root).hostname or ""):
        return ""
    page = htmlparse.parse(got.text(), got.url)
    found = (page.meta.get(META_NAME) or "").strip()
    return "meta" if found and hmac.compare_digest(found, expected) else ""


def verified_host() -> str:
    """Подтверждённый сайт текущей схемы (без www.) или ''."""
    from ..models import SiteImportRun

    host = (
        SiteImportRun.objects.filter(verified_at__isnull=False)
        .order_by("-verified_at")
        .values_list("host", flat=True)
        .first()
    )
    return _site(host or "")


def is_verified(run) -> bool:
    if run.verified_at:
        return True
    known = verified_host()
    return bool(known) and same_site(run.start_url, known)


def mark(run, method: str) -> None:
    run.verified_at = timezone.now()
    run.verified_method = method
    run.save(update_fields=["verified_at", "verified_method", "updated_at"])


def ensure(run, *, fetch=None) -> bool:
    """Прогон подтверждён: уже, по ранее подтверждённому сайту или проверкой сейчас."""
    if run.verified_at:
        return True
    known = verified_host()
    if known and same_site(run.start_url, known):
        mark(run, "known")
        return True
    method = check(run.start_url, fetch=fetch)
    if method:
        mark(run, method)
        return True
    return False


def tenant_verified_host(tenant) -> str:
    """То же для объекта тенанта из любой схемы (синк каталога города идёт в public).
    Запоминается на объекте — один запрос на синк/рендер."""
    if tenant is None or not getattr(tenant, "schema_name", ""):
        return ""
    memo = getattr(tenant, "_t827_verified_host", None)
    if memo is not None:
        return memo
    from django_tenants.utils import schema_context

    try:
        with schema_context(tenant.schema_name):
            value = verified_host()
    except Exception:  # noqa: BLE001 — нет таблицы/схемы: внешней ссылки нет (fail-closed)
        value = ""
    try:
        tenant._t827_verified_host = value
    except Exception:  # noqa: BLE001 — стаб без атрибутов
        pass
    return value
