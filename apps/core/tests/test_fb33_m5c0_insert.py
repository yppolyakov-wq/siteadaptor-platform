"""FB-33 M5c-1 (C0): вставка блока в позицию — поле `after` (не `value`), одна логика позиции
с перетаскиванием (`site_schema.place_item`), атомарный откат, свежий токен окна после вставки.

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C0 и правки §8.1 (H1, M2, L1–L2).
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core import aufbau_draft, detail_parts, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
#: замок первого коммита: поведения ещё нет (снимается реализацией C0)
_red = pytest.mark.xfail(strict=True, reason="FB-33 M5c-1: вставки в позицию ещё нет")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _blk(i, key="text"):
    return {"key": key, "id": i, "enabled": True, "data": {}}


def _order(items):
    return [i.get("id") or i["key"] for i in items]


def _new(items, before):
    old = {i.get("id") for i in before}
    return [i["id"] for i in items if i.get("id") and i["id"] not in old]


def _draft_items(b, code):
    req = type("R", (), {"session": b.session})()
    return (aufbau_draft._raw(req, code) or {}).get("items") or []


def _query(resp):
    return parse_qs(urlsplit(resp["Location"]).query)


# --- №2: одна логика позиции -----------------------------------------------------------------


@_red
def test_add_after_uses_place(monkeypatch):
    calls = []
    real = site_schema.place_item

    def spy(*args, **kwargs):
        calls.append(args[2:4])
        return real(*args, **kwargs)

    monkeypatch.setattr(site_schema, "place_item", spy)
    items = [_blk("a"), _blk("b")]
    new = site_schema.mutate(items, "text", "add", block_type="text", after="a")
    assert _order(items) == ["a", new, "b"]
    site_schema.mutate(items, "text", "move", ref="b", value="before:a")
    assert calls == [("after", "a"), ("before", "a")], "вставка и бросок — одна функция"


@_red
def test_insert_goes_through_mutate(monkeypatch):
    seen = []
    real = site_schema.mutate

    def spy(items, code, op, *args, **kwargs):
        seen.append((op, kwargs.get("after")))
        return real(items, code, op, *args, **kwargs)

    monkeypatch.setattr(site_schema, "mutate", spy)
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    first = _draft_items(b, "text")[-1]["id"]
    b.post(seite="text", op="add", type="text", after=first)
    assert seen[-1] == ("add", first), "позиция — полем `after` через `mutate`"


def test_empty_after_appends_to_tail():
    items = [_blk("a"), _blk("b")]
    new = site_schema.mutate(items, "text", "add", block_type="text")
    assert _order(items) == ["a", "b", new]


# --- №5: точное совпадение -------------------------------------------------------------------


@_red
@pytest.mark.parametrize(
    "after,ok",
    [("x", True), ("x_2", True), ("__page", False), ("__title", False), ("__title_x", False)],
)
def test_after_exact_match(after, ok):
    items = [_blk("x"), _blk("x_2"), _blk("y")]
    before = [dict(i) for i in items]
    if not ok:
        with pytest.raises(site_schema.SchemaError) as exc:
            site_schema.mutate(items, "text", "add", block_type="text", after=after)
        assert exc.value.args == ("op",)
        assert items == before, "отказ — список как был"
        return
    new = site_schema.mutate(items, "text", "add", block_type="text", after=after)
    order = _order(items)
    assert order[order.index(after) + 1] == new


# --- №6, №8: мусор, устаревший ref, полный список ---------------------------------------------


def _full():
    return [_blk(f"b{i}") for i in range(siteconfig._MAX_CBLOCKS)]


@_red
@pytest.mark.parametrize("case", ["ok", "junk", "stale", "main", "kauf", "full", "long"])
def test_add_after(case):
    code, items, after = "text", [_blk("a"), _blk("b")], "a"
    if case == "junk":
        after = "a b<script>"
    elif case == "stale":
        after = "deadbeef0000"
    elif case == "main":
        code, items = "catalog", [_blk("a"), {"key": "main"}, _blk("b")]
        after = "main"
    elif case == "kauf":
        code = "event"
        items, after = detail_parts.edit_rows({}, "event_detail", [_blk("a")]), "__kauf"
    elif case == "full":
        items = _full()
        after = "b3"
    elif case == "long":
        items = [_blk("a" * 70)]
        after = "a" * 70
    before = [dict(i) for i in items]
    if case in ("junk", "stale", "full", "long"):
        with pytest.raises(site_schema.SchemaError) as exc:
            site_schema.mutate(items, code, "add", block_type="text", after=after)
        assert exc.value.args == ("full" if case == "full" else "op",)
        assert items == before, "отказ не сползает в хвост и ничего не оставляет"
        return
    new = site_schema.mutate(items, code, "add", block_type="text", after=after)
    order = _order(items)
    if case == "kauf":
        assert order[-1] == new, "после «Buchung» — хвост (как бросок)"
    else:
        assert order[order.index(after) + 1] == new


@_red
def test_add_row_failed_place_rolls_back():
    items = [_blk("a"), _blk("b")]
    before = [dict(i) for i in items]
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "text", "add_row", value="text_image", after="nope")
    assert items == before


@_red
def test_junk_after_is_error_not_tail():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    before = _order(_draft_items(b, "text"))
    resp, msgs = b.post(seite="text", op="add", type="text", after="nope")
    assert resp.status_code == 302
    assert _order(_draft_items(b, "text")) == before, "мусор — отказ, не вставка в хвост"
    assert any("nicht möglich" in m for m in msgs)


# --- №11: токен окна ----------------------------------------------------------------------------


@_red
def test_add_gets_fresh_window_token():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    first = _draft_items(b, "text")[-1]["id"]
    resp, _m = b.post(
        seite="text", op="add", type="text", after=first, wopen="TOKa1", tab="karte", sprache="en"
    )
    q = _query(resp)
    new = _draft_items(b, "text")
    added = [i["id"] for i in new if i.get("id") and i["id"] != first]
    assert q["block"] == added
    assert "wopen" not in q and "tab" not in q and "sprache" not in q, q
    assert resp["Location"].endswith("#schema-panel")


@_red
def test_add_row_gets_fresh_window_token():
    b = Browser(_tenant())
    resp, _m = b.post(seite="text", op="add_row", value="text_image", wopen="TOKa1", tab="karte")
    q = _query(resp)
    assert "block" in q and "wopen" not in q and "tab" not in q


@_red
def test_failed_add_closes_window():
    b = Browser(_tenant())
    resp, _m = b.post(seite="text", op="add", type="text", after="nope", wopen="TOKa1", tab="karte")
    q = _query(resp)
    assert "block" not in q and "wopen" not in q, q


def test_after_is_read_only_for_insert():
    """`after` не трогает другие операции (бросок несёт позицию в `value`)."""
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    b.post(seite="text", op="add", type="text")
    a, c = [i["id"] for i in _draft_items(b, "text") if i.get("id")]
    b.post(seite="text", op="up", ref=c, after=a)
    order = _order(_draft_items(b, "text"))
    assert order.index(c) < order.index(a)


# --- №12–13: позиция по ref на настоящих хостах ----------------------------------------------


@_red
def test_add_row_contiguous_after_ref():
    items = [_blk("a"), _blk("b")]
    site_schema.mutate(items, "text", "add_row", value="three_cards", after="a")
    order = _order(items)
    assert order[0] == "a" and order[-1] == "b"
    assert len(order) == 5, order


@_red
def test_insert_on_detail_past_in_place():
    """Блок после раздела, за которым идут строки «на месте», встаёт после всей группы — как
    при броске (редактор = страница)."""
    host = "event_detail"
    rows = detail_parts.edit_rows({}, host, [])
    keys = _order(rows)
    in_place = detail_parts.in_place_keys(host)
    assert in_place, "у события есть разделы «на месте»"
    first = keys.index(in_place[0])
    target = keys[first - 1]
    moved = [dict(i) for i in rows] + [_blk("m")]
    site_schema.mutate(moved, "event", "move", ref="m", value=f"after:{target}")
    new = site_schema.mutate(rows, "event", "add", block_type="text", after=target)
    assert _order(rows).index(new) == _order(moved).index("m")
    assert _order(rows).index(new) > first


@_red
def test_insert_cart_slides():
    """§ 312j: между формой и итогом корзины блоков нет — вставка после формы идёт под итог."""
    items = [{"key": "items"}, {"key": "form"}, {"key": "summary"}, _blk("t")]
    new = site_schema.mutate(items, "cart", "add", block_type="text", after="form")
    order = _order(items)
    assert order.index(new) == order.index("summary") + 1


@pytest.mark.parametrize("code,after", [("cart", "summary"), ("product", "__kauf")])
def test_add_under_legal_row(code, after):
    """H1: форма вставки без `ref` — правовая строка не уводит `add` в ветку закреплённых
    строк; блок встаёт по `after`."""
    b = Browser(_tenant())
    b.get(f"?seite={code}")
    resp, msgs = b.post(seite=code, op="add", type="text", after=after)
    assert resp.status_code == 302
    assert not any("nicht möglich" in m for m in msgs), msgs
    assert "block" in _query(resp), "блок вставлен и открыт"


@_red
def test_add_under_gift_form():
    """H1: форма ваучера — правовая строка; вставка после неё — по `after` (у магазина без
    продажи ваучеров страницы нет — проверка на списке строк)."""
    items = [{"key": "intro"}, {"key": "form"}, _blk("t")]
    new = site_schema.mutate(items, "gift", "add", block_type="text", after="form")
    assert _order(items).index(new) == _order(items).index("form") + 1


@_red
def test_insert_after_categories():
    """M2: вставка после «Kategorien» — как бросок туда сегодня."""
    b = Browser(_tenant())
    b.get("?seite=catalog")
    b.post(seite="catalog", op="add", type="text")
    base = _draft_items(b, "catalog")
    assert "categories" in _order(base)
    moved = [dict(i) for i in base]
    mover = moved[-1]["id"]
    site_schema.mutate(moved, "catalog", "move", ref=mover, value="after:categories")
    items = [dict(i) for i in base]
    new = site_schema.mutate(items, "catalog", "add", block_type="text", after="categories")
    assert _order(items).index(new) == _order(moved).index(mover)


@_red
def test_insert_on_inherited_category():
    """L5: категория без своей схемы — `after` только из её собственных строк (неявного
    `adopt` нет): блок каталога в позиции — отказ, без `after` — как прежде."""
    from apps.catalog.models import Category

    b = Browser(_tenant())
    cat = Category.objects.create(name={"de": "Tee"}, slug="tee")
    code = f"category@{siteconfig.category_host(cat.slug)}"
    b.post(seite="catalog", op="add", type="text")
    b.post(seite="catalog", op="save")
    catalog_block = [i for i in _draft_items(b, "catalog") if i.get("id")] or [
        i
        for i in (siteconfig.normalize(b.tenant.site_config).get("page_blocks") or {}).get(
            "catalog", []
        )
        if i.get("id")
    ]
    resp, _m = b.post(seite=code, op="add", type="text", after=catalog_block[0]["id"])
    own = [i for i in _draft_items(b, code) if i.get("id")]
    assert all(i["id"] != catalog_block[0]["id"] for i in own)
    assert "block" not in _query(resp), "чужой ref — отказ"


# --- №31: запросы ------------------------------------------------------------------------------


def test_add_after_queries():
    b = Browser(_tenant())
    b.post(seite="text", op="add", type="text")
    first = _draft_items(b, "text")[-1]["id"]
    with CaptureQueriesContext(connection) as tail:
        b.post(seite="text", op="add", type="text")
    with CaptureQueriesContext(connection) as placed:
        b.post(seite="text", op="add", type="text", after=first)
    assert len(placed) == len(tail)
