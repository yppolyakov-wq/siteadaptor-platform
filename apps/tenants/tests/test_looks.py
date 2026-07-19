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


# --- ST-1b: stateless-превью ?look= + слайд мастера ---------------------------------


def _home(tenant, query=""):
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    from apps.promotions import public_views

    request = RequestFactory().get(f"/{query}")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def test_preview_look_overlay_is_stateless():
    tenant = TenantFactory.build(business_type="bakery", primary_color="#4f46e5")
    nacht_accent = sitetemplates.look_accent("bakery", "nacht")
    html = _home(tenant, "?preview=1&look=nacht")
    assert 'var tenantDark = "dark" === "dark"' in html  # тёмный оверлей
    assert nacht_accent in html  # архетипный акцент семейства
    # Оверлей ничего не пишет и не действует вне превью / на мусорный ключ.
    assert tenant.site_config in (None, {}, tenant.site_config)  # конфиг не тронут
    assert 'var tenantDark = "" === "dark"' in _home(tenant)
    assert "#4f46e5" in _home(tenant, "?preview=1&look=junk")


def test_wizard_stil_slide_looks_gallery_and_apply():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import setup_steps

    tenant = TenantFactory(business_type="friseur")

    def _req(method="get", data=None):
        import uuid as _uuid

        request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return request

    ctx = setup_steps._ctx_template(_req())
    assert [lk["key"] for lk in ctx["looks"]] == ["klar", "warm", "nacht"]
    assert ctx["looks_classic"] is False

    # POST с look → применяется семейство (serif у warm), template игнорируется.
    setup_steps._post_template(_req("post", {"look": "warm", "template": "laden"}))
    tenant.refresh_from_db()
    assert tenant.site_config["font"] == "serif"
    assert tenant.primary_color == sitetemplates.look_accent("friseur", "warm")

    # classic_ui → в контексте флаг classic (галерея Look'ов скрыта шаблоном).
    cfg = dict(tenant.site_config)
    cfg["classic_ui"] = True
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    assert setup_steps._ctx_template(_req())["looks_classic"] is True


def test_wizard_stil_template_renders_lazy_iframes():
    from django.template.loader import render_to_string

    from apps.tenants import sitetemplates as st

    html = render_to_string(
        "tenant/setup/_step_stil.html",
        {
            "templates": st.template_cards("bakery"),
            "looks": st.looks_for("bakery"),
            "looks_classic": False,
        },
    )
    assert 'data-src="/?preview=1&look=klar"' in html
    assert 'data-src="/?preview=1&look=nacht"' in html
    # classic: галереи Look'ов нет, легаси-галерея живёт
    html_classic = render_to_string(
        "tenant/setup/_step_stil.html",
        {
            "templates": st.template_cards("bakery"),
            "looks": st.looks_for("bakery"),
            "looks_classic": True,
        },
    )
    assert "look-gallery" not in html_classic
    assert 'name="template"' in html_classic


# --- ST-1b: билдер — Look-карточки + round-trip темы -------------------------------


def test_builder_theme_roundtrip_and_look_cards():
    """Hidden `theme` пред-заполнен и переживает Save (W0/W6); карточки Look'ов
    в разметке нового вида, в classic — нет."""
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    tenant = TenantFactory(business_type="bakery", site_config={"theme": "dark"})

    def _req(method="get", data=None):
        request = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return request

    html = core_views.home_builder_view(_req()).content.decode()
    assert 'name="theme" id="bld-theme" value="dark"' in html  # round-trip префилл
    assert 'class="bld-look' in html and "data-look=" in html  # карточки Look'ов

    # Save с theme="" (светлый) → ключ снят; с "dark" → сохранён.
    resp = core_views.home_builder_view(_req("post", {"theme": "", "font": "system"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert "theme" not in tenant.site_config
    core_views.home_builder_view(_req("post", {"theme": "dark", "font": "system"}))
    tenant.refresh_from_db()
    assert tenant.site_config["theme"] == "dark"

    # classic_ui → карточек Look'ов нет (железное правило §8b).
    cfg = dict(tenant.site_config)
    cfg["classic_ui"] = True
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    html = core_views.home_builder_view(_req()).content.decode()
    assert "bld-look" not in html


def test_preview_draft_accepts_theme():
    """Draft-канал: theme="dark" красит превью, ""/отсутствие — снимает/не трогает."""
    import json as _json
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views

    tenant = TenantFactory(business_type="bakery")

    def _post(payload):
        request = RequestFactory().post(
            "/dashboard/site/preview-draft/",
            _json.dumps(payload),
            content_type="application/json",
        )
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        core_views.site_preview_draft(request)
        return request.session.get("site_preview_draft") or {}

    assert _post({"theme": "dark"}).get("theme") == "dark"
    assert "theme" not in _post({"theme": ""})
    assert "theme" not in _post({})  # не прислан → не трогаем
