"""FB-33 M5c-2 (C1): строки схемы — номер, одна ссылка ⚙ на строку (растянутая), «⋯» у каждой
строки одним партиалом, ⠿ вне ссылки и без фокуса, номер в заголовке окна, сообщение после
перестановки из «⋯» строки.

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C1 и правки §8.1 (H2, M3–M6), §8.2 (A1, A2, B1,
B2, B4, B6).
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import polib
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.core import aufbau_draft, block_window, detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _draft_items, _order
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/tenant/site_schema.html"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(n=3):
    """Магазин, страница «Über uns» (`text`) с n своими блоками в черновике."""
    b = Browser(_tenant())
    for _i in range(n):
        b.post(seite="text", op="add", type="text")
    return b


def _ids(b):
    return [i["id"] for i in _draft_items(b, "text") if i.get("id")]


def _map(html):
    start = html.index("data-schema-map")
    return html[start : html.index("</section>", start)]


def _lines(html):
    m = re.search(r"<ol\b[^>]*data-schema-lines[^>]*>(.*?)</ol>", html, re.S)
    assert m, "строки блоков — в <ol>"
    return m.group(1)


def _rowbox(html, ref):
    at = html.index(f'data-schema-gear="{ref}"')
    start = html.rindex("data-schema-rowbox", 0, at)
    start = html.rindex("<div", 0, start)
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            i = start + m.end()
            break
    return html[start : html.index(">", i) + 1]


def _query(resp):
    parts = urlsplit(resp["Location"])
    return parse_qs(parts.query), parts.fragment


# --- номера ------------------------------------------------------------------------------------


def test_numbers_follow_layout():
    a, b, c, d = (
        {"ref": r, "enabled": True, "width": "", "newline": False, "shared": r == "s"}
        for r in ("a", "s", "c", "d")
    )
    hidden = {"ref": "h", "enabled": False, "width": "", "newline": False}
    layout = site_schema.schema_layout([a, b, c, hidden, d])
    assert site_schema.row_numbers(layout) == {"a": 1, "c": 2, "d": 3}


def test_rows_are_ol_numbers_match():
    b = _browser(3)
    html = b.get("?seite=text")
    lines = _lines(html)
    nums = re.findall(r'<span class="schema-num" aria-hidden="true">(\d+)</span>', lines)
    assert nums == [str(n) for n in range(1, len(nums) + 1)] and len(nums) >= 3
    assert "__page" not in lines and "data-schema-title-hint" not in lines.split("<ul")[0]


def test_number_aria_hidden():
    html = _browser(1).get("?seite=text")
    spans = re.findall(r'<span class="schema-num"[^>]*>', html)
    assert spans
    for span in spans:
        assert 'aria-hidden="true"' in span


def test_window_by_ref_not_number():
    b = _browser(3)
    ids = _ids(b)
    html = b.get(f"?seite=text&block={ids[1]}")
    title = re.search(r'<h2 id="schema-panel-title"[^>]*>(.*?)</h2>', html, re.S).group(1)
    num = re.search(
        rf'<span class="schema-num" aria-hidden="true">(\d+)</span>(?:(?!data-schema-gear=).)*'
        rf'data-schema-gear="{ids[1]}"',
        _lines(html),
        re.S,
    ).group(1)
    assert f'<span class="sr-only">Block {num}: </span>' in title
    assert f'<span class="schema-num" aria-hidden="true">{num}</span>' in title


# --- одна ссылка на строку ----------------------------------------------------------------------


def test_row_single_link():
    b = _browser(2)
    ref = _ids(b)[0]
    html = b.get("?seite=text")
    box = _rowbox(html, ref)
    # ссылки в Tab-порядке строки: «Entfernen …» — внутри закрытого «⋯», не стоп строки
    links = re.findall(r"<a\b[^>]*>", re.sub(r"<details\b.*?</details>", "", box, flags=re.S))
    assert len(links) == 1, links
    gear = links[0]
    assert f'data-schema-block="{ref}"' in gear and f'data-schema-gear="{ref}"' in gear
    assert 'aria-label="Einstellungen: ' in gear
    for desc in re.search(r'aria-describedby="([^"]+)"', gear).group(1).split():
        assert f'id="{desc}"' in box


def test_gear_no_title():
    html = _browser(1).get("?seite=text")
    gears = re.findall(r"<a\b[^>]*data-schema-gear[^>]*>", html)
    assert gears
    for gear in gears:
        assert " title=" not in gear


def test_selected_row_aria_current():
    b = _browser(2)
    ref = _ids(b)[0]
    html = b.get(f"?seite=text&block={ref}")
    gear = re.search(rf'<a\b[^>]*data-schema-gear="{ref}"[^>]*>', html).group(0)
    assert 'aria-current="true"' in gear


def test_grip_not_focusable():
    html = _browser(2).get("?seite=text")
    grips = re.findall(r"<span\b[^>]*schema-grip[^>]*>", html)
    assert grips
    for g in grips:
        assert 'aria-hidden="true"' in g and "tabindex" not in g
    for a in re.findall(r"<a\b.*?</a>", _map(html), re.S):
        assert "schema-grip" not in a, "⠿ — не внутри ссылки"


def test_grip_hidden_no_display_class():
    html = _browser(2).get("?seite=text")
    for g in re.findall(r"<span\b[^>]*schema-grip[^>]*>", html):
        cls = re.search(r'class="([^"]*)"', g).group(1).split()
        assert "hidden" in cls, "видимость ⠿ — только классом"
        assert not re.search(r"\shidden(\s|>|=)", g.replace(f'class="{" ".join(cls)}"', ""))
        assert not {"flex", "inline-flex", "block", "inline-block"} & set(cls)


# --- «⋯» строки -----------------------------------------------------------------------------------


def test_more_single_partial():
    src = TEMPLATE.read_text()
    row = (ROOT / "templates/tenant/_schema_row.html").read_text()
    assert 'include "tenant/_schema_row.html"' in src
    assert src.count('include "tenant/_schema_more.html"') == 1, "шапка окна"
    assert row.count('include "tenant/_schema_more.html"') == 1, "строка схемы"
    assert "data-schema-more>" not in src + row and 'data-schema-more"' not in src + row, (
        "«⋯» — только партиалом"
    )


def test_more_summary_no_haspopup():
    b = _browser(2)
    ref = _ids(b)[0]
    html = b.get("?seite=text")
    box = _rowbox(html, ref)
    summary = re.search(r"<summary\b[^>]*>(.*?)</summary>", box, re.S)
    assert summary and "aria-haspopup" not in summary.group(0)
    assert f'id="schema-more-{ref}"' in summary.group(0)
    assert '<span aria-hidden="true">⋯</span>' in summary.group(1)
    assert re.search(r'<span class="sr-only">Weitere Aktionen: [^<]+</span>', summary.group(1))


def test_can_hide_from_blocks_for():
    cfg = siteconfig.normalize({})
    rows = {r["ref"]: r for r in site_schema.blocks_for(cfg, "product")}
    assert rows[detail_parts.KAUF_REF]["can_hide"] is False
    cart = {r["ref"]: r for r in site_schema.blocks_for(cfg, "cart")}
    assert not any(cart[k]["can_hide"] for k in ("items", "form", "summary") if k in cart)
    cat = {r["ref"]: r for r in site_schema.blocks_for(cfg, "catalog")}
    assert cat["main"]["can_hide"] is False
    assert "can_hide" in block_window.ROW_KEYS


@pytest.mark.parametrize("code", ["home", "text", "catalog", "cart", "product", "event"])
def test_more_actions_match_mutate(code):
    """M3: «⋯» строки предлагает «Ausblenden» ровно там, где его примет `mutate`."""
    tenant = TenantFactory()  # все модули — все типы страниц
    cfg = siteconfig.normalize(tenant.site_config)
    _pt, host, home = site_schema.resolve(tenant, code)
    items = site_schema.load_items(cfg, home, host)
    if detail_parts.module_of(host):
        items = detail_parts.edit_rows(cfg, host, items)
    for row in site_schema.blocks_for(cfg, code, host=host):
        trial = [dict(i) for i in items]
        try:
            site_schema.mutate(trial, code, "toggle", ref=row["ref"])
            ok = True
        except site_schema.SchemaError:
            ok = False
        assert row["can_hide"] == ok, (code, row["ref"])


def test_more_absent_without_actions():
    html = Browser(_tenant()).get("?seite=product")
    box = _rowbox(html, detail_parts.KAUF_REF)
    assert "data-schema-more" not in box, "строке без действий «⋯» не рисуется"


def test_no_duplicate_ids():
    b = _browser(3)
    ref = _ids(b)[1]
    html = b.get(f"?seite=text&block={ref}")
    ids = re.findall(r'\sid="([^"]+)"', html)
    dup = {i for i in ids if ids.count(i) > 1}
    assert not dup, dup


def test_row_more_nojs_post():
    b = _browser(3)
    a, m, c = _ids(b)
    html = b.get(f"?seite=text&block={a}&wopen=TOKa1&tab=karte")
    box = _rowbox(html, m)
    form = re.search(r"<form\b.*?</form>", box, re.S).group(0)
    assert 'name="zeile" value="1"' in form and f'name="ref" value="{m}"' in form
    assert 'name="wopen"' not in form and 'name="tab"' not in form
    b.post(seite="text", op="down", ref=m, zeile="1")
    assert _ids(b) == [a, c, m]


def test_row_more_redirect_no_block():
    b = _browser(3)
    a, m, _c = _ids(b)
    resp, _msgs = b.post(seite="text", op="up", ref=m, zeile="1", wopen="TOKa1", tab="karte")
    q, frag = _query(resp)
    assert "block" not in q and "wopen" not in q and "tab" not in q
    assert q["bewegt"] == [m] and frag == f"schema-more-{m}"


def test_row_more_no_window_snapshot():
    """H2: форма строки не продолжает чужое окно — снимка «Abbrechen» по её токену нет."""
    b = _browser(3)
    _a, m, _c = _ids(b)
    b.post(seite="text", op="up", ref=m, zeile="1", wopen="TOKb1")
    req = type("R", (), {"session": b.session})()
    window = (aufbau_draft._raw(req, "text") or {}).get(aufbau_draft.WINDOW_KEY) or {}
    assert m not in window, window


def test_hide_from_row_focuses_show_button():
    b = _browser(2)
    a, _c = _ids(b)
    resp, _m = b.post(seite="text", op="toggle", ref=a, zeile="1")
    q, frag = _query(resp)
    assert frag == f"schema-more-{a}", "фокус — «Einblenden» этой строки"
    html = b.get(f"?seite=text&bewegt={a}")
    hidden = html[html.index("data-schema-hidden") :]
    assert re.search(r"<details\b[^>]*data-schema-hidden[^>]*\sopen", html)
    button = re.search(rf'<button\b[^>]*id="schema-more-{a}"[^>]*>', hidden)
    assert button and 'value="toggle"' in button.group(0)


def test_moved_status():
    b = _browser(3)
    a, m, _c = _ids(b)
    b.post(seite="text", op="up", ref=m, zeile="1")
    order = _order(_draft_items(b, "text"))
    assert order.index(m) < order.index(a)
    html = b.get(f"?seite=text&bewegt={m}")
    said = re.search(r"<p\b[^>]*data-schema-moved[^>]*>(.*?)</p>", html, re.S)
    assert said and re.fullmatch(r"Block „[^“]+“ ist jetzt Nummer \d+ von \d+\.", said.group(1))
    assert "data-schema-moved" not in b.get("?seite=text&bewegt=nope")


def test_moved_status_ru():
    b = _browser(2)
    a, c = _ids(b)
    b.post(seite="text", op="up", ref=c, zeile="1")
    with translation.override("ru"):
        html = b.get(f"?seite=text&bewegt={c}")
    said = re.search(r"<p\b[^>]*data-schema-moved[^>]*>(.*?)</p>", html, re.S).group(1)
    assert "ist jetzt" not in said and re.search(r"[а-я]", said)


def test_move_status_queries():
    b = _browser(3)
    _a, m, _c = _ids(b)
    b.get("?seite=text")
    with CaptureQueriesContext(connection) as plain:
        b.get("?seite=text")
    with CaptureQueriesContext(connection) as moved:
        b.get(f"?seite=text&bewegt={m}")
    assert len(moved) == len(plain)


NEW_MSGIDS = (
    "Einstellungen: %(name)s",
    "Weitere Aktionen: %(name)s",
    "Block %(n)s:",
    "Block „%(name)s“ ist jetzt Nummer %(n)s von %(total)s.",
)


def test_new_msgids_in_all_po():
    for po in sorted((ROOT / "locale").glob("*/LC_MESSAGES/django.po")):
        cat = {(e.msgctxt, e.msgid): e for e in polib.pofile(str(po))}
        lang = po.parts[-3]
        for msgid in NEW_MSGIDS:
            entry = cat.get((None, msgid))
            assert entry is not None, (lang, msgid)
            assert lang == "de" or entry.msgstr, (lang, msgid)
    assert (
        "Block „%(name)s“ verschieben" not in (ROOT / "locale/de/LC_MESSAGES/django.po").read_text()
    )
