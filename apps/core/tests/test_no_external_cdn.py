"""KA-12 E0.1 (KA-9 №7, KA-10 №25–26): скрипты и стили — со своего сервера.

Подключение с unpkg/jsdelivr/cdnjs передаёт IP посетителя третьей стороне без согласия
(DSGVO). Исключение — telegram-web-app.js: его требует сам Telegram для Mini App.
"""

import re
from pathlib import Path

CDN = re.compile(r"https://(unpkg\.com|cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)")


def _files(*globs):
    root = Path(__file__).resolve().parents[3]
    for g in globs:
        yield from root.glob(g)


def test_no_cdn_in_templates_or_asset_registries():
    hits = []
    for f in _files("templates/**/*.html", "apps/**/templatetags/*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if CDN.search(line):
                hits.append(f"{f}: {line.strip()[:120]}")
    assert not hits, "внешний CDN:\n" + "\n".join(hits)


def test_htmx_is_self_hosted_once():
    root = Path(__file__).resolve().parents[3]
    assert (root / "static/vendor/htmx/htmx.min.js").is_file()
    base = (root / "templates/base.html").read_text()
    dash = (root / "templates/tenant/_base_dashboard.html").read_text()
    assert (
        base.count("htmx.min.js") == 1
        and "htmx" not in dash.split("{% block extra_head %}")[1][:80]
    )
    assert "alpinejs" not in base


def test_gift_voucher_tile_links_somewhere(settings, db):
    """KA-12 E0.2 (KA-5a B3): плитка «Geschenkgutscheine» в Sortiment вела в никуда."""
    from apps.core.sellable_manage import digital_shelf
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory.build(disabled_modules=[])
    tiles = [t for t in digital_shelf(tenant) if "/gutschein/" in " ".join(map(str, t["items"]))]
    assert tiles and all(t["url"] for t in tiles)
