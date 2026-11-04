"""UX-D D7 (П6): узкие страницы кабинета → на широком экране две колонки.

План — docs/ux-d7-wide-pages-plan-2026-11-04.md. Раскладка меняется только на xl
(`xl:grid-cols-…`); порядок DOM — порядок чтения на телефоне. Поля форм остаются теми
же (W0): эти замки проверяют обёртку, а поведение форм — замки самих экранов.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

TWO_COLUMN = (
    "tenant/betriebsferien.html",
    "tenant/redirects.html",
    "support/help_list.html",
    "imports/import_start.html",
    "publishing/posts.html",
    "publishing/channels.html",
    "stays/stay_settings.html",
    "finance/ergebnis.html",
    "tenant/site_seo.html",
    "booking/service_page.html",
    "stays/unit_page.html",
)


@pytest.mark.parametrize("name", TWO_COLUMN)
def test_page_has_two_columns_on_wide_screens(name):
    text = (ROOT / "templates" / name).read_text()
    m = re.search(r'<div class="[^"]*\bxl:grid-cols-[^"]*"[^>]*data-d7-cols', text)
    assert m, name
    # одна колонка до xl: никаких sm/md/lg-колонок у самой обёртки
    assert not re.search(r"\b(?:sm|md|lg):grid-cols", m.group(0)), name


@pytest.mark.parametrize(
    "name",
    (
        "tenant/betriebsferien.html",
        "tenant/redirects.html",
        "stays/stay_settings.html",
        "stays/kurtaxe.html",
        "stays/reports.html",
        "tenant/site_seo.html",
    ),
)
def test_no_narrow_root_container(name):
    text = (ROOT / "templates" / name).read_text()
    body = text.split("dash_content", 1)[1]
    # корневой контейнер страницы или сетка блоков — не уже 6xl (текстовые заметки — можно)
    narrow = r"\bmax-w-(?:md|lg|xl|2xl|3xl|4xl|5xl)\b"
    pattern = rf'<div class="(?:{narrow[2:-2]}\b|[^"]*\bgrid\b[^"]*{narrow})'
    assert not re.search(pattern, body), name


@pytest.mark.parametrize("name", ("booking/service_page.html", "stays/unit_page.html"))
def test_object_pages_show_customer_preview(name):
    text = (ROOT / "templates" / name).read_text()
    assert '{% include "core/_object_preview.html"' in text


def test_preview_is_inert_and_uses_storefront_card():
    text = (ROOT / "templates/core/_object_preview.html").read_text()
    assert '{% sellable_card kind obj href="#" edit=False %}' in text
    assert re.search(r'<div inert aria-hidden="true"', text)
    assert 'aria-labelledby="obj-preview-h"' in text and 'id="obj-preview-h"' in text
