"""FB-33 стопка 14 E3: вкладка «Wie anordnen» окна блока без скриптов не теряет набранное —
только у части `listview` (вид списка; решение владельца 2026-11-24, план
`docs/fb33-stack14-plan-2026-11-24.md` §0.1, §2 «E3», §4 «E3»).

Красные до кода: кнопки вкладок «Wie» с формой вида — кнопки этой формы (`zu_tab`), переход
применяет вид; у каждой применяющей части вкладки есть форма с её `form_id` (№14); кнопка по
умолчанию — `op=update` перед вкладками, у формы вида одна «Übernehmen», без `aria-hidden`
(a11y M5). Охранные: «Wie» у блоков без вида списка (FAQ, `usp_bar`, `cta`, `about`,
`testimonials`) — байт-в-байт со снимком до E3 (`golden_fb33e3/`, пересъёмка `FB33_E3_REGEN=1`);
`wie_nojs` галереи, команды, `t2`, `tr1`; отказ правки — остаёмся на «Wie».
"""

import copy
import os
import re
from pathlib import Path

import pytest
from django.utils import translation

from apps.core import aufbau_draft, block_window
from apps.core.tests import test_fb33_m3_3_nojs as m33
from apps.core.tests.form_post import form_post
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_2_nojs import _normalize
from apps.core.tests.test_fb33_m3_window_before import CASES as WINDOW_CASES
from apps.core.tests.test_fb33_m3_window_before import CFG as WINDOW_CFG
from apps.core.tests.test_fb33_m3_window_before import _capture, _panel

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_fb33e3"
LIST_FORM = "bw-form-listview"
LIST_QUERY = "?seite=home&block=l1&tab=wie"

#: блоки с видом на «Wie» своей частью `fields` (не `listview`) и полоса доверия
STYLE_REFS = ("faq", "usp_bar", "cta", "about", "testimonials")
STYLE_CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "usp_bar", "enabled": True},
        {"key": "faq", "enabled": True},
        {"key": "cta", "enabled": True},
        {"key": "about", "enabled": True},
        {"key": "testimonials", "enabled": True},
    ]
}


def _shop(cfg):
    tenant = _tenant()
    tenant.site_config = copy.deepcopy(cfg)
    tenant.save()
    return tenant


def _get(b, query):
    with translation.override("de"):
        return _panel(b.get(query))


def _nav(panel):
    at = panel.index("data-window-tabs")
    start = panel.rindex("</h2>", 0, at)
    return panel[start : panel.index("</nav>", at)]


def _list_form(panel):
    return re.search(rf'<form[^>]*id="{LIST_FORM}".*?</form>', panel, flags=re.S).group(0)


def _row(b, ref, code="home"):
    draft = ((b.session or {}).get(aufbau_draft.SESSION_KEY) or {}).get(code) or {}
    return next((r for r in draft.get("items") or [] if r.get("id") == ref), None)


def _tab_post(panel, **change):
    """Поля формы вида так, как их отправит браузер, плюс `bw_tabs` (поле вне формы с
    `form=`) и правка."""
    data, _parser = form_post(panel, LIST_FORM)
    tabs = re.search(
        rf'<input type="hidden" form="{LIST_FORM}" name="bw_tabs" value="([^"]*)">', panel
    )
    data["bw_tabs"] = [tabs.group(1)]
    for name, value in change.items():
        data[name] = [value]
    return data


def _default_button(panel, form):
    """Кнопка по умолчанию формы `form` (Enter в поле): первая кнопка отправки в порядке
    документа, чей владелец — эта форма (атрибут `form=` или вложенность без `form=`)."""
    spans = [
        (m.start(), m.end(), m.group(1))
        for m in re.finditer(r'<form\b[^>]*?(?:id="([^"]*)")?[^>]*>.*?</form>', panel, flags=re.S)
    ]
    for match in re.finditer(r"<button\b[^>]*>", panel):
        tag = match.group(0)
        if 'type="button"' in tag:
            continue
        owner = re.search(r'\bform="([^"]*)"', tag)
        if owner:
            mine = owner.group(1) == form
        else:
            inside = [s for s in spans if s[0] < match.start() < s[1]]
            mine = bool(inside) and inside[-1][2] == form
        if mine:
            return tag
    return ""


# --- красные: кнопки вкладок применяют форму вида --------------------------------------------


@pytest.mark.xfail(strict=True, reason="E3: «Wie» с формой вида — вкладки-ссылки")
def test_wie_tab_buttons_apply_listview():
    b = Browser(_shop(m33.CFG))
    panel = _get(b, LIST_QUERY)
    nav = _nav(panel)
    assert f'<form method="post" id="{LIST_FORM}"' in panel
    for other in ("was", "karte"):
        assert re.search(
            rf'<button type="submit" form="{LIST_FORM}" name="zu_tab" value="{other}"[^>]*>', nav
        ), other
    assert "data-window-hint" not in panel  # подсказка «Erst „Übernehmen“» уходит
    resp, msgs = b.post(**_tab_post(panel, f_cols="3", zu_tab="was"))
    assert resp.status_code == 302 and msgs == []
    loc = resp["Location"]
    assert "tab=was" in loc and "tab=wie" not in loc and loc.endswith("#schema-tab-was")
    assert str(_row(b, "l1")["data"]["cols"]) == "3"
    # тот же черновик, что у «Übernehmen» формы вида
    two = Browser(_shop(m33.CFG))
    data = _tab_post(_get(two, LIST_QUERY), f_cols="3", op="update")
    two.post(**data)
    first = copy.deepcopy(b.session[aufbau_draft.SESSION_KEY]["home"])
    second = copy.deepcopy(two.session[aufbau_draft.SESSION_KEY]["home"])
    for draft in (first, second):
        draft.pop("ts", None)
        draft.pop(aufbau_draft.WINDOW_KEY, None)  # токены окон разные
    assert first == second


@pytest.mark.xfail(strict=True, reason="E3: APPLY_TAB_PARTS ещё нет, у формы вида нет id")
def test_every_applying_part_of_a_tab_has_its_form():
    """№14: у каждой живой применяющей части (по вкладкам `APPLY_TAB_PARTS`) — форма с её
    `form_id`; вид списка среди них."""
    applying = {p for parts in block_window.APPLY_TAB_PARTS.values() for p in parts}
    assert block_window.APPLY_TABS == tuple(block_window.APPLY_TAB_PARTS)
    seen = set()
    for cfg, cases in ((WINDOW_CFG, WINDOW_CASES), (m33.CFG, m33.CASES)):
        b = Browser(_shop(cfg))
        for case in cases:
            code, ref, extra = (*case, "")[:3]
            extra = f"&{extra}" if extra and not extra.startswith("&") else extra
            html, view, selected = _capture(b, f"?seite={code}&block={ref}{extra}")
            if view["confirm_remove"]:
                continue
            panel = _panel(html)
            for part in block_window.parts(selected, view):
                if part in applying:
                    seen.add(part)
                    assert f'id="{block_window.form_id(part)}"' in panel, (case, part)
    assert {"fields", "usp", "listview"} <= seen


@pytest.mark.xfail(strict=True, reason="E3: кнопки по умолчанию у формы вида перед вкладками нет")
def test_default_submit_is_update():
    """a11y M5: Enter в поле формы вида — `op=update`, а не кнопка вкладки; кнопка по
    умолчанию — перед вкладками; у формы вида одна «Übernehmen», без `aria-hidden`."""
    b = Browser(_shop(m33.CFG))
    panel = _get(b, LIST_QUERY)
    default = _default_button(panel, LIST_FORM)
    assert f'form="{LIST_FORM}" name="op" value="update"' in default
    assert "data-window-default" in default
    at = panel.index("data-window-default")
    assert at < panel.index('name="zu_tab"') < panel.index(f'id="{LIST_FORM}"')
    form = _list_form(panel)
    assert len(re.findall(r'<button[^>]*value="update"', form)) == 1
    assert "aria-hidden" not in "".join(re.findall(r"<button\b[^>]*>", form))
    # Enter шлёт кнопку по умолчанию: правка, без перехода
    resp, msgs = b.post(**_tab_post(panel, f_cols="4", op="update"))
    assert msgs == [] and "tab=wie" in resp["Location"] and "tab=was" not in resp["Location"]
    assert str(_row(b, "l1")["data"]["cols"]) == "4"


# --- охранные --------------------------------------------------------------------------------


def _style_render(ref):
    b = Browser(_shop(STYLE_CFG))
    return _normalize(_get(b, f"?seite=home&block={ref}&tab=wie")) + "\n"


@pytest.mark.parametrize("ref", STYLE_REFS)
def test_wie_fields_style_tab_unchanged(ref):
    """Решение владельца: «Wie» у блоков без вида списка — байт-в-байт (снимок до E3)."""
    got = _style_render(ref)
    path = GOLDEN / f"wie_{ref}.html"
    if os.environ.get("FB33_E3_REGEN") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(got)
        pytest.fail("регенерация снимков — перезапусти без FB33_E3_REGEN")
    assert got == path.read_text(), path.name
    assert "zu_tab" not in got and "data-window-default" not in got


@pytest.mark.parametrize("case", [c for c in m33.CASES if c[1] != "l1"], ids="|".join)
def test_wie_without_listview_unchanged(case):
    assert m33._render(case) == (m33.GOLDEN / m33._name(case)).read_text()


def test_wie_refused_update_stays():
    """№7: отказ правки из формы вида кнопкой вкладки — остаёмся на «Wie», без перехода."""
    b = Browser(_shop(m33.CFG))
    panel = _get(b, LIST_QUERY)
    b.post(seite="home", ref="l1", op="delete")  # блок удалён в другой вкладке
    data = _tab_post(panel, f_cols="3", zu_tab="was") if LIST_FORM in panel else None
    if data is None:  # до E3 у формы вида нет id — поля вручную
        data = {
            "seite": "home",
            "ref": "l1",
            "panel_present": "1",
            "tab": "wie",
            "bw_tabs": "was wie karte",
            "f_cols": "3",
            "zu_tab": "was",
        }
    with translation.override("de"):
        resp, msgs = b.post(**data)
    loc = resp["Location"]
    assert msgs and "tab=wie" in loc and "tab=was" not in loc and loc.endswith("#schema-panel")
