"""KA-12 E9.9: фото добавляются одной плиткой «＋ Foto» — второго «Choose Files» нет."""

import re
from pathlib import Path

from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"
# Студия и мастер настройки — свой механизм фото; витрина/публичные — не кабинет;
# _photo_picker — камера/галерея ассистента акции (две своих кнопки).
SKIP = (
    "storefront/",
    "aggregator/",
    "tenants/",
    "platform/",
    "public/",
    "konto/",
    "tenant/site_home.html",
    "tenant/site_sections.html",
    "tenant/setup",
    "promotions/_photo_picker.html",
)
_FILE = re.compile(r"<input\b[^>]*\btype=\"file\"[^>]*>")


def test_cabinet_photo_inputs_are_driven_by_tile():
    visible = []
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith(SKIP):
            continue
        for tag in _FILE.findall(path.read_text()):
            if 'accept="image' not in tag or ".pdf" in tag:
                continue  # документы/CSV/Belege (PDF) — не фото
            if 'class="hidden"' in tag or 'class="sr-only"' in tag:
                continue
            visible.append((rel, tag[:90]))
    assert not visible, visible


def test_tile_targets_named_input_in_own_form():
    text = (TEMPLATES / "catalog/_photo_add_tile.html").read_text()
    assert "data-photo-add-proxy=\"{{ target|default:'images' }}\"" in text
    assert 'b.closest("form")' in text
