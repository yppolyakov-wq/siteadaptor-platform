"""FB-33 M5c (ревью C3–C4, 2026-11-23): без JS «Fertig» панели виден, пока панель стоит под
схемой (до 1280 px); счётчик черновика — не живая область внутри подменяемого узла.
"""

import re

import pytest

from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _draft_items

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _done_wrappers(html):
    """Обёртки «Fertig» в верху панели (форма `window_done` и ссылка без окна)."""
    panel = html[html.index('id="schema-panel"') :]
    return re.findall(r"<(?:form|p)\b[^>]*>(?:(?!</(?:form|p)>).)*?data-schema-done", panel, re.S)


def test_done_visible_until_column_layout():
    """MED django: колонка справа — с `xl` (1280); ниже без JS панель под схемой — «Fertig» сверху
    обязан быть виден (`xl:hidden`, не `md:hidden`), у обоих вариантов."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    ref = next(i["id"] for i in _draft_items(b, "text") if i.get("id"))
    wrappers = _done_wrappers(b.get(f"?seite=text&block={ref}"))
    wrappers += _done_wrappers(b.get("?seite=home&block=hero"))
    assert wrappers
    for w in wrappers:
        tag = w[: w.index(">") + 1]
        assert "xl:hidden" in tag and "md:hidden" not in tag, tag


def test_draft_note_is_not_a_live_region():
    """LOW a11y: узел счётчика подменяется целиком — его role=status не звучит; говорит
    постоянная `[data-schema-live]`."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    html = b.get("?seite=text")
    note = re.search(r"<p\b[^>]*data-schema-draft-note[^>]*>", html).group(0)
    assert "role=" not in note
    assert re.search(r'<p\b[^>]*role="status"[^>]*data-schema-live', html)
