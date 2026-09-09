"""STU-12g (срез 3): Студия больше не владеет ГЛОБАЛЬНЫМ дизайном.

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12g): «Студия: `collect()`
НЕ шлёт ключи темы, Save Студии их не пишет и не роняет (presence); области `theme`,
`quickstart` удалены; `storefront_root` — в панель главной».

Главный инвариант среза — W6: владелец выставил цвет/шрифт/типографику/тему/карточки на
`/dashboard/design/`, вернулся в Студию, подвинул блок и нажал Save — НИЧЕГО из этого не
должно измениться. Сегодня три ветки `home_builder_view` пишут эти ключи безусловно
(`typography`, полная пересборка `site_defaults`, `storefront_root`), поэтому после удаления
полей из формы первый же Save их обнулил бы.

НЕ переезжают и остаются настройками СТРАНИЦЫ (реестр `apps/core/studio_pages.py`):
`card_style`, `promo_card`, `category_page_style`, `promo_group_style`, `text_width`.
"""

import pathlib
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")

# поля глобального дизайна: их место — экран кабинета, а не канва
MOVED_FIELDS = (
    "accent",
    "font",
    "typo_weight_head",
    "typo_line_height",
    "sd_card_radius",
    "sd_card_shadow",
    "sd_card_padding",
    "sd_card_bg",
    "sd_card_bg_on",
    "sd_page_bg",
    "sd_page_bg_on",
    "sd_page_bg_present",
    "sd_card_chrome",
    "sd_media_shape",
    "sd_variant_style",
    "sd_card_slider",
    "quick_add",
    "quick_add_present",
    "wishlist",
    "wishlist_present",
    "theme",
)

# поля, которые ОСТАЮТСЯ в Студии (настройки страницы и композиции)
STUDIO_FIELDS = (
    "hero_style",
    "sd_card_style",
    "sd_promo_card",
    "sd_category_page_style",
    "sd_promo_group_style",
    "sd_text_width",
    "storefront_root",
)


def _req(method, tenant, data=None):
    req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _builder(tenant):
    return views.home_builder_view(_req("get", tenant)).content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_req("post", tenant, data))
    assert resp.status_code == 302, resp.status_code
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def _designed(**extra):
    """Тенант, у которого дизайн уже выставлен на экране «Design des Shops»."""
    cfg = {
        "font": "editorial",
        "theme": "dark",
        "typography": {"weight_head": 800, "line_height": 1.8},
        "quick_add": True,
        "wishlist": True,
        "storefront_root": "catalog",
        "site_defaults": {
            "card_radius": 20,
            "card_shadow": True,
            "card_padding": 16,
            "card_bg": "#112233",
            "page_bg": "#f5f5f4",
            "card_chrome": "hairline",
            "media_shape": "round",
            "variant_style": "buttons",
            "card_slider": True,
            # настройки СТРАНИЦЫ — остаются во владении Студии
            "card_style": "overlay",
            "text_width": "wide",
        },
    }
    cfg.update(extra)
    return cfg


def test_studio_no_longer_ships_global_design_fields():
    body = _builder(TenantFactory(slug="stth1", name="StTh1"))
    for name in MOVED_FIELDS:
        assert f'name="{name}"' not in body, f"{name} переехал на /dashboard/design/"
    for name in STUDIO_FIELDS:
        assert f'name="{name}"' in body, f"{name} — настройка Студии, обязан остаться"


def test_areas_theme_and_quickstart_are_gone():
    body = _builder(TenantFactory(slug="stth2", name="StTh2"))
    for area in ("theme", "quickstart"):
        assert f'data-bld-area="{area}"' not in body, area
    tpl = TPL.read_text(encoding="utf-8")
    assert '"quickstart"' not in tpl, "мёртвая запись карты подписей"


def test_studio_save_keeps_the_design_set_in_the_cabinet():
    """W6: Save Студии не роняет ничего из глобального дизайна."""
    tenant = TenantFactory(slug="stth3", name="StTh3", site_config=_designed())
    tenant.primary_color = "#123456"
    tenant.save(update_fields=["primary_color"])
    cfg = _save(tenant, {"order_faq": "1", "enabled_faq": "on"})
    assert cfg["font"] == "editorial"
    assert cfg["theme"] == "dark"
    assert cfg["typography"] == {"weight_head": 800, "line_height": 1.8}
    assert cfg["quick_add"] is True and cfg["wishlist"] is True
    sd = cfg["site_defaults"]
    assert sd["card_radius"] == 20 and sd["card_shadow"] is True and sd["card_padding"] == 16
    assert sd["card_bg"] == "#112233" and sd["page_bg"] == "#f5f5f4"
    assert sd["card_chrome"] == "hairline" and sd["media_shape"] == "round"
    assert sd["variant_style"] == "buttons" and sd["card_slider"] == "on"
    tenant.refresh_from_db()
    assert tenant.primary_color == "#123456", "акцент — поле Tenant, Студия его не трогает"


def test_studio_save_keeps_the_start_page():
    """`storefront_root` писался БЕЗ presence-guard: Save сбрасывал бы витрину на «home»."""
    tenant = TenantFactory(slug="stth4", name="StTh4", site_config=_designed())
    assert _save(tenant, {"order_faq": "1"})["storefront_root"] == "catalog"


def test_studio_still_owns_page_scoped_settings():
    """Настройки страницы Студия по-прежнему пишет — иначе срез утащил бы лишнее."""
    tenant = TenantFactory(slug="stth5", name="StTh5", site_config=_designed())
    cfg = _save(
        tenant,
        {
            "sd_present": "1",
            "sd_card_style": "compact",
            "tw_present": "1",
            "sd_text_width": "narrow",
            "storefront_root": "home",
        },
    )
    assert cfg["site_defaults"]["card_style"] == "compact"
    assert cfg["site_defaults"]["text_width"] == "narrow"
    assert cfg["storefront_root"] == "home"
    # и при этом глобальный дизайн цел
    assert cfg["site_defaults"]["card_radius"] == 20 and cfg["font"] == "editorial"


def test_draft_no_longer_carries_theme_but_still_carries_page_keys():
    """Черновик шлёт ВСЮ форму: дефолты `font:"system"` и `typography:{0,0}` перекрасили бы
    превью в системный шрифт, а гейт `if (sdR || sdSh)` увёл бы вместе с собой и
    НЕпереезжающие ключи страницы (card_style/promo_card/…)."""
    tpl = TPL.read_text(encoding="utf-8")
    i = tpl.index("function collect(")
    fn = tpl[i : tpl.index("function push(", i)]
    # сверяем СЕЛЕКТОРЫ, а не голые имена: имя может законно встретиться в комментарии
    for gone in ("[name=font]", "[name=accent]", "'typo_weight_head'", "'sd_card_radius'"):
        assert gone not in fn, f"collect() не должен читать {gone}"
    for kept in ("sd_card_style", "sd_promo_card", "sd_text_width"):
        assert kept in fn, f"{kept} — ключ страницы, черновик обязан его слать"


def test_template_and_demo_actions_left_the_studio():
    """Шаблоны витрины и демо-контент живут на экране «Design des Shops» (4A)."""
    body = _builder(TenantFactory(slug="stth6", name="StTh6"))
    for action in ("apply_template", "load_demo", "clear_demo"):
        assert f'value="{action}"' not in body, action
    tenant = TenantFactory(slug="stth7", name="StTh7", site_config=_designed())
    # ветка удалена → POST проваливается в обычное сохранение и НЕ раскладывает шаблон
    cfg = _save(
        tenant,
        {"action": "apply_template", "template": "gastro", "order_faq": "1", "enabled_faq": "on"},
    )
    on = {s["key"] for s in cfg["sections"] if s.get("enabled")}
    assert on == {"faq"}, f"шаблон gastro не должен раскладываться из Студии: {on}"
