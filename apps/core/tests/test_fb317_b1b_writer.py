"""FB-31.7 B1b-1: шаблон страницы уровня сайта пишется строками схемы (оси), старый ключ
снимается; витрина видит тот же вид, что давал код (`docs/fb31-7-materialize-plan-2026-11-16.md`)."""

import pytest

from apps.catalog import catalog_parts
from apps.core import page_parts as pp
from apps.tenants import siteconfig

OWN = {"key": "text", "id": "own1", "enabled": True, "data": {"title": "Hinweis"}}


def _codes(key):
    host, _path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    if host in ("catalog", "category"):
        return [c for c in catalog_parts._FROM_CODE if c]
    return [c for c in siteconfig._pp_surface(host).codes if c]


@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_every_template_round_trips_through_rows(key):
    host, path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    for code in _codes(key):
        for rows in ([], [OWN], [{"key": "main"}, OWN]):
            raw = {"page_blocks": {host: list(rows)}}
            out = siteconfig.normalize(siteconfig.set_page_template(raw, key, code))
            assert siteconfig.page_template_code(out, key) == code, (key, code, rows)
            # старый ключ снят — вид держат строки
            node = out
            for part in path:
                node = node.get(part) if isinstance(node, dict) else None
            assert not node, (key, code)
            kept = [r for r in out["page_blocks"][host] if r.get("id")]
            assert [r["id"] for r in kept] == [r["id"] for r in rows if r.get("id")]


@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_written_rows_give_the_code_view_without_the_code(key):
    host, _path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    for code in _codes(key):
        out = siteconfig.normalize(siteconfig.set_page_template({}, key, code))
        if host in ("catalog", "category"):
            want = catalog_parts.from_code(code)
            got = catalog_parts.effective(out, host)
            if host == "catalog" and code == "sets":
                want = catalog_parts.Parts(sets="above")  # у корня шапки у «sets» не было
            assert got == want, (key, code)
        else:
            s = siteconfig._pp_surface(host)
            assert pp.effective(s, out, host) == pp.from_code(s, code), (key, code)


@pytest.mark.parametrize("key", sorted(siteconfig.PAGE_TEMPLATE_HOSTS))
def test_standard_after_a_template_clears_both_rows_view_and_the_old_key(key):
    host, path = siteconfig.PAGE_TEMPLATE_HOSTS[key]
    code = _codes(key)[0]
    raw = {"page_blocks": {host: [OWN]}}
    raw = siteconfig.set_page_template(raw, key, code)
    # старый ключ с другим кодом (до переноса) не перебивает выбор «Standard»
    if len(path) == 1:
        raw[path[0]] = code
    else:
        raw.setdefault(path[0], {})[path[1]] = code
    out = siteconfig.normalize(siteconfig.set_page_template(raw, key, ""))
    assert siteconfig.page_template_code(out, key) == ""


def test_template_choice_keeps_own_block_translations_on_their_blocks():
    """Ревью B1b-1: строки осей встают перед своими блоками — переводы едут за блоками."""
    raw = {
        "page_blocks": {"catalog": [OWN]},
        "i18n": {"en": {"page_blocks": {"catalog": [{"data": {"title": "Note"}}]}}},
    }
    out = siteconfig.set_page_template(raw, "catalog_page_style", "magazin")
    en = siteconfig.localize(siteconfig.normalize(out), "en")
    own = next(r for r in en["page_blocks"]["catalog"] if r.get("id") == "own1")
    assert own["data"]["title"] == "Note"


def test_template_choice_replaces_hidden_axis_rows_like_before():
    """Выбор шаблона — решение владельца целиком: прежние строки осей (и скрытые) снимаются,
    как и до B1b (`drop_page_views`); невыразимого случая у писателя нет."""
    from apps.core import page_settings

    raw = {"page_blocks": {"promos": [{"key": "groups", "enabled": False}, {"key": "main"}]}}
    code = next(
        c
        for c in _codes("promo_page_style")
        if pp.from_code(siteconfig._pp_surface("promos"), c).get("groups")
    )
    out = page_settings.apply_override(raw, "promo_page_style", code)
    assert siteconfig.page_template_is(siteconfig.normalize(out), "promo_page_style", code)


def test_same_code_but_different_axes_is_not_a_no_op():
    """Ревью B1b-1: «тот же шаблон» — по осям, а не по ближайшему коду."""
    from apps.core import page_settings

    raw = {"page_blocks": {"catalog": [{"key": "main", "style": "mosaik", "grid": "cols6"}]}}
    out = page_settings.apply_override(raw, "catalog_page_style", "mosaik")
    norm = siteconfig.normalize(out)
    assert siteconfig.page_template_is(norm, "catalog_page_style", "mosaik")
