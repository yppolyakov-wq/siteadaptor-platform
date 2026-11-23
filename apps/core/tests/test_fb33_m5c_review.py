"""FB-33 M5c (ревью C0–C2, 2026-11-23): правка строкой сбрасывает снимок окна этого блока,
якорь редиректа экранирован, позиция вставки и параметры GET не попадают в ответ как есть.

Находки — `docs/fb33-stack11-plan-2026-11-23.md` (ревью C0–C2: django L3, security LOW).
"""

from urllib.parse import parse_qs, quote, urlsplit

import pytest

from apps.core import aufbau_draft, detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m5c0_insert import _blk, _draft_items, _order

pytestmark = pytest.mark.django_db
#: замок первого коммита: поведения ещё нет (снимается реализацией)
_red = pytest.mark.xfail(strict=True, reason="FB-33 M5c ревью C0–C2: правки ещё нет")


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


def _item(b, ref):
    return next(i for i in _draft_items(b, "text") if i.get("id") == ref)


@_red
def test_row_edit_drops_window_snapshot():
    """L3: правка в окне → «⋯ Ausblenden» строкой → «Abbrechen» окна — блок остаётся скрытым
    (снимок окна этого блока снят правкой строки, «Abbrechen» не откатывает её молча)."""
    b = _browser(2)
    a, _c = _ids(b)
    b.post(seite="text", op="update", ref=a, wopen="TOKa1", panel_present="1", f_title="Neu")
    req = type("R", (), {"session": b.session})()
    assert a in ((aufbau_draft._raw(req, "text") or {}).get(aufbau_draft.WINDOW_KEY) or {})
    b.post(seite="text", op="toggle", ref=a, zeile="1")
    assert _item(b, a).get("enabled") is False
    b.post(seite="text", op="revert", ref=a, wopen="TOKa1")
    assert _item(b, a).get("enabled") is False, "скрытие строкой не откатилось молча"


def test_row_redirect_is_relative_and_quoted():
    b = _browser(2)
    a, _c = _ids(b)
    resp, _m = b.post(seite="text", op="up", ref=_ids(b)[1], zeile="1")
    loc = resp["Location"]
    assert loc.startswith("/") and "//" not in loc.split("?")[0]
    parts = urlsplit(loc)
    ref = parse_qs(parts.query)["bewegt"][0]
    assert parts.fragment == f"schema-more-{quote(ref, safe='')}"
    resp, _m = b.post(seite="text", op="toggle", ref="x&y<z>", zeile="1")
    assert "x&y" not in resp["Location"] and "<z>" not in resp["Location"]


@pytest.mark.parametrize("after", ["a" * 65, "nope"])
def test_bad_after_refused_items_unchanged(after):
    b = _browser(1)
    before = _order(_draft_items(b, "text"))
    resp, msgs = b.post(seite="text", op="add", type="text", after=after)
    assert _order(_draft_items(b, "text")) == before
    assert "block" not in parse_qs(urlsplit(resp["Location"]).query)
    assert any("nicht möglich" in m for m in msgs)


@pytest.mark.parametrize("key", ["bewegt", "neu", "zuletzt"])
def test_get_params_not_reflected(key):
    b = _browser(1)
    (a,) = _ids(b)
    probe = "<script>alert(1)</script>"
    html = b.get(f"?seite=text&block={a}&{key}={quote(probe)}")
    assert probe not in html and "alert(1)" not in html


def test_insert_after_kauf_first_goes_to_top():
    """L4: «Kaufen» в первом экране — вставка «после» неё = в начало (как бросок)."""
    items = detail_parts.edit_rows({}, "product_detail", [_blk("a")])
    new = site_schema.mutate(
        items, "product", "add", block_type="text", after=detail_parts.KAUF_REF
    )
    assert _order(items)[0] == new


@_red
def test_insert_checks_pinned_order(monkeypatch):
    """L4: вставка проверяет порядок неподвижных строк той же функцией, что и бросок."""
    seen = []
    real = site_schema.place_item

    def spy(*args, **kwargs):
        seen.append(kwargs.get("before"))
        return real(*args, **kwargs)

    monkeypatch.setattr(site_schema, "place_item", spy)
    items = [{"key": "items"}, {"key": "form"}, {"key": "summary"}, _blk("t")]
    site_schema.mutate(items, "cart", "add", block_type="text", after="t")
    assert seen and seen[0] is not None, "place_item получает копию списка до вставки"
