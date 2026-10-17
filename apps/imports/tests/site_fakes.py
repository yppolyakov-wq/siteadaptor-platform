"""Фейковый транспорт для тестов импорта с сайта: словарь URL → ответ, без сети."""

import json

from apps.core.ssrf import Fetched, SsrfError


class FakeSite:
    def __init__(self, pages: dict, *, blocked=()):
        self.pages = pages  # url -> (status, content_type, body) | str(html)
        self.blocked = set(blocked)
        self.calls = []

    def __call__(self, url, *, accept=None, max_bytes=0, headers=None, **_kw):
        self.calls.append(url)
        if url in self.blocked:
            raise SsrfError("blocked")
        value = self.pages.get(url)
        if value is None:
            return Fetched(url, 404, "text/html", b"")
        if isinstance(value, str):
            value = (200, "text/html", value)
        status, ctype, body = value
        if isinstance(body, str):
            body = body.encode()
        return Fetched(url, status, ctype, body if 200 <= status < 300 else b"", "utf-8")


def html(*, body="", jsonld=None, meta=None, lang="de", title="Seite"):
    head = [f"<title>{title}</title>"]
    for key, value in (meta or {}).items():
        attr = "property" if key.startswith(("og:", "product:")) else "name"
        head.append(f'<meta {attr}="{key}" content="{value}">')
    for block in jsonld or []:
        head.append(f'<script type="application/ld+json">{json.dumps(block)}</script>')
    return f'<html lang="{lang}"><head>{"".join(head)}</head><body>{body}</body></html>'


def verified_run(host="laden.example"):
    """Ранее подтверждённый сайт тенанта (ревью Г1: без него ничего не применяется)."""
    from django.utils import timezone

    from apps.imports.models import SiteImportRun

    return SiteImportRun.objects.create(
        start_url=f"https://{host}/",
        host=host,
        consent_at=timezone.now(),
        consent_version="x",
        status=SiteImportRun.STATUS_FAILED,
        verified_at=timezone.now(),
        verified_method="meta",
    )
