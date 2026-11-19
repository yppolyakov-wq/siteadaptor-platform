"""FB-31 P4 R2–R5: листинги в «Seitenaufbau» — закреплённые строки «Banner · Fotos der Seite»
и навигации (Kollektionen · Themen · Bereiche) с плитками вида; шаблон листинга — блоками."""

import pytest

from apps.core import page_settings, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

# FB-31.7 B3b: модуль проверяет отрисовку по старым кодам шаблонов (до B4) — см. conftest
LEGACY_CODES = True

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _salon(**cfg):
    return TenantFactory(
        business_type="friseur",
        disabled_modules=list(default_disabled_for("friseur")),
        site_config=cfg,
    )


def _saved(tenant, host):
    tenant.refresh_from_db()
    return (siteconfig.normalize(tenant.site_config).get("page_blocks") or {}).get(host) or []


def test_listing_rows_are_pinned_and_read_the_template():
    cfg = siteconfig.normalize({"page_styles": {"services": "tabs"}})
    rows = site_schema.blocks_for(cfg, "services")
    assert [r["key"] for r in rows[:3]] == ["page_head", "groups", "main"]
    assert rows[1]["catview"]["value"] == "tabs" and str(rows[1]["label"]) == "Kollektionen"
    assert rows[0]["catview"]["value"] == "aus"


def test_listing_without_subsections_has_only_the_banner_row():
    rows = site_schema.blocks_for(siteconfig.normalize({}), "blog")
    assert [r["key"] for r in rows[:2]] == ["page_head", "main"]


def test_stays_rows_live_on_stay_rooms():
    cfg = siteconfig.normalize(
        {"page_blocks": {"stay_rooms": [{"key": "groups", "style": "side"}]}}
    )
    rows = site_schema.blocks_for(cfg, "stays")
    assert next(r for r in rows if r["key"] == "groups")["catview"]["value"] == "side"


def test_unavailable_navigation_and_banner_are_refused_with_reason():
    tenant = _salon()  # без подборок и без фото сайта
    b = Browser(tenant)
    html = b.get("?seite=services&block=groups")
    assert "Nur mit Unterteilung der Liste verfügbar." in html
    b.post(seite="services", op="catview", ref="groups", value="tabs")
    b.post(seite="services", op="catview", ref="page_head", value="titelbild")
    b.post(seite="services", op="save")
    assert _saved(tenant, "services") == []


def test_owner_view_is_saved_as_a_row():
    tenant = _salon()
    b = Browser(tenant)
    b.post(seite="services", op="catview", ref="groups", value="auto")
    b.post(seite="services", op="save")
    assert {"key": "groups", "enabled": True, "style": "auto"} in _saved(tenant, "services")


def test_template_settings_are_replaced_and_writers_drop_views():
    assert "services_page_style" not in site_schema.setting_codes(_salon(), "services")
    cfg = {"page_blocks": {"stay_rooms": [{"key": "groups", "style": "side"}]}}
    out = page_settings.apply_override(cfg, "stays_page_style", "regale")
    # B3a: прежний вид строки снят, шаблон записан строками хоста (старый ключ не пишется)
    from apps.core import listing_parts

    assert "page_styles" not in out
    assert listing_parts.code_for(siteconfig.normalize(out), "stays") == "regale"
    same = page_settings.apply_override(
        {**cfg, "page_styles": {"stays": "regale"}}, "stays_page_style", "regale"
    )
    assert same["page_blocks"]["stay_rooms"], "тот же шаблон виды не снимает"


def test_review_pinned_rows_do_not_count_as_blocks_and_labels_translate():
    from django.utils import translation

    tenant = _salon()
    cfg = siteconfig.normalize(tenant.site_config)
    rows = {r.code: r for _l, items in site_schema.type_groups(tenant, cfg) for r in items}
    assert rows["services"].count == 0, "пустая страница — ноль своих блоков"
    with translation.override("ru"):
        got = site_schema.blocks_for(siteconfig.normalize({}), "services")
        assert str(next(r for r in got if r["key"] == "groups")["label"]) != "Kollektionen"
