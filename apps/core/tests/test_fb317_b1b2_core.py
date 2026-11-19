"""FB-31.7 B1b-2a: «Alle Kategorien» и свои шаблоны категорий — единый читатель вида
(`catalog_parts.category_parts`), переключатель «вид после B3» и писатель строками."""

from types import SimpleNamespace

from apps.catalog import catalog_parts
from apps.catalog.category_styles import page_style
from apps.core import page_axes_migration as pam
from apps.tenants import siteconfig

# FB-31.7 B3b: модуль проверяет отрисовку по старым кодам шаблонов (до B4) — см. conftest
LEGACY_CODES = True


def _cat(slug="tee", style=""):
    return SimpleNamespace(slug=slug, page_style=style)


def test_own_code_wins_over_site_default_without_rows():
    cfg = siteconfig.normalize({"site_defaults": {"category_page_style": "kopfbild"}})
    assert (
        catalog_parts.legacy_code(catalog_parts.category_parts(cfg, _cat(style="tabs"))) == "tabs"
    )
    assert catalog_parts.category_host(cfg, _cat()) == "category"


def test_own_rows_win_over_own_code_and_parent_tabs_follow_rows():
    # своя схема с осями — сильнее кода; табы родителя читают то же правило (раньше — код)
    rows = catalog_parts.write_rows([], catalog_parts.from_code("tabs"))
    cfg = siteconfig.normalize({"page_blocks": {siteconfig.category_host("tee"): rows}})
    parent = _cat(style="")
    assert catalog_parts.category_host(cfg, parent) == siteconfig.category_host("tee")
    assert catalog_parts.legacy_code(catalog_parts.category_parts(cfg, parent)) == "tabs"


def test_objects_blind_hides_own_codes_only_inside_the_block():
    cat = _cat(style="tabs")
    with pam.objects_blind():
        # B3b: «вид без кодов» не читает ни своего кода, ни дефолта сайта — только строки
        assert page_style(cat, "kopfbild") == ""
    assert page_style(cat, "kopfbild") == "tabs"


def test_alle_kategorien_writer_stores_rows_and_drops_the_key():
    cfg = siteconfig.normalize({"site_defaults": {"category_page_style": "kopfbild"}})
    out = siteconfig.set_page_template(cfg, "category_page_style", "tabs")
    assert "category_page_style" not in (out.get("site_defaults") or {})
    assert siteconfig.page_template_code(siteconfig.normalize(out), "category_page_style") == "tabs"


def test_site_level_move_leaves_alle_kategorien_for_the_category_unit():
    raw = {"site_defaults": {"category_page_style": "kopfbild"}}
    out, report = pam.migrate_templates(raw)
    assert "category_page_style" not in report.surfaces
    assert out["site_defaults"]["category_page_style"] == "kopfbild"


def test_category_host_cap_raised_to_120():
    assert siteconfig._MAX_CATEGORY_HOSTS == 120


def test_explicit_rows_pin_every_axis_even_standard():
    from apps.core import page_parts as pp
    from apps.promotions import promo_parts

    s = promo_parts.PROMO_GROUP
    target = pp.from_code(s, "magazin")  # вид «magazin», шапка — обычная
    rows = pp.rows_with(s, [], target, explicit=True)
    assert pp.effective_rows(s, rows) == target
    assert set(pp._stored(s, rows)) == {a.name for a in s.axes}, "каждая ось — строкой"
    # без explicit — только отличающиеся оси (прежнее поведение materialize_rows)
    assert pp.materialize_rows(s, [], "magazin") == pp.rows_with(s, [], target)


def test_objects_blind_hides_own_promo_and_group_codes():
    from apps.promotions import promo_parts

    cfg = siteconfig.normalize({"promo_groups": {"Sale": {"style": "magazin"}}})
    seen = promo_parts.group_parts(cfg, "Sale")
    with pam.objects_blind():
        assert promo_parts.group_parts(cfg, "Sale") != seen
        assert promo_parts.detail_parts(cfg, "plakat", "") == promo_parts.detail_parts(cfg, "", "")


def test_alle_kategorien_write_refuses_cleanly_when_own_templates_cannot_be_kept(monkeypatch, db):
    """Ревью ветки B1b-2: закрепить свои шаблоны категорий не вышло (нет места под своими
    схемами) — `PageSettingError`, настройки не тронуты (не тихая потеря своего шаблона)."""
    import pytest

    from apps.core import page_axes_objects as pao
    from apps.core import page_settings
    from apps.tenants.tests.factories import TenantFactory

    cap = siteconfig._MAX_CATEGORY_HOSTS
    full = {siteconfig.category_host(f"c{i:03d}"): [{"key": "main"}] for i in range(cap)}
    tenant = TenantFactory(
        schema_name="public", slug="b1b2pin", name="P", site_config={"page_blocks": full}
    )
    idx = pao.ObjectIndex(
        categories=[pao.CategoryRef("neu", "tabs")],
        all_category_slugs=frozenset({"neu", *(f"c{i:03d}" for i in range(cap))}),
    )
    monkeypatch.setattr(pao, "build_index", lambda: idx)
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "category_page_style", "magazin")
    tenant.refresh_from_db()
    assert tenant.site_config == {"page_blocks": full}
