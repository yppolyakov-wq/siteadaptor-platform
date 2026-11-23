"""FB-33 M5c-5 (C4): раскладка «Seitenaufbau» без JS, на телефоне и при окне-диалоге.

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C4, §4 C4, правки §8.1 L (оба узла черновика в
липкой полосе, флаг одной колонки — правилом `app.css` по атрибуту, снимается в `closeWindow`),
§8.2 A3 (2.4.11 / 1.4.10: `scroll-padding-bottom` = высота полосы, нижний отступ страницы,
липкая только при `(max-width: 47.99rem) and (min-height: 30rem)`), ответ владельца 10 (без JS
ниже 1280 px окно — под схемой, не листом поверх).
"""

import re
from pathlib import Path

import pytest

from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _draft_items

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
APP_CSS = ROOT / "static/src/app.css"
AUFBAU_JS = ROOT / "static/js/aufbau.js"
PHONE = "@media (max-width: 47.99rem) and (min-height: 30rem)"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.LANGUAGE_CODE = "de"


def _aside(html: str) -> str:
    return re.search(r"<aside\b[^>]*data-schema-panel[^>]*>", html).group(0)


def _bar(html: str) -> str | None:
    m = re.search(r"<div\b[^>]*data-schema-draftbar\b.*?</form>\s*</div>", html, re.S)
    return m.group(0) if m else None


def _media(css: str, head: str) -> str:
    """Тела всех блоков `@media` с этим заголовком (вложенность — одна пара скобок)."""
    out, i = [], 0
    while (i := css.find(head, i)) != -1:
        j = css.index("{", i) + 1
        depth, k = 1, j
        while depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        out.append(css[j : k - 1])
        i = k
    return "\n".join(out)


def _selected(b):
    ref = [i["id"] for i in _draft_items(b, "text") if i.get("id")][-1]
    return b.get(f"?seite=text&block={ref}")


def test_nojs_panel_below_schema():
    """Без JS ниже 1280 px панель выбранного блока — под схемой (одна колонка сетки), не лист."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    html = _selected(b)
    aside = _aside(html)
    assert 'id="schema-panel"' in aside and "data-schema-panel" in aside
    assert "fixed" not in aside and "max-h-[60dvh]" not in aside, aside
    grid = re.search(r"<div\b[^>]*data-site-schema[^>]*>", html).group(0)
    assert "grid-cols-1" in grid and "xl:grid-cols-[minmax(0,1fr)_20rem]" in grid
    # порядок атрибутов `<aside … id … data-schema-panel>` — как прежде (замок M3-2)
    assert aside.index('id="schema-panel"') < aside.index("data-schema-panel")


def test_draft_bar_only_with_draft():
    b = Browser(_tenant())
    assert "data-schema-draftbar" not in b.get("?seite=text"), "без черновика полосы нет"
    b.post(seite="text", op="add", type="text")
    html = b.get("?seite=text")
    assert html.count("data-schema-draftbar") == 1
    bar = _bar(html)
    assert bar, "текст «Entwurf · …» и форма — в одной полосе"
    assert "data-schema-draft-note" in bar and "data-schema-draft" in bar
    assert 'value="discard"' in bar and 'value="save"' in bar
    status = html[html.index("data-schema-status") :]
    assert status.index("data-schema-draftbar") < status.index("data-schema-live"), (
        "полоса — внутри [data-schema-status] (автосохранение подменяет её целиком)"
    )


def test_draft_bar_sticky_only_on_tall_phone():
    css = APP_CSS.read_text()
    body = _media(css, PHONE)
    assert body, "липкая полоса — только при узком И не низком экране"
    rule = re.search(r"\[data-schema-draftbar\]\s*\{([^}]*)\}", body)
    assert rule and "position: fixed" in rule.group(1)
    assert "env(safe-area-inset-bottom)" in body
    assert re.search(r"scroll-padding-bottom:[^;]*var\(--schema-draft-h", body), "2.4.11"
    assert re.search(
        r"padding-bottom:[^;]*var\(--schema-draft-h", body.replace("scroll-padding-bottom", "")
    ), "нижний отступ страницы — последняя строка не уходит под полосу"
    outside = css.replace(body, "")
    assert not re.search(r"\[data-schema-draftbar\]\s*\{[^}]*position:\s*fixed", outside)


def test_solo_flag_rule_in_css():
    css = APP_CSS.read_text()
    rule = re.search(r"\[data-site-schema\]\[data-schema-solo\]\s*\{([^}]*)\}", css)
    assert rule, "одна колонка при окне-диалоге — правилом app.css по атрибуту"
    assert "grid-template-columns: minmax(0, 1fr)" in rule.group(1)
    assert "max-width: 760px" in rule.group(1) and "margin-inline: auto" in rule.group(1)


def test_solo_flag_set_and_cleared_in_js():
    js = AUFBAU_JS.read_text()
    dress = js[js.index("function dress()") : js.index("function tabLinks()")]
    close = js[js.index("function closeWindow()") : js.index("window.aufbauWindow =")]
    assert 'setAttribute("data-schema-solo"' in dress, "флаг ставит панель в окне (dress)"
    # ревью C3–C4: снятие флага — одна функция `unsolo` (closeWindow, close диалога, загрузка)
    unsolo = js[js.index("function unsolo()") : js.index("function closeWindow()")]
    assert 'removeAttribute("data-schema-solo")' in unsolo
    assert "unsolo();" in close, "флаг снимает closeWindow"
    # путь dress() без окна уходит в closeWindow — флаг снимается там же
    head = dress[: dress.index('setAttribute("data-schema-solo"')]
    assert "closeWindow();" in head


def test_draft_bar_height_measured():
    js = AUFBAU_JS.read_text()
    assert "--schema-draft-h" in js, "скрипт ставит реальную высоту полосы (перенос, крупный шрифт)"
