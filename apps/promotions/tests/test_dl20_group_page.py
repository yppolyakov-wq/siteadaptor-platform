"""DL-20.4/20.5 — страница ГРУППЫ акций: заголовок (починка) и пять композиций.

Разведка волны: до DL-20 страницы группы фактически не было — `/aktionen/?gruppe=X`
отдавал плоскую сетку под общим заголовком «Aktuelle Angebote», и посетитель,
пришедший по ссылке из меню, не видел названия открытой группы.

План — `docs/dl20-category-templates-plan-2026-09-03.md`.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import group_styles, public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _promo(title, group="Wochenangebote", days=3, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("promo_type", "discount")
    kw.setdefault("price_override", Decimal("2.49"))
    kw.setdefault("compare_at_price", Decimal("3.49"))
    kw.setdefault("ends_at", timezone.now() + timedelta(days=days) if days else None)
    return Promotion.objects.create(title={"de": title}, group=group, **kw)


def _render(tenant, **params):
    request = RequestFactory().get("/aktionen/", params)
    request.tenant = tenant
    request.session = {}
    return public_views.promotion_list(request).content.decode()


def _tenant(style="", per_group=None):
    tenant = TenantFactory.build()
    cfg = {}
    if style:
        cfg["site_defaults"] = {"promo_group_style": style}
    if per_group:
        cfg["promo_groups"] = per_group
    tenant.site_config = cfg
    return tenant


# ─────────────────────────── реестр и хранение ───────────────────────────


def test_registry_has_the_five_layouts_plus_standard():
    codes = [c for c, _l, _h in group_styles.GROUP_PAGE_STYLES]
    assert codes[0] == ""
    for key in ("schaufenster", "prospekt", "magazin", "countdown", "vergleich"):
        assert key in codes, key


def test_group_choice_beats_the_site_default_and_garbage_falls_back():
    per_group = {"Wochenangebote": "prospekt", "Räumung": "erfunden"}
    assert group_styles.group_style("Wochenangebote", per_group, "magazin") == "prospekt"
    assert group_styles.group_style("Räumung", per_group, "magazin") == "magazin"
    assert group_styles.group_style("Neu", per_group, "magazin") == "magazin"
    assert group_styles.group_style("Neu", per_group, "erfunden") == ""


def test_both_keys_are_presence_minimal():
    assert "promo_groups" not in siteconfig.normalize({})
    assert "promo_group_style" not in siteconfig.normalize({})["site_defaults"]
    # мусорные значения ключей не материализуют
    assert "promo_groups" not in siteconfig.normalize({"promo_groups": {"A": "erfunden"}})
    kept = siteconfig.normalize({"promo_groups": {"A": "prospekt"}})
    assert kept["promo_groups"] == {"A": "prospekt"}


def test_unknown_group_key_is_ignored_not_crashing():
    """Имя группы — свободный текст: переименование осиротит запись словаря."""
    assert group_styles.group_style("", {"A": "prospekt"}, "") == ""
    assert group_styles.group_style("A", None, "") == ""


# ─────────────────────────── страница группы ───────────────────────────


def test_group_page_shows_its_name_even_without_a_template():
    """Починка: раньше заголовок оставался «Aktuelle Angebote»."""
    _promo("Bio-Milch")
    body = _render(_tenant(), gruppe="Wochenangebote")
    assert "Wochenangebote" in body
    assert 'data-group-head="standard"' in body


def test_plain_list_without_a_group_is_unchanged():
    """Инвариант волны: без выбранной группы страница прежняя байт-в-байт."""
    _promo("Bio-Milch")
    body = _render(_tenant())
    assert "data-group-head" not in body
    assert 'data-grid="promo_list" class="grid grid-cols-2' in body


def test_site_default_applies_to_every_group():
    _promo("Bio-Milch")
    body = _render(_tenant(style="prospekt"), gruppe="Wochenangebote")
    assert 'data-group-head="prospekt"' in body
    assert 'data-group-grid="prospekt"' in body


def test_group_choice_wins_over_the_site_default_on_the_page():
    _promo("Bio-Milch")
    tenant = _tenant(style="prospekt", per_group={"Wochenangebote": "countdown"})
    body = _render(tenant, gruppe="Wochenangebote")
    assert 'data-group-head="countdown"' in body
    assert 'data-group-head="prospekt"' not in body


def test_schaufenster_lifts_the_first_offer_into_a_wide_card():
    for i in range(4):
        _promo(f"Angebot {i}")
    body = _render(_tenant(style="schaufenster"), gruppe="Wochenangebote")
    assert "data-promo-hero" in body


def test_magazin_shows_conditions_on_the_card():
    _promo("Massage", target_rules={"weekdays": [0, 1, 2]})
    body = _render(_tenant(style="magazin"), gruppe="Wochenangebote")
    assert 'data-group-item="magazin"' in body
    assert "Mo" in body  # человеческая запись окна из rules_text


def test_countdown_sorts_by_time_left_and_respects_an_explicit_sort():
    _promo("Später", days=9)
    _promo("Zuerst", days=1)
    tenant = _tenant(style="countdown")
    body = _render(tenant, gruppe="Wochenangebote")
    assert body.index("Zuerst") < body.index("Später")
    # явный выбор посетителя сильнее — иначе его переключатель молча не работает
    body2 = _render(tenant, gruppe="Wochenangebote", sort="neu")
    assert 'data-group-grid="countdown"' in body2


def test_vergleich_marks_the_middle_column_only_when_the_count_is_odd():
    for i in range(3):
        _promo(f"Paket {i}")
    body = _render(_tenant(style="vergleich"), gruppe="Wochenangebote")
    assert "data-group-compare" in body and body.count("data-group-featured") == 1
    _promo("Paket 4")
    body = _render(_tenant(style="vergleich"), gruppe="Wochenangebote")
    assert "data-group-featured" not in body


def test_list_view_still_silences_every_group_layout():
    """Инвариант: `?ansicht=liste` — таблица при любом шаблоне группы."""
    _promo("Bio-Milch")
    body = _render(_tenant(style="prospekt"), gruppe="Wochenangebote", ansicht="liste")
    assert 'data-group-grid="prospekt"' not in body


@pytest.mark.parametrize("style", ["schaufenster", "prospekt", "magazin", "countdown", "vergleich"])
def test_every_layout_survives_a_single_offer_without_a_deadline(style):
    """Класс «шаблон разваливается на реальных данных»: одна акция и без срока."""
    _promo("Solo", days=0)
    body = _render(_tenant(style=style), gruppe="Wochenangebote")
    assert "Wochenangebote" in body


# ─────────────────────────── кабинет и Studio ───────────────────────────


def test_cabinet_lists_live_groups_and_saves_their_templates():
    """Строки берутся по живым акциям: осиротевшая запись словаря группой не станет."""
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.promotions import views

    tenant = TenantFactory(schema_name="public", slug="dl20g", name="DL20G")
    tenant.site_config = {"promo_groups": {"Umbenannt": "prospekt"}}
    tenant.save(update_fields=["site_config"])
    _promo("Bio-Milch", group="Wochenangebote")

    def _req(method, data=None):
        r = getattr(RequestFactory(), method)("/promotions/", data or {})
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.user = get_user_model()(is_active=True)
        r.tenant = tenant
        return r

    rows = views._promo_group_rows(_req("get"))
    assert rows == [{"name": "Wochenangebote", "style": ""}]

    resp = views.promotion_page_mode(_req("post", {"group_style:Wochenangebote": "magazin"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["promo_groups"]["Wochenangebote"] == "magazin"
    # прежние ключи страницы не пострадали (targeted-write)
    assert cfg["promo_groups"]["Umbenannt"] == "prospekt"

    views.promotion_page_mode(_req("post", {"group_style:Wochenangebote": ""}))
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert "Wochenangebote" not in cfg.get("promo_groups", {})
