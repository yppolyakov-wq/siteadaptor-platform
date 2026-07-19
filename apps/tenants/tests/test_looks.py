"""ST-1 «Каталог Look'ов»: реестр 3×14 + apply_look + ключ theme (тёмный Look).

Адверсариальный замок (образец CBLOCK_VARIANTS): КАЖДЫЙ Look каждого архетипа
проходит apply_look → normalize без потерь и идемпотентно; golden целы (theme —
presence-minimal ключ); применение шаблона/Look'а НЕ стирает чужие ключи
конфига (исправленный латентный баг класса W6). План: st1-looks-plan-2026-07-19.
"""

import pytest

from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ARCHETYPES = [k for k, _ in Tenant.BUSINESS_TYPES if k != "other"]


def test_registry_shape_three_looks_per_archetype():
    assert len(sitetemplates.LOOK_FAMILIES) == 3
    keys = [f["key"] for f in sitetemplates.LOOK_FAMILIES]
    assert len(set(keys)) == 3
    assert len(ARCHETYPES) == 14  # 3 × 14 = 42 Look'а
    for bt in ARCHETYPES:
        looks = sitetemplates.looks_for(bt)
        assert [lk["key"] for lk in looks] == keys
        for lk in looks:
            assert lk["accent"].startswith("#")


def test_normalize_theme_presence_minimal():
    assert "theme" not in siteconfig.normalize({})
    assert "theme" not in siteconfig.normalize({"theme": "light"})
    assert "theme" not in siteconfig.normalize({"theme": "junk"})
    assert siteconfig.normalize({"theme": "dark"})["theme"] == "dark"


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_look_survives_apply_and_normalize(business_type):
    """Адверсариальный замок: apply → значения семейства в конфиге 1:1, normalize
    идемпотентен, тёмная тема только у nacht, чужие ключи целы."""
    for family in sitetemplates.LOOK_FAMILIES:
        tenant = TenantFactory(
            business_type=business_type,
            site_config={
                "hero_title": "Mein Titel",  # текст владельца — не затирается
                "ui_mode": "simple",
                "board": {"labels": {"intake": "Neu!"}},
                "presence": {"mode": "on"},
            },
        )
        assert sitetemplates.apply_look(tenant, family["key"]) is True
        cfg = tenant.site_config
        # идемпотентность normalize (двойной прогон без изменений)
        assert siteconfig.normalize(cfg) == cfg
        # пачка Look'а материализована 1:1
        assert cfg["font"] == family["font"]
        assert cfg["typography"] == siteconfig.normalize_typography(family["typography"])
        assert cfg["site_defaults"] == siteconfig.normalize_site_defaults(family["site_defaults"])
        assert cfg["nav"]["style"] == family["nav_style"]
        assert cfg["hero_style"] == family["hero_style"]
        if family["theme"] == "dark":
            assert cfg.get("theme") == "dark"
        else:
            assert "theme" not in cfg
        # акцент архетипа
        assert tenant.primary_color == sitetemplates.look_accent(business_type, family["key"])
        # чужие ключи и тексты владельца целы (латентный баг W6-класса исправлен)
        assert cfg["hero_title"] == "Mein Titel"
        assert cfg["ui_mode"] == "simple"
        assert cfg["board"]["labels"]["intake"] == "Neu!"
        assert cfg["presence"] == {"mode": "on"}
        # повторное применение — идемпотентно
        before = dict(cfg)
        sitetemplates.apply_look(tenant, family["key"])
        assert tenant.site_config == before


def test_apply_template_preserves_foreign_keys_too():
    """Фикс распространяется и на старый apply_template (та же _apply-база)."""
    tenant = TenantFactory(
        business_type="bakery",
        site_config={"ui_mode": "simple", "seo": {"allow_ai": False}},
    )
    assert sitetemplates.apply_template(tenant, "laden") is True
    assert tenant.site_config["ui_mode"] == "simple"
    assert tenant.site_config["seo"]["allow_ai"] is False


def test_light_look_removes_dark_theme():
    tenant = TenantFactory(business_type="cafe", site_config={"theme": "dark"})
    sitetemplates.apply_look(tenant, "klar")
    assert "theme" not in tenant.site_config


def test_dark_default_rendered_on_storefront():
    """theme=dark → _base.html отдаёт tenantDark=true (посетительский тумблер сильнее)."""
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    from apps.promotions import public_views

    tenant = TenantFactory.build(site_config={"theme": "dark"})
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    html = public_views.storefront_home(request).content.decode()
    assert 'var tenantDark = "dark" === "dark"' in html
    light = TenantFactory.build()
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = light
    html = public_views.storefront_home(request).content.decode()
    assert 'var tenantDark = "" === "dark"' in html
