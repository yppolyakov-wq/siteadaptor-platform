"""FB-33 M5c-3 (C2): «＋ Block» под выбранной строкой и в конце, кнопки типов из реестра одной
разметкой с JS и без, после вставки — окно нового блока с сообщением, «Fertig» — к строке.

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C2 и правки §8.1 (M1, M6, M7), §8.2 (B3, B4).
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.core import site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _draft_items, _order

pytestmark = pytest.mark.django_db
#: замок первого коммита: поведения ещё нет (снимается реализацией)
_red = pytest.mark.xfail(strict=True, reason="FB-33 M5c-3: «＋ Block» по C2 ещё нет")

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(n=2):
    b = Browser(_tenant())
    for _i in range(n):
        b.post(seite="text", op="add", type="text")
    return b


def _ids(b):
    return [i["id"] for i in _draft_items(b, "text") if i.get("id")]


def _adds(html):
    return re.findall(r"<details\b[^>]*data-schema-add\b.*?</details>", html, re.S)


def _query(resp):
    parts = urlsplit(resp["Location"])
    return parse_qs(parts.query), parts.fragment


@_red
def test_add_panel_from_registry():
    b = _browser(0)
    html = b.get("?seite=text")
    (box,) = _adds(html)
    types = re.findall(r'<button\b[^>]*name="type" value="([^"]+)"', box)
    rows = re.findall(r'<button\b[^>]*name="value" value="([^"]+)"', box)
    want = [k for g in site_schema.add_groups("text") for k, _lab in g["options"]]
    assert types == want
    assert rows == [k for k, _lab in site_schema.row_options()]
    assert "<select" not in box, "без выпадающего списка — кнопки (ответ владельца №2)"
    from django.utils.html import escape

    from apps.core import block_catalog

    hint = str(block_catalog.library_entry("text").hint)
    assert escape(hint) in box, "подсказка типа — из каталога блоков"


@_red
def test_add_after_last_in_row():
    b = Browser(_tenant())
    b.post(seite="text", op="add_row", value="text_image")
    a, c = _ids(b)
    html = b.get(f"?seite=text&block={a}")
    boxes = _adds(html)
    assert len(boxes) == 2
    under = boxes[0]
    afters = set(re.findall(r'name="after" value="([^"]+)"', under))
    assert afters == {c}, "после последнего блока ряда выбранного"
    assert 'name="after"' not in boxes[1], "в конце — без позиции"


def test_add_under_selected_inserts_there():
    b = _browser(3)
    a, m, c = _ids(b)
    resp, _msgs = b.post(seite="text", op="add", type="text", after=m)
    order = _order(_draft_items(b, "text"))
    new = _query(resp)[0]["block"][0]
    assert order.index(new) == order.index(m) + 1


def test_no_add_under_star_hint_hidden():
    b = _browser(2)
    a, _c = _ids(b)
    assert len(_adds(b.get("?seite=text"))) == 1, "ничего не выбрано — только в конце"
    assert len(_adds(b.get("?seite=text&block=__page"))) == 1, "под ★ — нет"
    b.post(seite="text", op="toggle", ref=a)
    assert len(_adds(b.get(f"?seite=text&block={a}"))) == 1, "под скрытой — нет"


@_red
def test_add_summary_names():
    b = _browser(2)
    a, _c = _ids(b)
    html = b.get(f"?seite=text&block={a}")
    sel, end = _adds(html)
    s1 = re.search(r"<summary\b[^>]*>(.*?)</summary>", sel, re.S).group(1)
    s2 = re.search(r"<summary\b[^>]*>(.*?)</summary>", end, re.S).group(1)
    assert re.search(r'<span class="sr-only">[^<]*einfügen nach „[^“]+“</span>', s1)
    assert '<span class="sr-only">am Ende einfügen</span>' in s2
    assert '<span aria-hidden="true">＋</span>' in s1 and '<span aria-hidden="true">＋</span>' in s2
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids))


@_red
def test_nojs_insert_opens_column():
    b = _browser(1)
    (a,) = _ids(b)
    resp, _m = b.post(seite="text", op="add", type="text", after=a)
    q, frag = _query(resp)
    new = q["block"][0]
    assert q["neu"] == [new] and frag == "schema-panel"
    html = b.get(f"?seite=text&block={new}&neu={new}")
    said = re.search(r"<p\b[^>]*data-schema-inserted[^>]*>(.*?)</p>", html, re.S)
    assert said, "сообщение о вставке — в панели нового блока"
    assert re.fullmatch(
        r"Block „[^“]+“ eingefügt, Nummer 2\. Der Block bleibt — entfernen über „⋯“\.",
        said.group(1).strip(),
    )
    assert 'value="window_done"' in html


def test_neu_whitelist():
    b = _browser(2)
    a, c = _ids(b)
    assert "data-schema-inserted" not in b.get(f"?seite=text&block={a}&neu=junk")
    assert "data-schema-inserted" not in b.get(f"?seite=text&block={a}&neu={c}")


@_red
def test_insert_status_ru():
    b = _browser(1)
    (a,) = _ids(b)
    with translation.override("ru"):
        html = b.get(f"?seite=text&block={a}&neu={a}")
    said = re.search(r"<p\b[^>]*data-schema-inserted[^>]*>(.*?)</p>", html, re.S).group(1)
    assert "eingefügt" not in said and re.search(r"[а-я]", said)


@_red
def test_window_done_returns_to_row():
    b = _browser(1)
    (a,) = _ids(b)
    resp, _m = b.post(seite="text", op="window_done", ref=a)
    assert _query(resp)[1] == f"schema-row-{a}"
    html = b.get("?seite=text")
    assert re.search(rf'<a\b[^>]*id="schema-row-{a}"[^>]*data-schema-gear="{a}"', html)


def test_insert_status_queries():
    b = _browser(2)
    a, _c = _ids(b)
    b.get(f"?seite=text&block={a}")
    with CaptureQueriesContext(connection) as plain:
        b.get(f"?seite=text&block={a}")
    with CaptureQueriesContext(connection) as fresh:
        b.get(f"?seite=text&block={a}&neu={a}")
    assert len(fresh) == len(plain)


NEW_MSGIDS = (
    "einfügen nach „%(name)s“",
    "am Ende einfügen",
    "Block „%(name)s“ eingefügt, Nummer %(n)s. Der Block bleibt — entfernen über „⋯“.",
)


@_red
def test_new_msgids_in_all_po():
    for po in sorted((ROOT / "locale").glob("*/LC_MESSAGES/django.po")):
        cat = {(e.msgctxt, e.msgid): e for e in polib.pofile(str(po))}
        lang = po.parts[-3]
        for msgid in NEW_MSGIDS:
            entry = cat.get((None, msgid))
            assert entry is not None, (lang, msgid)
            assert lang == "de" or entry.msgstr, (lang, msgid)
