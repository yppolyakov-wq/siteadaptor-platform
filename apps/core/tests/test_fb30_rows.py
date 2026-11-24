"""FB-30.8 (макет 4): блоки встают в ряд по ширине. Операция `beside` ставит блок в ряд к
узкому блоку: своя узкая ширина, если влезает, иначе наибольшая допустимая, что помещается;
не помещается ничего — блок встаёт своим рядом сразу после этого (как на макете). Сумма
долей ряда никогда не больше единицы. `own_row` выносит блок в свой ряд."""

import random
from fractions import Fraction

import pytest

from apps.core import site_schema
from apps.core.tests.test_fb27_r3_width import _tenant
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _rows(tenant):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    layout = site_schema.schema_layout(site_schema.blocks_for(cfg, "text", tenant=None))
    return [[(b["ref"], b.get("width") or "") for b in row] for row in layout["rows"]]


def _add(tenant, kind="text", width=""):
    ref = site_schema.apply(tenant, "text", "add", block_type=kind)
    if width:
        site_schema.apply(tenant, "text", "width", ref=ref, value=width)
    return ref


def _row_of(rows, ref):
    return next(r for r in rows if ref in [x for x, _w in r])


def test_text_dropped_next_to_a_half_becomes_a_half_and_joins_the_row():
    t = _tenant()
    a = _add(t, width="w12")
    x = _add(t)
    site_schema.apply(t, "text", "beside", ref=x, value=a)
    assert _row_of(_rows(t), a) == [(a, "w12"), (x, "w12")]


def test_the_largest_width_that_fits_is_chosen():
    t = _tenant()
    a = _add(t, width="w23")
    x = _add(t)
    site_schema.apply(t, "text", "beside", ref=x, value=a)
    assert _row_of(_rows(t), a) == [(a, "w23"), (x, "w13")]
    b = _add(t, width="w12")
    _add(t, width="w13")
    c_row = _row_of(_rows(t), b)
    assert [w for _r, w in c_row] == ["w12", "w13"]
    y = _add(t)
    site_schema.apply(t, "text", "beside", ref=y, value=b)
    assert [w for _r, w in _row_of(_rows(t), b)] == ["w12", "w13", "w16"]


def test_own_narrow_width_is_kept_when_it_fits():
    t = _tenant()
    a = _add(t, width="w12")
    _add(t)  # широкий разделитель
    x = _add(t, width="w13")
    site_schema.apply(t, "text", "beside", ref=x, value=a)
    assert _row_of(_rows(t), a) == [(a, "w12"), (x, "w13")]


def test_full_row_puts_the_block_in_its_own_row_right_after():
    t = _tenant()
    a = _add(t, width="w12")
    b = _add(t, width="w12")
    x = _add(t, "image_text")  # не уже половины
    site_schema.apply(t, "text", "beside", ref=x, value=a)
    rows = _rows(t)
    assert _row_of(rows, a) == [(a, "w12"), (b, "w12")]
    i = rows.index(_row_of(rows, a))
    assert rows[i + 1][0][0] == x


def test_moving_out_of_a_row_does_not_glue_its_neighbours_to_the_row_above():
    t = _tenant()
    a = _add(t, width="w12")
    m = _add(t, width="w12")
    c = _add(t, width="w12")
    site_schema.apply(t, "text", "newline", ref=m)  # ряды: [a] [m c]
    target = _add(t, width="w12")
    _add(t)  # разделитель
    site_schema.apply(t, "text", "beside", ref=m, value=target)
    rows = _rows(t)
    assert _row_of(rows, a) == [(a, "w12")], "c не прилип к ряду a"
    assert _row_of(rows, c)[0][0] == c


def test_own_row_splits_a_row():
    t = _tenant()
    a = _add(t, width="w13")
    b = _add(t, width="w13")
    c = _add(t, width="w13")
    site_schema.apply(t, "text", "own_row", ref=b)
    rows = _rows(t)
    assert [r[0][0] for r in rows[-3:]] == [a, b, c]


def test_refusals():
    t = _tenant()
    a = _add(t, width="w12")
    wide = _add(t)
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text", "beside", ref=a, value=a)
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text", "beside", ref=a, value=wide)  # цель не узкая
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "text", "beside", ref=a, value="nope")


def test_row_sums_never_exceed_one():
    rnd = random.Random(30)
    t = _tenant()
    refs = [_add(t, width=rnd.choice(["", "w12", "w13", "w23", "w14"])) for _i in range(7)]
    for _step in range(25):
        x, y = rnd.sample(refs, 2)
        try:
            site_schema.apply(t, "text", "beside", ref=x, value=y)
        except site_schema.SchemaError:
            pass
        for row in _rows(t):
            share = sum(site_schema.ROW_SHARE.get(w, Fraction(1)) for _r, w in row)
            assert share <= 1, row


def test_structure_list_offers_a_slot_where_a_row_has_room():
    t = _tenant()
    a = _add(t, width="w12")
    cfg = siteconfig.normalize(Tenant.objects.get(pk=t.pk).site_config)
    lines = site_schema.schema_layout(site_schema.blocks_for(cfg, "text", tenant=None))["lines"]
    line = next(li for li in lines if li["blocks"][0]["ref"] == a)
    assert line["slot"] == {"ref": a, "label": "½"}
    site_schema.apply(t, "text", "beside", ref=_add(t), value=a)
    cfg = siteconfig.normalize(Tenant.objects.get(pk=t.pk).site_config)
    lines = site_schema.schema_layout(site_schema.blocks_for(cfg, "text", tenant=None))["lines"]
    line = next(li for li in lines if li["blocks"][0]["ref"] == a)
    assert line["slot"] is None, "ряд полон — места нет"


# --- экран ---


def test_screen_shows_the_slot_and_the_row_buttons_without_script():
    from apps.core.tests.test_fb27_r2_draft import Browser

    t = _tenant()
    a = _add(t, width="w12")
    x = _add(t)
    b = Browser(t)
    html = b.get("?seite=text")
    assert f'data-schema-slot="{a}"' in html and "bis ½" in html
    html = b.get(f"?seite=text&block={x}")
    assert 'name="op" value="beside"' in html and f'name="value" value="{a}"' in html
    resp, msgs = b.post(seite="text", op="beside", ref=x, value=a)
    assert resp.status_code == 302 and not msgs
    b.post(seite="text", op="save")
    assert _row_of(_rows(t), a) == [(a, "w12"), (x, "w12")]
    html = b.get(f"?seite=text&block={x}")
    assert 'value="own_row"' in html


def test_drag_onto_the_slot_sends_beside():
    import pathlib

    js = pathlib.Path("static/js/aufbau.js").read_text()
    # FB-33 M3-6: и закреплённая строка 🔒 — цель броска
    assert '"[data-schema-drag],[data-schema-slot],[data-schema-pinned]"' in js
    assert 'data.set("op", slot ? "beside" : "move")' in js


def test_rows_wrap_when_they_would_be_wider_than_the_page():
    rows = siteconfig.group_block_rows(
        [{"width": "w23"}, {"width": "w12"}, {"width": "w13"}, {"width": "w12"}]
    )
    assert [[b["width"] for b in r["row"]] for r in rows] == [["w23"], ["w12", "w13"], ["w12"]]


# --- ревью (django-reviewer) ---


def test_moving_from_the_end_of_a_row_does_not_pull_up_the_next_row():
    t = _tenant()
    a = _add(t, width="w12")
    b = _add(t, width="w12")
    c = _add(t, width="w12")  # ряды: [a b] [c]
    target = _add(t, width="w13")
    site_schema.apply(t, "text", "own_row", ref=target)
    site_schema.apply(t, "text", "beside", ref=b, value=target)
    rows = _rows(t)
    assert _row_of(rows, a) == [(a, "w12")], "c не стянулся к a"
    assert _row_of(rows, c)[0] == (c, "w12")


def test_joining_a_row_leaves_no_stray_new_row_flags():
    t = _tenant()
    a = _add(t, width="w12")
    x = _add(t)
    d = _add(t, width="w13")
    site_schema.apply(t, "text", "beside", ref=x, value=a)
    cfg = siteconfig.normalize(Tenant.objects.get(pk=t.pk).site_config)
    flags = {b["id"]: bool(b.get("newline")) for b in cfg["page_blocks"]["info"] if b.get("id")}
    assert flags[x] is False, "вставленный в ряд блок не начинает ряд"
    assert _row_of(_rows(t), d) == [(d, "w13")], "следующий ряд остался своим"


def test_the_home_banner_never_joins_a_row():
    t = _tenant()
    a = site_schema.apply(t, "home", "add", block_type="text")
    site_schema.apply(t, "home", "width", ref=a, value="w12")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "home", "beside", ref="hero", value=a)


def test_slot_is_hidden_from_screen_readers():
    import pathlib

    src = pathlib.Path("templates/tenant/site_schema.html").read_text()
    slot = src[src.index("data-schema-slot=") - 300 : src.index("data-schema-slot=")]
    assert 'aria-hidden="true"' in slot
