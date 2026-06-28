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


def test_home_builder_inserter_lists_block_templates():
    """SE-4c: инсертер «+» предлагает вставить сохранённый блок-шаблон в позицию."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbinstpl",
        name="HBINSTPL",
        site_config={
            "block_templates": {
                "tplA": {"key": "text", "label": "Greeting", "data": {"title": "Hi"}}
            }
        },
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'class="bld-ins-tpl' in body and 'data-tpl="tplA"' in body  # кнопка вставки шаблона
    assert "function submitInsertTemplate" in body  # use_block_template + insert_after
    assert "showDropLine" in body  # SE-4c: индикатор позиции при перетаскивании


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
    v = siteconfig.section_visual(cfg, "products")
    assert v["radius"] == 12 and v["shadow"] is False


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
    v = siteconfig.section_visual(cfg, "products")
    assert v["radius"] == 0 and v["shadow"] is False


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


def test_home_builder_get_renders_event_detail_inspector():
    """SE-2b-2: on-canvas инспектор порядка/видимости секций детальной события."""
    tenant = TenantFactory(
        schema_name="public", slug="hbed", name="HBED", enabled_modules=["events"]
    )
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert 'data-page-key="event_detail"' in body  # клик-цель инспектора
    assert 'name="ed_order_faq"' in body and 'name="ed_visible_idea"' in body  # реестр секций
    assert 'class="ed-up' in body and "function edMove" in body  # ↑▼ value-based


def test_home_builder_get_includes_event_detail_preview_page():
    """SE-2b-2: переключатель превью включает конкретное событие (детальную на канве)."""
    from datetime import timedelta

    from django.urls import reverse
    from django.utils import timezone

    from apps.events.models import Event

    tenant = TenantFactory(
        schema_name="public", slug="hbep", name="HBEP", enabled_modules=["events"]
    )
    ev = Event.objects.create(
        title="Konzert",
        starts_at=timezone.now() + timedelta(days=5),
        status=Event.STATUS_PUBLISHED,
        capacity=10,
    )
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    body = resp.content.decode()
    assert reverse("storefront-event", args=[ev.pk]) in body  # опция превью события


def test_home_builder_saves_event_detail_order():
    """SE-2b-2: порядок/видимость секций детальной события сохраняются с канвы."""
    tenant = TenantFactory(
        schema_name="public", slug="hbeo", name="HBEO", enabled_modules=["events"]
    )
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "ed_order_faq": "1",
        "ed_visible_faq": "on",
        "ed_order_for_whom": "2",
        "ed_visible_for_whom": "on",
        "ed_order_idea": "3",  # ed_visible_idea не прислан → скрыта
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    order = siteconfig.event_detail_order(cfg)
    assert order[0] == "faq" and "idea" not in order  # faq поднят, idea скрыта
    assert order.index("faq") < order.index("for_whom")


def test_home_builder_save_without_inspector_keeps_event_detail():
    """SE-2b-2 presence-guard: POST без ed_-полей не скрывает все секции детальной."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbeg",
        name="HBEG",
        enabled_modules=["events"],
        site_config={"event_detail": {"order": ["faq"], "hidden": ["idea"]}},
    )
    data = {"order_hero": "1", "enabled_hero": "on"}  # инспектор не прислан
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    order = siteconfig.event_detail_order(cfg)
    assert order[0] == "faq" and "idea" not in order  # сохранённый порядок цел


def test_home_builder_add_category_creates_live_category():
    """SE-2c-1: мини-форма «+ Kategorie» создаёт живую категорию (видимую на витрине)."""
    from apps.catalog.models import Category

    tenant = TenantFactory(schema_name="public", slug="hbac", name="HBAC")
    data = {"action": "add_category", "name_de": "Brot"}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cat = Category.objects.get(slug="brot")
    assert cat.name["de"] == "Brot" and cat.is_active is True  # сразу видима


def test_home_builder_add_category_under_parent():
    """SE-2c-1: можно создать подкатегорию, указав родителя в мини-форме."""
    from apps.catalog.models import Category

    tenant = TenantFactory(schema_name="public", slug="hbacp", name="HBACP")
    parent = Category.objects.create(name={"de": "Backwaren"}, slug="backwaren")
    data = {"action": "add_category", "name_de": "Brot", "parent": str(parent.pk)}
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    assert Category.objects.get(slug="brot").parent_id == parent.pk


def test_home_builder_add_category_invalid_name():
    """SE-2c-1: пустое имя → категория не создаётся, без 500."""
    from apps.catalog.models import Category

    tenant = TenantFactory(schema_name="public", slug="hbaci", name="HBACI")
    resp = views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "add_category", "name_de": ""}, tenant)
    )
    assert resp.status_code == 302
    assert Category.objects.count() == 0


def test_home_builder_get_renders_add_category_form():
    """SE-2c-1: форма быстрого создания категории отрисована при активном каталоге."""
    tenant = TenantFactory(schema_name="public", slug="hbacf", name="HBACF")
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'value="add_category"' in body and 'name="name_de"' in body


def test_home_builder_saves_global_card_bg_padding():
    """SE-3d: глобальные фон/отступы карточек сохраняются (фон — лишь при включённом тоггле)."""
    tenant = TenantFactory(schema_name="public", slug="hbsdbp", name="HBSDBP")
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "sd_card_padding": "16",
        "sd_card_bg": "#112233",
        "sd_card_bg_on": "on",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    sd = siteconfig.normalize(tenant.site_config)["site_defaults"]
    assert sd["card_padding"] == 16 and sd["card_bg"] == "#112233"


def test_home_builder_global_bg_ignored_without_toggle():
    """SE-3d: без тоггла sd_card_bg_on фон не применяется (color-input всегда шлёт значение)."""
    tenant = TenantFactory(schema_name="public", slug="hbsdbn", name="HBSDBN")
    data = {"order_hero": "1", "enabled_hero": "on", "sd_card_bg": "#112233"}  # без _on
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert siteconfig.normalize(tenant.site_config)["site_defaults"]["card_bg"] == ""


def test_home_builder_saves_section_visual_padding():
    """SE-3d: пер-секционный отступ карточек сохраняется в visual.padding."""
    tenant = TenantFactory(schema_name="public", slug="hbsvp", name="HBSVP")
    data = {"order_products": "1", "enabled_products": "on", "visual_padding_products": "8"}
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    assert siteconfig.section_visual(cfg, "products")["padding"] == 8


def test_home_builder_saves_per_device_columns():
    """SE-3c: пер-девайс число колонок секции (📱/▭/🖥) сохраняется в layout."""
    tenant = TenantFactory(schema_name="public", slug="hbpd", name="HBPD")
    data = {
        "order_products": "1",
        "enabled_products": "on",
        "layout_preset_products": "cols4",
        "mobile_products": "1",
        "tablet_products": "3",
        "cols_products": "4",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    lay = siteconfig.section_layout(cfg, "products")
    assert lay["mobile"] == 1 and lay["tablet"] == 3 and lay["cols"] == 4
    assert "sm:grid-cols-3" in siteconfig.grid_class_string(lay)  # планшет = 3


def test_home_builder_get_renders_per_device_columns():
    """SE-3c: поля пер-девайс колонок отрисованы для секций-сеток."""
    tenant = TenantFactory(schema_name="public", slug="hbpdg", name="HBPDG")
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'name="tablet_products"' in body and 'name="mobile_products"' in body


def test_home_builder_get_renders_micro_templates():
    """SE-3a: кнопки «Quick styles» отрисованы для секций-сеток + JS-распаковка."""
    tenant = TenantFactory(schema_name="public", slug="hbmt2", name="HBMT2")
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'class="mt-btn' in body and "data-preset=" in body  # кнопки с пресетом
    assert ".mt-btn" in body  # JS-обработчик распаковки


def test_home_builder_saves_typography():
    """SE-3b: начертание заголовков + межстрочный интервал сохраняются (валидируются)."""
    tenant = TenantFactory(schema_name="public", slug="hbty", name="HBTY")
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "typo_weight_head": "700",
        "typo_line_height": "1.6",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    typo = siteconfig.normalize(tenant.site_config)["typography"]
    assert typo == {"weight_head": 700, "line_height": 1.6}


def test_home_builder_typography_invalid_resets():
    """SE-3b: невалидный вес/интервал → 0 (= дефолт, без регрессии)."""
    tenant = TenantFactory(schema_name="public", slug="hbtyi", name="HBTYI")
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "typo_weight_head": "0",
        "typo_line_height": "0",
    }
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert siteconfig.normalize(tenant.site_config)["typography"] == {
        "weight_head": 0,
        "line_height": 0.0,
    }


def test_home_builder_get_renders_typography_controls():
    """SE-3b: селекторы начертания/интервала отрисованы с текущими значениями."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbtyg",
        name="HBTYG",
        site_config={"typography": {"weight_head": 600, "line_height": 1.8}},
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'name="typo_weight_head"' in body and 'name="typo_line_height"' in body


def test_home_builder_get_renders_apply_all_landings():
    """SE-2d-4: контрол «применить раскладку ко всем лендингам» отрисован."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbaa",
        name="HBAA",
        enabled_modules=["catalog", "events", "stays"],
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'id="apply-all-landings"' in body and 'id="apply-all-preset"' in body
    assert "apply-all-landings" in body and 'name="catalog_preset"' in body  # связка с селекторами


def test_home_builder_saves_global_card_style():
    """SE-2d-3: глобальный стиль карточек (site_defaults) сохраняется из конструктора."""
    tenant = TenantFactory(schema_name="public", slug="hbsd", name="HBSD")
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "sd_card_radius": "12",
        "sd_card_shadow": "on",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["site_defaults"]["card_radius"] == 12 and cfg["site_defaults"]["card_shadow"] is True


def test_home_builder_global_card_radius_clamped():
    """SE-2d-3: глобальный radius клампится 0..24 (мусор/перебор → 24)."""
    tenant = TenantFactory(schema_name="public", slug="hbsdc", name="HBSDC")
    data = {"order_hero": "1", "enabled_hero": "on", "sd_card_radius": "999"}
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    assert (
        cfg["site_defaults"]["card_radius"] == 24 and cfg["site_defaults"]["card_shadow"] is False
    )


def test_home_builder_get_renders_global_card_style():
    """SE-2d-3: контрол глобального стиля карточек отрисован с текущим значением."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbsdg",
        name="HBSDG",
        site_config={"site_defaults": {"card_radius": 8}},
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'name="sd_card_radius" min="0" max="24" value="8"' in body
    assert 'name="sd_card_shadow"' in body


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


def test_home_builder_save_block_as_template():
    """SE-4a: сохранить C-блок как многоразовый шаблон (данные из POST)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbsbt",
        name="HBSBT",
        site_config={
            "sections": [{"key": "text", "id": "blk1", "enabled": True, "data": {"title": "Hi"}}]
        },
    )
    data = {
        "action": "save_block_template:blk1",
        "cb_type_blk1": "text",
        "cb_blk1_title": "Hi",
        "cb_blk1_body": "X",
        "tpl_label_blk1": "Greeting",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    bt = siteconfig.normalize(tenant.site_config)["block_templates"]
    assert len(bt) == 1
    t = next(iter(bt.values()))
    assert t["key"] == "text" and t["label"] == "Greeting" and t["data"]["title"] == "Hi"


def test_home_builder_use_block_template_inserts_copy():
    """SE-4a: вставка из шаблона создаёт новый C-блок с теми же данными."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbubt",
        name="HBUBT",
        site_config={
            "block_templates": {"tplA": {"key": "text", "label": "G", "data": {"title": "Hi"}}}
        },
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "use_block_template:tplA"}, tenant)
    )
    cfg = siteconfig.normalize(tenant.site_config)
    inserted = [s for s in cfg["sections"] if s["key"] == "text" and s.get("id")]
    assert any(s["data"].get("title") == "Hi" for s in inserted)


def test_home_builder_delete_block_template():
    """SE-4a: удаление шаблона из библиотеки."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbdbt",
        name="HBDBT",
        site_config={
            "block_templates": {"tplA": {"key": "text", "label": "G", "data": {"title": "Hi"}}}
        },
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "delete_block_template:tplA"}, tenant)
    )
    assert siteconfig.normalize(tenant.site_config)["block_templates"] == {}


def test_home_builder_get_renders_block_template_library():
    """SE-4a: библиотека сохранённых шаблонов отрисована (вставить/удалить)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbbtl",
        name="HBBTL",
        site_config={
            "block_templates": {
                "tplA": {"key": "text", "label": "Greeting", "data": {"title": "Hi"}}
            }
        },
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert "use_block_template:tplA" in body and "Greeting" in body


def test_home_builder_saves_hidden_on_per_device():
    """SE-3c-mid: чекбоксы 📱/▭/🖥 сохраняют список устройств скрытия секции."""
    tenant = TenantFactory(schema_name="public", slug="hbho", name="HBHO", site_config={})
    data = {
        "order_products": "1",
        "enabled_products": "on",
        "hide_mobile_products": "on",
        "hide_desktop_products": "on",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["hidden_on"] == ["mobile", "desktop"]


def test_home_builder_get_renders_hidden_on_checkboxes():
    """SE-3c-mid: GET отрисовывает чекбоксы скрытия по устройствам, отражая состояние."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbhog",
        name="HBHOG",
        site_config={"sections": [{"key": "products", "enabled": True, "hidden_on": ["mobile"]}]},
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'name="hide_mobile_products"' in body
    assert 'name="hide_tablet_products"' in body
    assert 'name="hide_desktop_products"' in body


def test_home_builder_save_page_template_snapshots_layout():
    """SE-4b: «сохранить страницу как шаблон» делает снимок текущей компоновки из POST."""
    tenant = TenantFactory(schema_name="public", slug="hbspt", name="HBSPT", site_config={})
    data = {
        "action": "save_page_template",
        "page_tpl_label": "Mein Layout",
        "order_hero": "1",
        "enabled_hero": "on",
        "order_products": "2",  # без enabled_ → выключена в снимке
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    pts = siteconfig.normalize(tenant.site_config)["page_templates"]
    assert len(pts) == 1
    pt = next(iter(pts.values()))
    assert pt["label"] == "Mein Layout"
    by_key = {s["key"]: s for s in pt["sections"]}
    assert by_key["hero"]["enabled"] is True
    assert by_key["products"]["enabled"] is False


def test_home_builder_use_page_template_replaces_sections():
    """SE-4b: применение шаблона ЗАМЕНЯЕТ весь набор секций снимком."""
    snapshot = [
        {"key": "hero", "enabled": False},
        {"key": "events", "enabled": True},
    ]
    tenant = TenantFactory(
        schema_name="public",
        slug="hbupt",
        name="HBUPT",
        site_config={"page_templates": {"ptA": {"label": "L", "sections": snapshot}}},
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "use_page_template:ptA"}, tenant)
    )
    cfg = siteconfig.normalize(tenant.site_config)
    by_key = {s["key"]: s for s in cfg["sections"]}
    assert by_key["hero"]["enabled"] is False
    assert by_key["events"]["enabled"] is True


def test_home_builder_delete_page_template():
    """SE-4b: удаление шаблона страницы из библиотеки."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbdpt",
        name="HBDPT",
        site_config={"page_templates": {"ptA": {"label": "L", "sections": []}}},
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "delete_page_template:ptA"}, tenant)
    )
    assert siteconfig.normalize(tenant.site_config)["page_templates"] == {}


def test_home_builder_get_renders_page_template_library():
    """SE-4b: GET рендерит библиотеку шаблонов страниц (применить/удалить) + кнопку сохранения."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbptl",
        name="HBPTL",
        site_config={"page_templates": {"ptA": {"label": "Klassisch", "sections": []}}},
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert "use_page_template:ptA" in body and "Klassisch" in body
    assert 'value="save_page_template"' in body


def test_home_builder_save_creates_history_snapshot():
    """SE-5b: явное «Сохранить» кладёт предыдущую опубликованную версию в историю."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbhist",
        name="HBHIST",
        site_config={"hero_title": "Erste Version"},
    )
    data = {"order_hero": "1", "enabled_hero": "on"}
    views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    cfg = siteconfig.normalize(tenant.site_config)
    assert len(cfg["history"]) == 1
    assert cfg["history"][0]["config"]["hero_title"] == "Erste Version"


def test_home_builder_two_saves_keep_newest_first():
    """SE-5b: вторая публикация добавляет запись; новейшая — первая. Меняем заголовок
    секции (title_events — поле, которое реально пишет этот POST)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbhist2",
        name="HBHIST2",
        site_config={"section_titles": {"events": "V1"}},
    )
    views.home_builder_view(
        _request(
            "post", "/dashboard/site/home/", {"enabled_events": "on", "title_events": "V2"}, tenant
        )
    )
    views.home_builder_view(
        _request(
            "post", "/dashboard/site/home/", {"enabled_events": "on", "title_events": "V3"}, tenant
        )
    )
    hist = siteconfig.normalize(tenant.site_config)["history"]
    # перед 2-й публикацией было V2, перед 1-й — V1
    assert hist[0]["config"]["section_titles"]["events"] == "V2"
    assert hist[1]["config"]["section_titles"]["events"] == "V1"


def test_home_builder_restore_version_swaps_config():
    """SE-5b: restore_version меняет конфиг на снимок, текущий уходит в историю (undoable)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbrest",
        name="HBREST",
        site_config={
            "hero_title": "Current",
            "history": [{"ts": "2026-01-01T00:00", "config": {"hero_title": "Alt"}}],
        },
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "restore_version:0"}, tenant)
    )
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"] == "Alt"  # откатились
    assert cfg["history"][0]["config"]["hero_title"] == "Current"  # текущий — undoable


def test_home_builder_restore_invalid_index_noop():
    """SE-5b: невалидный индекс отката — без изменений."""
    tenant = TenantFactory(
        schema_name="public", slug="hbrest2", name="HBREST2", site_config={"hero_title": "Keep"}
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"action": "restore_version:9"}, tenant)
    )
    assert siteconfig.normalize(tenant.site_config)["hero_title"] == "Keep"


def test_home_builder_get_renders_history():
    """SE-5b: GET рендерит список версий с кнопкой Restore."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbhistg",
        name="HBHISTG",
        site_config={"history": [{"ts": "2026-06-28T15:30", "config": {"hero_title": "X"}}]},
    )
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert "restore_version:0" in body and "2026-06-28" in body


def test_home_builder_get_restores_db_draft():
    """SE-5b-2: при наличии `_draft` в БД редактор открывается на черновике + сидит сессию."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbdraft",
        name="HBDRAFT",
        site_config={
            "section_titles": {"events": "Published"},
            "_draft": {"section_titles": {"events": "DraftTitle"}},
            "_draft_ts": "2026-06-28T15:00",
        },
    )
    req = _request("get", "/dashboard/site/home/", tenant=tenant)
    body = views.home_builder_view(req).content.decode()
    assert "DraftTitle" in body  # форма открылась на черновике, не на опубликованном
    # сессия засеяна черновиком → превью ?preview=1 покажет то же
    assert (
        req.session.get("site_preview_draft", {}).get("section_titles", {}).get("events")
        == "DraftTitle"
    )


def test_home_builder_save_clears_db_draft():
    """SE-5b-2: явное «Сохранить» публикует и очищает `_draft` (normalize дропает служебное)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="hbdraftc",
        name="HBDRAFTC",
        site_config={"_draft": {"hero_title": "WIP"}, "_draft_ts": "t"},
    )
    views.home_builder_view(
        _request("post", "/dashboard/site/home/", {"order_hero": "1", "enabled_hero": "on"}, tenant)
    )
    tenant.refresh_from_db()
    assert "_draft" not in tenant.site_config and "_draft_ts" not in tenant.site_config


def test_home_builder_se6_fullscreen_overlay_shell():
    """SE-6: билдер — полноэкранный overlay (#bld-root fixed) + шторка-инспектор с тогглом."""
    tenant = TenantFactory(schema_name="public", slug="hbse6", name="HBSE6")
    body = views.home_builder_view(
        _request("get", "/dashboard/site/home/", tenant=tenant)
    ).content.decode()
    assert 'id="bld-root"' in body  # полноэкранный корень
    assert 'id="bld-drawer-toggle"' in body  # тоггл шторки в топ-баре
    assert 'id="bld-drawer-close"' in body  # ✕ закрыть шторку
    assert 'id="bld-editor-pane"' in body  # шторка-инспектор (id сохранён → JS работает)
    assert 'id="home-prev-frame"' in body  # канвас-iframe сохранён
    assert 'id="bld-tab-editor"' not in body  # старый сплит-таб Редактор/Превью убран
