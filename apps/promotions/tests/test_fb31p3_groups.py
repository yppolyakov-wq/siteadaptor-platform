"""FB-31 P3 R6a: страницы групп акций — «Alle Angebotsgruppen» (`promo_group`) и своя
схема группы (`promo_group:<md5>`); без них — блоки обзора, как раньше."""

import pytest

from apps.core import page_settings
from apps.promotions import promo_parts
from apps.promotions.tests.test_fb31p3_promo_golden import _check, _overview, _seed
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
TEXT = {"key": "text", "id": "t-grp", "data": {"title": "Nur Gruppen", "body": "x"}}
OVERVIEW = {"key": "text", "id": "t-promo", "data": {"title": "Hinweis", "body": "Gilt solange"}}
HOST = siteconfig.promo_group_host("Wochenangebote")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_group_hosts_are_stored_and_capped_apart():
    assert HOST.startswith("promo_group:") and len(HOST) == len("promo_group:") + 32
    assert siteconfig.is_page_block_host(HOST) and siteconfig.has_main_list(HOST)
    raw = {"promo_group": [], HOST: [TEXT, {"key": "page_head", "style": "countdown"}]}
    got = siteconfig.normalize_page_blocks(raw)
    assert got["promo_group"] == [], "сохранённая пустая — остаётся"
    assert {"key": "page_head", "enabled": True, "style": "countdown"} in got[HOST]
    many = {f"promo_group:{i:032x}": [TEXT] for i in range(60)}
    assert (
        sum(1 for k in siteconfig.normalize_page_blocks(many) if k.startswith("promo_group:")) == 40
    )


def test_unsaved_group_pages_fall_back_to_the_overview_blocks():
    cfg = {
        "page_blocks": {
            "promos": [
                {"key": "groups", "style": "tabs"},
                OVERVIEW,
                {"key": "main", "style": "magazin"},
            ]
        }
    }
    rows = siteconfig.page_rows(cfg, HOST)
    assert rows == [OVERVIEW, {"key": "main"}], "только свои блоки и место ★"


def test_group_page_without_own_blocks_looks_as_before():
    _seed(True)
    cfg = {"page_blocks": {"promos": [OVERVIEW, {"key": "main"}]}}
    _check("group-standard-overview-blocks", _overview(cfg, gruppe="Wochenangebote"))


def test_all_groups_blocks_replace_the_overview_blocks_on_group_pages():
    _seed(True)
    cfg = {
        "page_blocks": {
            "promos": [OVERVIEW, {"key": "main"}],
            "promo_group": [TEXT, {"key": "main"}],
        }
    }
    html = _overview(cfg, gruppe="Wochenangebote")
    assert "Nur Gruppen" in html and "Gilt solange" not in html
    assert "Gilt solange" in _overview(cfg), "обзор — свои блоки"


def test_own_group_blocks_beat_all_groups():
    _seed(True)
    own = {**TEXT, "id": "t-own", "data": {"title": "Nur diese", "body": "y"}}
    cfg = {"page_blocks": {"promo_group": [TEXT], HOST: [own]}}
    assert "Nur diese" in _overview(cfg, gruppe="Wochenangebote")
    assert "Nur Gruppen" in _overview(cfg, gruppe="Räumung")


def test_group_view_precedence():
    shared = {"page_blocks": {"promo_group": [{"key": "page_head", "style": "prospekt"}]}}
    assert promo_parts.group_parts(shared, "X").head == "prospekt", "строка сильнее дефолта"
    own_style = {**shared, "promo_groups": {"X": {"style": "countdown"}}}
    assert promo_parts.group_parts(own_style, "X").head == "countdown", "свой шаблон сильнее"
    host = siteconfig.promo_group_host("X")
    own_rows = {**own_style, "page_blocks": {host: [{"key": "main", "style": "vergleich"}]}}
    parts = promo_parts.group_parts(own_rows, "X")
    assert parts.view == "vergleich" and parts.head == "countdown", "«nur diese» поверх"


def test_group_template_writes_drop_the_views():
    cfg = {"page_blocks": {"promo_group": [{"key": "page_head", "style": "prospekt"}]}}
    out = page_settings.apply_override(cfg, "promo_group_style", "magazin")
    # FB-31.7 B1b: прежний вид (шапка «Prospekt») снят, новый шаблон — строками осей
    code = siteconfig.page_template_code(siteconfig.normalize(out), "promo_group_style")
    assert code == "magazin" and "promo_group_style" not in (out.get("site_defaults") or {})
