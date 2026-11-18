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
