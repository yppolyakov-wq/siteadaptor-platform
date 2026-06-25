"""S2b: отдельный конструктор главной /dashboard/site/home/.

Композиция блоков главной (порядок/видимость секций + тизеры архетипов) живёт
здесь; сохранение мёржит в текущий site_config, не затрагивая остальной дизайн.
`site_view` («Site») больше НЕ перестраивает секции из своей формы — переносит
как есть (регрессия: пустая форма не должна гасить блоки).
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse("site-home") в редиректе


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)  # обойти login_required
    req.tenant = tenant
    return req


def test_home_builder_saves_blocks_and_preserves_design():
    tenant = TenantFactory(
        schema_name="public",
        slug="hb",
        name="HB",
        site_config={
            "hero_title": "Hallo",
            "nav": {"style": "centered", "sticky": False, "items": []},
        },
    )
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "order_archetypes": "2",
        "enabled_archetypes": "on",
        "order_products": "3",  # без enabled_ → выключается
        "arch_visible_catalog": "on",
        "arch_label_catalog": "Speisekarte",
        "arch_blurb_catalog": "Frisch & vegan",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302

    cfg = siteconfig.normalize(tenant.site_config)
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "hero" in enabled and "archetypes" in enabled
    assert "products" not in enabled  # снят
    # Композиция не затёрла остальной дизайн.
    assert cfg["hero_title"] == "Hallo"
    assert cfg["nav"]["style"] == "centered" and cfg["nav"]["sticky"] is False
    # Оверрайд тизера сохранён.
    assert cfg["archetypes"]["catalog"]["label"] == "Speisekarte"
    assert cfg["archetypes"]["catalog"]["blurb"] == "Frisch & vegan"


def test_home_builder_saves_layout_preset():
    """M20U-7: пресет раскладки секции-сетки сохраняется в layout секции."""
    tenant = TenantFactory(schema_name="public", slug="hbl", name="HBL")
    data = {
        "order_products": "1",
        "enabled_products": "on",
        "layout_preset_products": "cols3",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["layout"]["preset"] == "cols3"
    assert products["layout"]["cols"] == 3  # пресет развёрнут normalize_layout


def test_home_builder_saves_limit():
    """M20U-7: число элементов секции-превью сохраняется (клампится в normalize)."""
    tenant = TenantFactory(schema_name="public", slug="hbn", name="HBN")
    data = {"order_products": "1", "enabled_products": "on", "limit_products": "4"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_limit(cfg, "products") == 4


def test_home_builder_saves_product_source():
    """M20U-7: источник товаров секции products сохраняется."""
    tenant = TenantFactory(schema_name="public", slug="hbs", name="HBS")
    data = {"order_products": "1", "enabled_products": "on", "source_products": "newest"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.product_source(cfg) == "newest"


def test_home_builder_hides_view_all_when_unchecked():
    """M20U-7: чекбокс «View all» не прислан → ссылка скрывается (show_all=False)."""
    tenant = TenantFactory(schema_name="public", slug="hbv", name="HBV")
    data = {"order_products": "1", "enabled_products": "on"}  # show_all_products не прислан
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_show_all(cfg, "products") is False


def test_home_builder_saves_section_title():
    """M20U-7: кастомный заголовок секции сохраняется в section_titles."""
    tenant = TenantFactory(schema_name="public", slug="hbt", name="HBT")
    data = {"order_events": "1", "enabled_events": "on", "title_events": "Unsere Retreats"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["section_titles"]["events"] == "Unsere Retreats"


def test_home_builder_saves_catalog_layout():
    """M20U-7 (per-page): пресет раскладки каталога/номеров сохраняется."""
    tenant = TenantFactory(schema_name="public", slug="hbcat", name="HBCAT")
    data = {"catalog_preset": "gallery", "stay_index_preset": "cols4"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_layout"]["preset"] == "gallery"
    assert cfg["stay_index_layout"]["preset"] == "cols4"


def test_home_builder_get_renders_layout_select():
    """M20U-7: для секций-сеток в билдере отрисован селектор раскладки."""
    tenant = TenantFactory(schema_name="public", slug="hbl2", name="HBL2")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'name="layout_preset_products"' in body
    assert 'name="layout_preset_hero"' not in body  # hero — не сетка


def test_home_builder_gallery_upload_and_delete(tmp_path, settings):
    """M20e: фото галереи грузятся/удаляются прямо в билдере (multipart-формы)."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    settings.MEDIA_ROOT = str(tmp_path)
    tenant = TenantFactory(schema_name="public", slug="hbg", name="HBG")

    buf = BytesIO()
    Image.new("RGB", (40, 40), "#abc").save(buf, format="PNG")
    upload = SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")
    req = _request("post", "/dashboard/site/home/", {"action": "upload_gallery"}, tenant)
    req.FILES["images"] = upload  # RequestFactory data не кладёт файлы — добавляем вручную
    resp = views.home_builder_view(req)
    assert resp.status_code == 302
    gallery = siteconfig.normalize(tenant.site_config)["gallery"]
    assert len(gallery) == 1 and gallery[0]["url"]

    # удаление по id
    img_id = gallery[0]["id"]
    req2 = _request(
        "post",
        "/dashboard/site/home/",
        {"action": "delete_gallery_image", "image_id": img_id},
        tenant,
    )
    assert views.home_builder_view(req2).status_code == 302
    assert siteconfig.normalize(tenant.site_config)["gallery"] == []


def test_home_builder_get_renders():
    tenant = TenantFactory(schema_name="public", slug="hb2", name="HB2")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "order_hero" in body  # форма секций отрисована
    assert "arch_visible_catalog" in body  # карточки архетипов
    assert 'name="accent"' in body and 'name="font"' in body  # M20f: контролы дизайна


def test_home_builder_saves_design():
    """M20f: билдер сохраняет шрифт/стиль hero (site_config) и акцент (Tenant)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbd",
        name="HBD",
        site_config={"sections": [{"key": "hero", "enabled": True}]},
        primary_color="#000000",
    )
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "font": "serif",
        "hero_accent": "on",
        "accent": "#ff8800",
        "storefront_root": "home",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["font"] == "serif" and cfg["hero_style"] == "accent"
    assert tenant.primary_color == "#ff8800"


def test_home_builder_saves_content_sections():
    """M20d: контент-секции (CTA/FAQ/Testimonials) правятся прямо в билдере."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbc",
        name="HBC",
        site_config={"sections": [{"key": "cta", "enabled": True}]},
    )
    data = {
        "enabled_cta": "on",
        "order_cta": "1",
        "cta_title": "Jetzt buchen",
        "cta_button_label": "Termin",
        "cta_button_url": "/termin/",
        "faq_text": "Parkplatz? | Ja, direkt davor.",
        "testimonials_text": "Anna | Top!",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["cta"]["title"] == "Jetzt buchen" and cfg["cta"]["button_url"] == "/termin/"
    assert cfg["faq"] == [{"q": "Parkplatz?", "a": "Ja, direkt davor."}]
    assert cfg["testimonials"] == [{"name": "Anna", "text": "Top!"}]


def test_site_view_does_not_wipe_homepage_composition():
    """Регрессия S2b: форма «Site» не присылает order_/enabled_ → секции и
    оверрайды тизеров должны сохраниться (раньше site_view строил их из POST)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="sv",
        name="SV",
        site_config={
            "sections": [{"key": "archetypes", "enabled": True}],
            "archetypes": {"catalog": {"label": "Speisekarte", "blurb": "", "hidden": False}},
        },
    )
    resp = views.site_view(_request("post", "/dashboard/site/", {}, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "archetypes" in enabled  # не погашено пустой формой
    assert cfg["archetypes"]["catalog"]["label"] == "Speisekarte"  # оверрайд цел
