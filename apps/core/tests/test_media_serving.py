"""P0-2 (аудит 2026-09-03 §9.3): раздача /media/ не отдаёт приватные префиксы.

Один MEDIA_ROOT на всех бизнесов, Caddy проксирует всё в Django (file_server
для /media/ нет), а `django.views.static.serve` стоял в трёх urlconf без
единого гейта — загрузки мастера импорта (`imports/<исходное имя>`) и
шифротексты документов (`documents/*.enc`) были доступны с любого хоста.
Теперь три urlconf зовут одну обёртку с deny-list'ом; путь нормализуется ДО
проверки префикса, иначе `./imports/x` или `products/../imports/x` обошли бы её.
"""

from pathlib import Path

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings

from apps.core import media_views

pytestmark = pytest.mark.django_db


def _get(path: str):
    request = RequestFactory().get(f"/media/{path}")
    return media_views.serve_media(request, path=path)


@pytest.mark.parametrize(
    "path",
    [
        "imports/preisliste-2026.csv",
        "documents/0d3e1f.enc",
        "./imports/preisliste-2026.csv",
        "products/../imports/preisliste-2026.csv",
        "/imports/preisliste-2026.csv",
    ],
)
def test_private_prefixes_are_not_served(path, tmp_path):
    (tmp_path / "imports").mkdir()
    (tmp_path / "imports" / "preisliste-2026.csv").write_text("sku;price\n")
    with override_settings(MEDIA_ROOT=tmp_path):
        with pytest.raises(Http404):
            _get(path)


def test_public_prefix_is_still_served(tmp_path):
    (tmp_path / "products").mkdir()
    (tmp_path / "products" / "a.webp").write_bytes(b"RIFF....WEBP")
    with override_settings(MEDIA_ROOT=tmp_path):
        response = _get("products/a.webp")
    assert response.status_code == 200


@pytest.mark.parametrize("urlconf", ["urls_tenant", "urls_public", "urls_portal"])
def test_every_urlconf_routes_media_through_the_guard(urlconf):
    """Гейт бесполезен, если хоть один urlconf зовёт голый static.serve.

    Замок по ИСХОДНИКУ: ветка `if SERVE_MEDIA` строится при импорте urlconf и
    зависит от окружения (в тестах выключена) — резолвить /media/ в рантайме
    нельзя, а вот пропустить голый `serve` в одном из трёх файлов — легко.
    """
    text = (Path(__file__).resolve().parents[3] / "config" / f"{urlconf}.py").read_text()
    media_lines = [line for line in text.splitlines() if 'path("media/<path:path>"' in line]
    assert media_lines, f"{urlconf}: маршрут /media/ исчез"
    assert all("serve_media" in line for line in media_lines), media_lines
    assert "django.views.static import serve" not in text, f"{urlconf}: голый static.serve"
