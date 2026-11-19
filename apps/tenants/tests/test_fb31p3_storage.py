"""FB-31 P3 R2: строки осей страниц акций хранятся (как строки каталога FB-30.16)."""

from apps.tenants import siteconfig

HEX = "a" * 32


def _norm(host, rows):
    return siteconfig.normalize_page_blocks({host: rows}).get(host)


def test_promos_keeps_its_part_rows_and_star_fields():
    rows = [
        {"key": "page_head", "style": "titelbild"},
        {"key": "groups", "style": "tabs"},
        {"key": "main", "style": "prospekt", "grouping": "ohne", "grid": "cols4"},
    ]
    got = _norm("promos", rows)
    assert {"key": "page_head", "enabled": True, "style": "titelbild"} in got
    assert {"key": "groups", "enabled": True, "style": "tabs"} in got
    marker = next(r for r in got if r.get("key") == "main")
    assert marker == {"key": "main", "style": "prospekt", "grouping": "ohne"}, "чужие поля — нет"


def test_junk_views_and_catalog_keys_are_dropped_on_promos():
    rows = [
        {"key": "groups", "style": "wegweiser"},
        {"key": "categories", "style": "regale"},
        {"key": "main", "style": "mosaik"},
    ]
    assert _norm("promos", rows) is None, "мусор не хранится, голый ★ первым — тоже"


def test_detail_and_object_hosts_keep_the_offer_row():
    for host in ("promo_detail", f"promo:{HEX}"):
        got = _norm(host, [{"key": "offer", "style": "plakat"}, {"key": "offer", "style": "x"}])
        assert got == [{"key": "offer", "enabled": True, "style": "plakat"}], host
    # FB-31 P5 R8 (осознанно): у хоста одного товара — строки-якоря его разделов (своя
    # схема объекта), строки «Angebot» по-прежнему только у акций
    keys = siteconfig.page_builtin_keys(f"product:{HEX}")
    assert "offer" not in keys and keys == {
        "description",
        "info",
        "sizes",
        "trust",
        "anprobe",
        "waitlist",
        "instore",
        "question",
        "reviews",
        "related",
        "recent",
    }


def test_drop_page_views_removes_promo_views_only():
    cfg = {
        "page_blocks": {
            "promos": [
                {"key": "groups", "style": "tabs"},
                {"key": "text", "id": "t1", "data": {}},
                {"key": "main", "style": "magazin", "grouping": "ohne"},
            ]
        }
    }
    out = siteconfig.drop_page_views(cfg, "promos")
    assert out["page_blocks"]["promos"] == [
        {"key": "text", "id": "t1", "data": {}},
        {"key": "main"},
    ]
    assert cfg["page_blocks"]["promos"][0]["style"] == "tabs", "копия"


def test_catalog_storage_is_unchanged():
    rows = [{"key": "categories", "style": "regale"}, {"key": "main", "style": "mosaik"}]
    got = _norm("catalog", rows)
    assert got[-1] == {"key": "main", "style": "mosaik"}
    assert siteconfig.part_styles("catalog", "page_head") == ("aus", "titelbild")
