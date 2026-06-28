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


def test_home_builder_preserves_page_layouts():
    """Сохранение главной не затирает per-page раскладки (они на «Pages»)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbpp",
        name="HBPP",
        site_config={"catalog_layout": {"preset": "gallery"}},
    )
    data = {"order_products": "1", "enabled_products": "on"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_layout"]["preset"] == "gallery"  # сохранён


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


def test_home_builder_get_renders_undo_redo():
    """E.1: панель Undo/Redo + клиентский стек снимков отрисованы в билдере."""
    tenant = TenantFactory(schema_name="public", slug="hbur", name="HBUR")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'id="home-undo"' in body and 'id="home-redo"' in body  # кнопки
    assert "function snapshot()" in body and "function undo()" in body  # история
    assert "Ctrl+Z" in body  # подсказка клавиш


def test_home_builder_get_renders_block_popup():
    """E.2: попап настроек блока + маркеры cb-row для переноса контролов."""
    tenant = TenantFactory(schema_name="public", slug="hbpop", name="HBPOP")
    # C-блок, чтобы проверить разметку cb-row (попап переносит её реальные контролы).
    views.home_builder_view(
        _request(
            "post", "/dashboard/site/home/", {"action": "add_block", "block_type": "text"}, tenant
        )
    )
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'id="bld-block-popup"' in body  # контейнер попапа
    assert "function openBlockPopup" in body  # логика переноса контролов
    assert 'class="cb-row' in body and "data-cb-id=" in body  # маркеры C-блока


def test_home_builder_get_renders_inserter():
    """E.3: библиотека блоков инсертера «+» + инъекция зон в превью отрисованы."""
    tenant = TenantFactory(schema_name="public", slug="hbins", name="HBINS")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'id="bld-inserter"' in body  # библиотека блоков
    assert 'class="bld-ins-btn' in body  # кнопки типов
    assert "function submitInsert" in body  # add_block с add_after
    assert "data-sf-ins" in body  # инъекция зоны «+» в превью


def test_home_builder_get_renders_canvas_drag():
    """E.4: drag-on-canvas — инъекция ручек + перенос порядка в редактор."""
    tenant = TenantFactory(schema_name="public", slug="hbdrag", name="HBDRAG")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert "function moveBlock" in body  # маппинг порядка в order-инпуты
    assert "data-sf-drag" in body  # инъекция ручки на блок превью


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


def test_home_builder_saves_visual_radius_from_slider():
    """SE-3d: точное значение радиуса (Эксперт, slider) сохраняется и клампится."""
    tenant = TenantFactory(schema_name="public", slug="hbvr", name="HBVR")
    data = {"order_products": "1", "enabled_products": "on", "visual_radius_px_products": "12"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products") == {"radius": 12, "shadow": False}


def test_home_builder_visual_radius_clamped():
    """SE-3d: радиус за пределами 0..24 клампится (slider не должен пробить лимит)."""
    tenant = TenantFactory(schema_name="public", slug="hbvc", name="HBVC")
    data = {"order_products": "1", "enabled_products": "on", "visual_radius_px_products": "999"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products")["radius"] == 24


def test_home_builder_visual_radius_basic_toggle_fallback():
    """SE-3d: без slider basic-тоггл «Round corners» (on) даёт выраженные 16px."""
    tenant = TenantFactory(schema_name="public", slug="hbvt", name="HBVT")
    data = {"order_products": "1", "enabled_products": "on", "visual_radius_products": "on"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products")["radius"] == 16


def test_home_builder_visual_radius_default_zero():
    """SE-3d: без visual-полей радиус=0 (= «не переопределять», без регрессии вида)."""
    tenant = TenantFactory(schema_name="public", slug="hbv0", name="HBV0")
    data = {"order_products": "1", "enabled_products": "on"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products") == {"radius": 0, "shadow": False}


def test_home_builder_saves_visual_shadow():
    """SE-3d: чекбокс тени сохраняется (Эксперт)."""
    tenant = TenantFactory(schema_name="public", slug="hbvs", name="HBVS")
    data = {"order_products": "1", "enabled_products": "on", "visual_shadow_products": "on"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products")["shadow"] is True


def test_home_builder_get_renders_mode_toggle_and_visual_controls():
    """SE-1f/SE-3d: режим Обычный/Эксперт + визуальные контролы отрисованы в билдере."""
    tenant = TenantFactory(schema_name="public", slug="hbmt", name="HBMT")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'id="bld-mode-basic"' in body and 'id="bld-mode-expert"' in body  # SE-1f тумблер
    assert "sf_editor_mode" in body  # localStorage-ключ режима
    assert 'name="visual_radius_products"' in body  # basic-тоггл скругления
    assert 'name="visual_radius_px_products"' in body  # expert-slider радиуса
    assert 'name="visual_shadow_products"' in body  # expert-тень


def test_home_builder_get_renders_move_buttons():
    """SE-1c: дружелюбные кнопки перемещения ↑▼ (работают и в обычном режиме)."""
    tenant = TenantFactory(schema_name="public", slug="hbmv", name="HBMV")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'class="blk-up' in body and 'class="blk-down' in body  # кнопки в строке блока
    assert "function moveByOrder" in body  # value-based перестановка
    assert "function sortListByOrderValue" in body  # синхрон DOM-списка


def test_home_builder_get_renders_preview_page_switcher():
    """SE-2a-1: переключатель страницы превью (главная + лендинги активных архетипов)."""
    tenant = TenantFactory(
        schema_name="public", slug="hbpg", name="HBPG", enabled_modules=["catalog", "stays"]
    )
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'id="home-prev-page"' in body  # селектор страниц
    assert "function previewUrl" in body  # URL превью текущей страницы
    assert "/sortiment/" in body or "/unterkunft/" in body  # лендинг архетипа в опциях


def test_home_builder_get_renders_landing_inspectors():
    """SE-2a-2/SE-2b-1: per-page инспекторы лендингов (каталог/события/номера)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbcat",
        name="HBCAT",
        enabled_modules=["catalog", "events", "stays"],
    )
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'data-page-key="catalog"' in body and 'name="catalog_preset"' in body
    assert 'data-page-key="events"' in body and 'name="events_preset"' in body
    assert 'data-page-key="stay_rooms"' in body and 'name="stay_preset"' in body


def test_home_builder_saves_landing_layouts():
    """SE-2a-2/SE-2b-1: раскладки лендингов сохраняются из канвы (per-page инспектор)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbcl",
        name="HBCL",
        enabled_modules=["catalog", "events", "stays"],
    )
    data = {"catalog_preset": "cols2", "events_preset": "cols3", "stay_preset": "cols4"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_layout"]["preset"] == "cols2" and cfg["catalog_layout"]["cols"] == 2
    assert cfg["events_index_layout"]["preset"] == "cols3"
    assert cfg["stay_index_layout"]["preset"] == "cols4"


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
