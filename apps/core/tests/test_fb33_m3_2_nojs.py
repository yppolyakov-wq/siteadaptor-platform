"""FB-33 M3-2: замки ДО кода модального окна (`docs/fb33-editor-model-2026-11-19.md` §«План M3-2»).

Модальное окно `<dialog class="ui-bwin">` создаёт `static/js/aufbau.js` и переносит в него
существующую панель. Сервер и разметка без скриптов не меняются ни на байт: снимок рендера
`site_schema` от шапки (`data-schema-head`) до тега `aufbau.js` — эталон в
`golden_fb33m3/page_nojs/` (снят на de ДО правок кода). Случайное (токен CSRF, токен открытия
окна `wopen`, хеш статики) нормализуется. Пересъёмка — `FB33_M32_REGEN=1`.
"""

import os
import re
from pathlib import Path

import pytest
from django.utils import translation

from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_fb33m3" / "page_nojs"
ROOT = Path(__file__).resolve().parents[3]

#: CASES окна M3-0 и то, что окно M3-2 трогает сверх них
EXTRA = (
    ("home",),  # без блока: «Block wählen»
    ("home", "t1", "&tab=texte"),  # явно открытая вкладка
    ("home", "t1", "&ansicht=telefon"),  # вид «Telefon»
    ("home", "l1", "&welche=regel&tab=wie"),  # открытый способ «Welche»
    ("home", "t1", "&drawer=/dashboard/"),  # адрес со шторкой кабинета
)


def _query(case) -> str:
    code, ref, extra = (*case, "", "")[:3]
    return f"?seite={code}" + (f"&block={ref}" if ref else "") + extra


def _name(case) -> str:
    raw = "_".join(case).replace("&", "").replace("=", "-").replace("/", "")
    return re.sub(r"[^A-Za-z0-9_-]", "", raw) + ".html"


def _normalize(html: str) -> str:
    html = re.sub(
        r'name="csrfmiddlewaretoken" value="[^"]*"', 'name="csrfmiddlewaretoken" value="X"', html
    )
    html = re.sub(r'name="wopen" value="[^"]*"', 'name="wopen" value="W"', html)
    html = re.sub(r"wopen=[A-Za-z0-9_-]+", "wopen=W", html)
    return re.sub(r"aufbau(\.[0-9a-f]{6,})?\.js", "aufbau.js", html)


def _slice(html: str) -> str:
    start = html.rindex("<div", 0, html.index("data-schema-head"))
    end = html.index("js/aufbau", start)
    end = html.index(">", end) + 1
    return _normalize(html[start:end]) + "\n"


def _render(case) -> str:
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    with translation.override("de"):
        return Browser(tenant).get(_query(case))


ALL = (*CASES, *EXTRA)


@pytest.mark.parametrize("case", ALL, ids=["|".join(c) for c in ALL])
def test_page_without_js_is_byte_for_byte_the_same(case):
    got = _slice(_render(case))
    path = GOLDEN / _name(case)
    if os.environ.get("FB33_M32_REGEN") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(got)
        pytest.fail("регенерация эталонов — перезапусти без FB33_M32_REGEN")
    assert got == path.read_text(), path.name


def test_window_token_is_rendered_before_normalization():
    """Нормализация `wopen` не прячет пропажу токена: у окна блока он непустой."""
    html = _render(("home", "t1"))
    assert re.search(r'name="wopen" value="[A-Za-z0-9_-]{4,}"', html)
    assert re.search(r"&amp;wopen=[A-Za-z0-9_-]{4,}", html)


def test_golden_covers_every_case_and_nothing_else():
    assert sorted(p.name for p in GOLDEN.glob("*.html")) == sorted({_name(c) for c in ALL})


@pytest.mark.parametrize("case", ALL, ids=["|".join(c) for c in ALL])
def test_one_panel_inside_the_grid_and_no_server_dialog(case):
    html = _render(case)
    # окно — только из скрипта: серверных `<dialog>` столько же, сколько до M3-2 (шторка
    # кабинета `sf-drawer` и подтверждение `danger-confirm`), в самом экране — ни одного
    assert html.count("<dialog") == 2, case
    assert 'id="sf-drawer"' in html and 'id="danger-confirm"' in html
    assert "<dialog" not in _slice(html) and "ui-bwin" not in html
    assert html.count('id="schema-panel"') == 1
    grid = html[html.index("data-site-schema") : html.index("js/aufbau")]
    assert re.search(r'<aside[^>]*id="schema-panel"[^>]*data-schema-panel', grid)


def test_tab_roles_only_from_js():
    """Без скриптов вкладки — ссылки `?tab=`; роли tab/tablist/tabpanel навешивает `aufbau.js`
    (шаблоны экрана и его частей их не пишут, в эталонах рендера их нет)."""
    tpl = ROOT / "templates" / "tenant"
    names = ("site_schema.html", "_block_window.html", "_bw_*.html", "_schema_*.html")
    files = [p for name in names for p in tpl.glob(name)]
    assert len(files) > 5
    for path in [*files, *GOLDEN.glob("*.html")]:
        assert not re.search(r"role=[\"']tab", path.read_text()), path
