"""Целостность шаблонов: каждому `{%` — свой `%}`.

2026-11-03: `stays/_stay_guest.html` оказался склеен со своей копией, и склейка съела
`{% lo` у второго `{% load i18n cabinet %}` — на карточке брони торчал обрывок
«ad i18n cabinet %}», а имя и почта гостя печатались дважды. Такая порча оставляет
лишний `%}` — замок ловит весь класс по всем шаблонам.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_every_template_tag_is_balanced():
    broken = []
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(errors="ignore")
        if text.count("{%") != text.count("%}"):
            broken.append(
                f"{path.relative_to(ROOT)}: {{% ×{text.count('{%')} / %}} ×{text.count('%}')}"
            )
    assert not broken, "\n".join(broken)


def test_guest_card_renders_the_guest_once():
    text = (ROOT / "templates" / "stays" / "_stay_guest.html").read_text()
    assert text.count("Open customer card") == 1
    assert "ad i18n cabinet" not in text.replace("{% load i18n cabinet", "")
