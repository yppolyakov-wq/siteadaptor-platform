"""FB-33 M3-0: замки до кода окна блока (`docs/fb33-editor-model-2026-11-19.md` §«План M3»).

Окно блока — только раскладка прежней панели «Seitenaufbau» по вкладкам. Снимок ДО кода:
у типичных строк (секция, C-блок, ссылочный блок, ★-строка, закреплённая, баннер, строка
страницы) — какие части контекста панели непустые, какие операции панель предлагает и формы
панели целиком (без токена CSRF). После раскладки формы те же байт-в-байт: правка из окна
даёт тот же черновик, что из старой панели. Пересъёмка — `FB33_M3_REGEN=1`.
"""

import json
import os
import re
from pathlib import Path

import pytest
from django.test.signals import template_rendered

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_fb33m3" / "panel.json"

CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "usp_bar", "enabled": True},
        {"key": "faq", "enabled": True},
        {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Hallo", "body": "Welt"}},
        {"key": "button", "id": "bt1", "enabled": True, "data": {"label": "Los", "url": "/x"}},
        {"key": "list", "id": "l1", "enabled": True, "data": {"source": "products"}},
        {"key": "quick_links", "id": "quicklinks", "enabled": True, "data": {"set": "visit"}},
    ],
    "page_blocks": {
        "info": [
            {"key": "faq_ref", "id": "f1", "enabled": True},
            {"key": "textpage", "id": "tp1", "enabled": True, "data": {}},
            {"key": "banner", "id": "bn1", "enabled": True},
        ]
    },
}

#: (страница, строка[, доп. запрос]) — по одной на каждый вид панели
CASES = (
    ("home", "hero"),  # баннер главной: носитель настроек страницы
    ("home", "usp_bar"),  # пункты полосы доверия
    ("home", "faq"),  # секция главной со своим видом
    ("home", "t1"),  # C-блок: тексты, смена вида, ширина
    ("home", "t1", "&entfernen=1"),  # подтверждение удаления
    ("home", "bt1"),  # кнопка
    ("home", "l1"),  # блок «Liste»
    ("home", "quicklinks"),  # набор плиток
    ("home", "products"),  # встроенный список главной
    ("catalog", "main"),  # ★-строка: вид товаров и настройки типа
    ("catalog", "categories"),  # вид категорий
    ("product", "related"),  # раздел со своими настройками
    ("product", "__kauf"),  # закреплённая «Kaufen»
    ("cart", "summary"),  # закреплённый итог (§ 312j)
    ("promos", "__title"),  # «Seitentitel»
    ("promos", "groups"),  # вид групп акций
    ("text", "pagetext"),  # закреплённый текст страницы
    ("text", "f1"),  # ссылочный блок FAQ
    ("text", "tp1"),  # «Von einer Seite»
    ("text", "bn1"),  # баннер страницы: выбор из библиотеки
    ("text", "__page"),  # строка «Einstellungen der Seite»
)


def _capture(browser, query):
    seen = []

    def grab(sender, template, context, **kw):
        if getattr(template, "name", "") == "tenant/site_schema.html":
            seen.append(context)

    template_rendered.connect(grab)
    try:
        html = browser.get(query)
    finally:
        template_rendered.disconnect(grab)
    ctx = seen[-1]
    return html, {k: ctx.get(k) for k in _VIEW_KEYS}, ctx.get("selected") or {}


#: части панели, которые вьюха кладёт рядом с выбранной строкой
_VIEW_KEYS = (
    "page_row",
    "settings",
    "design_rows",
    "confirm_remove",
    "beside_target",
    "selected_in_row",
    "width_mates",
)


def _panel(html: str) -> str:
    at = html.index('id="schema-panel"')
    start = html.rindex("<aside", 0, at)
    return html[start : html.index("</aside>", at)]


def _forms(panel: str) -> list[str]:
    out = []
    for form in re.findall(r"<form\b.*?</form>", panel, flags=re.S):
        form = re.sub(r'<input type="hidden" name="csrfmiddlewaretoken"[^>]*>', "", form)
        out.append(re.sub(r"\s+", " ", form).strip())
    return sorted(out)


def _ops(panel: str) -> list[str]:
    ops = re.findall(r'name="op" value="([^"]+)"', panel)
    ops += re.findall(r'name="op"[^>]*value="([^"]+)"', panel)
    return sorted(set(ops))


def _nonempty(selected: dict) -> list[str]:
    return sorted(k for k, v in selected.items() if v not in (None, "", [], {}, (), False))


def snapshot() -> dict:
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    out = {}
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        b = Browser(tenant)
        html, view, selected = _capture(b, f"?seite={code}&block={ref}{extra}")
        panel = _panel(html)
        out["|".join(case)] = {
            "selected": _nonempty(selected),
            "view": sorted(k for k, v in view.items() if v not in (None, "", [], {}, False)),
            "ops": _ops(panel),
            "forms": _forms(panel),
        }
    return out


def test_panel_parts_ops_and_forms_are_unchanged():
    got = snapshot()
    if os.environ.get("FB33_M3_REGEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    want = json.loads(GOLDEN.read_text())
    assert sorted(got) == sorted(want)
    for case, snap in want.items():
        for part in ("selected", "view", "ops", "forms"):
            assert got[case][part] == snap[part], f"{case}: {part}"


def test_every_case_opens_a_block():
    """Снимок осмыслен: каждая строка открывает панель блока, а не «Block wählen»."""
    want = json.loads(GOLDEN.read_text())
    for case, snap in want.items():
        assert snap["selected"] or "page_row" in snap["view"], case


def test_opening_and_closing_without_an_edit_keeps_no_draft():
    tenant = _tenant()
    tenant.site_config = CFG
    tenant.save()
    b = Browser(tenant)
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        b.get(f"?seite={code}&block={ref}{extra}")
        b.get(f"?seite={code}&block={ref}&tab=texte")
        b.get(f"?seite={code}")
        assert aufbau_draft.dirty_codes(_Req(b.session)) == [], case


class _Req:
    def __init__(self, session):
        self.session = session
