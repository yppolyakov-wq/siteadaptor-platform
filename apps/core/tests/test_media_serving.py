"""P0-2 (аудит 2026-09-03 §9.3): раздача /media/ не отдаёт приватные префиксы.

Один MEDIA_ROOT на всех бизнесов, Caddy проксирует всё в Django (file_server
для /media/ нет), а `django.views.static.serve` стоял в трёх urlconf без
единого гейта — загрузки мастера импорта (`imports/<исходное имя>`) и
шифротексты документов (`documents/*.enc`) были доступны с любого хоста.
Теперь три urlconf зовут одну обёртку с deny-list'ом; префикс проверяется по
пути, решённому ОТНОСИТЕЛЬНО КОРНЯ: `./imports/x`, `products/../imports/x`,
`/imports/x` и — главное — `../media/imports/x` (ведущие `..` normpath не
убирает, а safe_join сворачивает внутрь корня) обязаны давать 404.
"""

import re
from pathlib import Path

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import resolve

from apps.core import media_views

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


def _get(path: str):
    request = RequestFactory().get(f"/media/{path}")
    return media_views.serve_media(request, path=path)


@pytest.fixture
def media_root(tmp_path):
    """MEDIA_ROOT = <tmp>/media, чтобы `../media/…` из корня возвращался в него же."""
    root = tmp_path / "media"
    (root / "imports").mkdir(parents=True)
    (root / "imports" / "preisliste-2026.csv").write_text("sku;price\n")
    (root / "documents").mkdir()
    (root / "documents" / "0d3e1f.enc").write_bytes(b"gAAAA")
    (root / "products").mkdir()
    (root / "products" / "a.webp").write_bytes(b"RIFF....WEBP")
    with override_settings(MEDIA_ROOT=root):
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "imports/preisliste-2026.csv",
        "documents/0d3e1f.enc",
        "imports",
        "imports/",
        "./imports/preisliste-2026.csv",
        "products/../imports/preisliste-2026.csv",
        "/imports/preisliste-2026.csv",
        # Обход первой версии гейта (ревью плана): ведущий `..` переживает
        # normpath, а safe_join сворачивает путь обратно внутрь MEDIA_ROOT.
        "../media/imports/preisliste-2026.csv",
        "../media/./documents/0d3e1f.enc",
        "products/../../media/imports/preisliste-2026.csv",
    ],
)
def test_private_prefixes_are_not_served(path, media_root):
    with pytest.raises(Http404):
        _get(path)


@pytest.mark.parametrize("path", ["../../etc/passwd", "../outside.txt", "/../x"])
def test_escape_from_media_root_is_404_not_400(path, media_root):
    """Выход за корень — 404, а не SuspiciousFileOperation/400: существование
    файлов вне корня мы не подтверждаем и не опровергаем."""
    (media_root.parent / "outside.txt").write_text("x")
    with pytest.raises(Http404):
        _get(path)


@pytest.mark.parametrize(
    "path", ["products/a.webp", "./products/a.webp", "../media/products/a.webp"]
)
def test_public_prefix_is_still_served(path, media_root):
    response = _get(path)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"RIFF....WEBP"


@pytest.mark.parametrize(
    "urlconf", ["config.urls_tenant", "config.urls_public", "config.urls_portal"]
)
def test_every_urlconf_resolves_media_to_the_guard(urlconf, media_root):
    """Сквозь резолвер каждого urlconf: маршрут /media/ существует (SERVE_MEDIA
    в тестах включён явно) и ведёт в гейт — приватное 404, публичное 200."""
    match = resolve("/media/imports/preisliste-2026.csv", urlconf=urlconf)
    assert match.func is media_views.serve_media
    request = RequestFactory().get("/media/imports/preisliste-2026.csv")
    with pytest.raises(Http404):
        match.func(request, *match.args, **match.kwargs)
    ok = resolve("/media/products/a.webp", urlconf=urlconf)
    assert (
        ok.func(RequestFactory().get("/media/products/a.webp"), *ok.args, **ok.kwargs).status_code
        == 200
    )


@pytest.mark.parametrize("urlconf", ["urls_tenant", "urls_public", "urls_portal"])
def test_no_urlconf_uses_bare_static_serve(urlconf):
    """Замок по исходнику дополняет резолверный: голый `serve` рядом с гейтом
    (второй маршрут, другой префикс) резолвер на одном пути не заметит."""
    text = (ROOT / "config" / f"{urlconf}.py").read_text()
    media_lines = [line for line in text.splitlines() if 'path("media/<path:path>"' in line]
    assert media_lines, f"{urlconf}: маршрут /media/ исчез"
    assert all("serve_media" in line for line in media_lines), media_lines
    assert "django.views.static import serve" not in text, f"{urlconf}: голый static.serve"


#: Папку загрузок задают тремя способами: `folder=`/`upload_to=` и прямой
#: `default_storage.save("<папка>/…")`. Третий сканер раньше не видел — новая
#: приватная папка молча оказалась бы «не классифицированной, но публичной».
_FOLDER_LITERAL = re.compile(
    r"""(?:folder|upload_to)\s*=\s*["']([A-Za-z0-9_]+)"""
    r"""|(?:default_storage|storage)\.save\(\s*f?["']([A-Za-z0-9_]+)/"""
)


def _upload_folders_in_code() -> set[str]:
    found = set()
    for py in (ROOT / "apps").rglob("*.py"):
        parts = py.relative_to(ROOT).parts
        if "tests" in parts or "migrations" in parts:
            continue
        for groups in _FOLDER_LITERAL.findall(py.read_text()):
            found.update(g for g in groups if g)
    return found


def test_every_upload_folder_is_classified():
    """Инвентарь папок загрузок = литералы `folder=`/`upload_to=` в коде. Каждая
    обязана быть либо в PUBLIC_PREFIXES, либо в PRIVATE_PREFIXES: новая папка
    без осознанной классификации — красный тест, а не «по умолчанию публично».
    Обратно: оба приватных префикса должны существовать в коде — иначе deny-list
    защищает призрак, а реальный путь переехал."""
    found = _upload_folders_in_code()
    classified = media_views.PUBLIC_PREFIXES | media_views.PRIVATE_PREFIXES
    assert found, "сканер не нашёл ни одной папки — регэксп или структура изменились"
    assert found <= classified, f"неклассифицированные папки: {sorted(found - classified)}"
    assert media_views.PRIVATE_PREFIXES <= found
    assert not (media_views.PUBLIC_PREFIXES & media_views.PRIVATE_PREFIXES)
