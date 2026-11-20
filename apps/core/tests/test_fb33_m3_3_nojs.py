"""FB-33 M3-3abc: вкладка «Wie anordnen» без скриптов — эталон панели окна блока
(`golden_fb33m3/wie_nojs/`). Новые случаи сверх M3-2: виды Team/Galerie картинками, ссылочный
блок Team, список со своими колонками (строка наследования и «zurücksetzen»), узкий блок в
ряду («Platz» → «Reihe»). Случайное (CSRF, токен окна) нормализуется. Пересъёмка —
`FB33_M33_REGEN=1`."""

import os
from pathlib import Path

import pytest
from django.utils import translation

from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_2_nojs import _normalize
from apps.core.tests.test_fb33_m3_window_before import _panel

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_fb33m3" / "wie_nojs"

CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "team", "enabled": True, "style": "circles"},
        {"key": "gallery", "enabled": True},
        {"key": "text", "id": "t1", "enabled": True, "width": "w12",
         "data": {"title": "Hallo", "body": "Welt"}},
        {"key": "text", "id": "t2", "enabled": True, "width": "w13",
         "data": {"title": "Daneben", "body": "Text"}},
        {"key": "list", "id": "l1", "enabled": True,
         "data": {"source": "products", "cols": 2, "out": "grid"}},
    ],
    "page_blocks": {"info": [{"key": "team_ref", "id": "tr1", "enabled": True}]},
}  # fmt: skip

CASES = (
    ("home", "team", "tab=wie"),  # вид секции Team картинками (свой вид)
    ("home", "gallery", "tab=wie"),  # Galerie — «Standard»
    ("text", "tr1", "tab=wie"),  # ссылочный блок Team — честно «Standard»
    ("home", "l1", "tab=wie"),  # список со своими колонками: строка наследования и сброс
    ("home", "t2", "tab=wie"),  # узкий блок в ряду: «Platz» → «Reihe», «Eigene Reihe»
)


def _name(case) -> str:
    return "_".join(case).replace("=", "-") + ".html"


def _render(case) -> str:
    code, ref, extra = case
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    with translation.override("de"):
        html = Browser(tenant).get(f"?seite={code}&block={ref}&{extra}")
    return _normalize(_panel(html)) + "\n"


@pytest.mark.parametrize("case", CASES, ids=["|".join(c) for c in CASES])
def test_wie_tab_without_js_is_byte_for_byte_the_same(case):
    got = _render(case)
    path = GOLDEN / _name(case)
    if os.environ.get("FB33_M33_REGEN") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(got)
        pytest.fail("регенерация эталонов — перезапусти без FB33_M33_REGEN")
    assert got == path.read_text(), path.name


def test_golden_covers_every_case_and_nothing_else():
    assert sorted(p.name for p in GOLDEN.glob("*.html")) == sorted(_name(c) for c in CASES)


def test_wie_tab_is_open_and_has_the_new_parts():
    team, ref, look, narrow = (_render(c) for c in (CASES[0], CASES[2], CASES[3], CASES[4]))
    assert 'data-window-tab="wie" tabindex="-1"' in team
    assert 'data-schema-view-tiles="style"' in team and 'data-schema-view-tiles="style"' in ref
    assert "data-schema-listview" in look and "data-schema-view-reset" in look
    assert "data-schema-reihe" in narrow and "data-schema-platz" in narrow
