"""AB6 Onboarding-Wizard: движок шагов (state v2 + реестр SETUP_STEPS), новая карта
слайдов AB6.2 (company/stil/menu/offer/category/home/payment/texts/done; business —
escape-hatch), гейты по модулям, авто-✓ по контенту, рельса, легаси-ремап, AB5."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import modules
from apps.core import views as core_views
from apps.tenants import onboarding, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


# --- состояние + легаси-ремап на новую карту --------------------------------------


def test_get_state_defaults_and_garbage():
    # Свежий тенант: позиция на первом ключе реестра (business), прогресс пуст.
    assert onboarding.get_state(TenantFactory.build()) == {
        "v": 2,
        "step": "business",
        "done": [],
        "skipped": [],
        "completed": False,
    }
    # Мусорный легаси-int: step 99 → первый; skipped [2]=template→stil; [7]=done (финал,
    # отброшен); completed truthy → True (done-список пуст, флаг завершения ведёт рельсу).
    t = TenantFactory.build(
        site_config={"onboarding": {"step": 99, "skipped": ["x", 2, 7], "completed": "y"}}
    )
    s = onboarding.get_state(t)
    assert s["step"] == "business" and s["skipped"] == ["stil"]
    assert s["completed"] is True and s["done"] == []


def test_legacy_v1_int_remaps_to_new_keys():
    """Легаси v1 (int-шаги прода) → новые ключи через _REMAP; modules→company."""
    t = TenantFactory.build(
        site_config={"onboarding": {"step": 4, "skipped": [2], "completed": False}}
    )
    s = onboarding.get_state(t)
    assert s["step"] == "company"  # int4=basics→company
    assert s["skipped"] == ["stil"]  # int2=template→stil
    # passed olds (1..3)=business,template,modules → business,stil,company минус пропущенный stil
    assert s["done"] == ["business", "company"]


def test_legacy_v2_ab61_slugs_remap_to_new_keys():
    """v2-state старой карты AB6.1 (basics/template/hero...) → новые ключи."""
    t = TenantFactory.build(
        site_config={
            "onboarding": {
                "v": 2,
                "step": "hero",
                "done": ["business", "basics"],
                "skipped": ["template"],
                "completed": False,
            }
        }
    )
    s = onboarding.get_state(t)
    assert s["step"] == "home"  # hero→home
    assert s["done"] == ["business", "company"]  # basics→company
    assert s["skipped"] == ["stil"]  # template→stil


def test_normalize_preserves_onboarding():
    config = siteconfig.normalize({"onboarding": {"v": 2, "step": "offer", "completed": False}})
    assert config["onboarding"]["step"] == "offer"


def test_state_v2_roundtrip_via_advance_and_skip():
    """advance/skip пишут state v2 (слаги, done-список); skip → ⏭, повторный проход
    снимает пропуск. Порядок по ВИДИМЫМ шагам тенанта."""
    tenant = TenantFactory(business_type="bakery")
    onboarding.goto(tenant, "company")  # старт с первого видимого
    onboarding.advance(tenant)  # company выполнен → stil
    onboarding.advance(tenant, skip=True)  # stil пропущен → menu
    raw = tenant.site_config["onboarding"]
    assert raw["v"] == 2 and raw["step"] == "menu"
    assert raw["done"] == ["company"] and raw["skipped"] == ["stil"]
    # Вернулись по рельсе и прошли пропущенный шаг → done, из skipped снят.
    onboarding.goto(tenant, "stil")
    onboarding.advance(tenant)
    state = onboarding.get_state(tenant)
    assert state["done"] == ["company", "stil"] and state["skipped"] == []


def test_goto_jumps_to_any_registry_step_incl_gated():
    tenant = TenantFactory(business_type="bakery")
    assert onboarding.goto(tenant, "home")["step"] == "home"
    assert onboarding.goto(tenant, "nope")["step"] == "home"  # невалидный ключ игнорируется
    # escape-hatch: скрытый business достижим прыжком.
    assert onboarding.goto(tenant, "business")["step"] == "business"
    assert onboarding.get_state(tenant)["done"] == []  # goto — позиция, не прогресс


# --- гейты видимости шагов --------------------------------------------------------


def test_business_hidden_from_rail_but_reachable():
    """AB6.2: тип выбран при регистрации → business вне рельсы, но достижим ?step=."""
    tenant = TenantFactory(schema_name="public", slug="esc", name="Esc", business_type="bakery")
    assert "business" not in [s["key"] for s in onboarding.steps_with_status(tenant)]
    html = core_views.setup_view(_req("get", {"step": "business"}, tenant)).content.decode()
    assert 'name="business_type"' in html  # escape-hatch рендерит слайд выбора отрасли


def test_payment_step_gated_by_checkout_module():
    """payment виден только при активном чекаут-модуле (orders/booking/…)."""
    # other: нет чекаута → payment скрыт; bakery: orders → payment виден.
    other = TenantFactory(
        business_type="other", disabled_modules=modules.default_disabled_for("other")
    )
    assert "payment" not in onboarding.visible_keys(other)
    bakery = TenantFactory(
        business_type="bakery", disabled_modules=modules.default_disabled_for("bakery")
    )
    assert "payment" in onboarding.visible_keys(bakery)


def test_visible_total_excludes_gated_steps():
    """«Step N of M» и прогресс считают только видимые шаги (business всегда скрыт)."""
    other = TenantFactory(
        business_type="other", disabled_modules=modules.default_disabled_for("other")
    )
    vis = onboarding.visible_keys(other)
    assert "business" not in vis and "payment" not in vis
    assert vis[0] == "start" and vis[-1] == "done"  # AB6.9: start — первый видимый
    assert onboarding.progress(other) == (0, len(vis))


# --- авто-✓ по реальному контенту (SetupStep.check) -------------------------------


def test_check_auto_ticks_company_and_offer_from_content():
    tenant = TenantFactory(
        schema_name="public", slug="chk", name="Chk", business_type="bakery", address="Hauptstr. 1"
    )
    from apps.tenants import demo

    demo.load_demo(tenant)  # создаёт товары → offer выполнен без явного прохода
    status = {s["key"]: s["status"] for s in onboarding.steps_with_status(tenant)}
    assert status["company"] == "done"  # адрес заполнен
    assert status["offer"] == "done"  # есть что продавать


# --- прохождение мастера ----------------------------------------------------------


def test_full_walkthrough_completes_over_visible_steps():
    """Линейный проход по всем видимым шагам → completed; прогресс = M/M."""
    tenant = TenantFactory(
        schema_name="public",
        slug="walk",
        name="Walk",
        business_type="other",
        disabled_modules=modules.default_disabled_for("other"),
    )
    vis = onboarding.visible_keys(tenant)
    for _ in range(len(vis) + 2):
        if onboarding.get_state(tenant)["completed"]:
            break
        core_views.setup_view(_req("post", {}, tenant))
    state = onboarding.get_state(tenant)
    assert state["completed"] and state["step"] == "done"
    assert onboarding.progress(tenant) == (len(vis), len(vis))


def test_start_slide_demo_start_loads_rich_examples_and_advances():
    """AB6.9: «Mit Beispielen starten» на слайде start — БОГАТОЕ демо (фото+баннер+
    шаблон архетипа) + шаг к company."""
    from apps.tenants import demo

    tenant = TenantFactory(
        schema_name="public", slug="demostart", name="DS", business_type="bakery"
    )
    onboarding.goto(tenant, "start")
    assert not demo.has_demo(tenant)
    resp = core_views.setup_view(_req("post", {"action": "demo_start"}, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert demo.has_demo(tenant)
    assert tenant.site_config.get("hero_image")  # баннер добавлен (rich)
    assert tenant.site_config.get("gallery")  # галерея добавлена
    assert onboarding.get_state(tenant)["step"] == "company"  # к первому контент-шагу


def test_start_is_first_visible_step():
    tenant = TenantFactory(business_type="bakery")
    assert onboarding.visible_keys(tenant)[0] == "start"


def test_clear_demo_soft_deletes_ordered_products():
    """AB6.9-фикс: демо-товар, на который уже ссылается заказ (protected FK), при
    clear_demo не роняет ProtectedError — soft-delete (история заказа цела)."""
    from decimal import Decimal

    from apps.catalog.models import Product
    from apps.orders.models import Order, OrderItem
    from apps.promotions.models import Customer
    from apps.tenants import demo

    tenant = TenantFactory(schema_name="public", slug="ord", name="Ord", business_type="bakery")
    demo.load_demo(tenant)
    p = Product.objects.filter(metadata__demo=True).first()
    customer = Customer.objects.create(name="Test", email="t@t.de")
    order = Order.objects.create(customer=customer, reference_code="O-DEMO01")
    OrderItem.objects.create(order=order, product=p, qty=1, unit_price=Decimal("1.00"))
    # не должно падать ProtectedError; товар исчезает с витрины (soft), заказ жив
    assert demo.clear_demo(tenant) is True
    assert not Product.objects.filter(pk=p.pk).exists()  # снят с витрины
    assert OrderItem.objects.filter(order=order).exists()  # история заказа цела


def test_rich_demo_adds_photos_and_is_reversible():
    """AB6.9: обогащённое демо — фото на товаре + hero + галерея (МЕРЖ, не замена);
    clear_demo откатывает добавленные cfg-ключи, НЕ трогая переопределённое владельцем."""
    from apps.catalog.models import Product
    from apps.tenants import demo

    tenant = TenantFactory(schema_name="public", slug="rich", name="Rich", business_type="bakery")
    assert demo.load_demo(tenant) is True
    tenant.refresh_from_db()
    # фото на товаре
    p = Product.objects.filter(metadata__demo=True).first()
    assert p and p.images and p.images[0].get("url")
    cfg = tenant.site_config
    assert cfg.get("hero_image") and cfg.get("hero_title") and cfg.get("gallery")
    assert cfg["demo"].get("_cfg", {}).get("hero_image")  # добавленное записано для отката
    # владелец переопределил hero_title ПОСЛЕ демо → clear его НЕ трогает
    cfg2 = dict(cfg)
    cfg2["hero_title"] = "Mein echter Titel"
    tenant.site_config = cfg2
    tenant.save(update_fields=["site_config"])
    demo.clear_demo(tenant)
    tenant.refresh_from_db()
    assert not demo.has_demo(tenant)
    assert tenant.site_config.get("hero_title") == "Mein echter Titel"  # правка владельца цела
    assert not tenant.site_config.get("hero_image")  # неизменённое демо-поле откачено


def test_stil_slide_shows_visual_template_gallery():
    """AB6.2b: stil = галерея готовых образов с мини-мокапом раскладки (акцент + стек
    секций) + бейдж «рекомендовано»; выбор radio → применяется на Weiter."""
    tenant = TenantFactory(business_type="bakery")
    onboarding.goto(tenant, "stil")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="template"' in html
    assert "Recommended" in html  # бейдж рекомендованного типу шаблона
    # мини-мокап: подписи секций шаблона (напр. hero-полоса) в карточке
    assert "aria-hidden" in html


def test_texts_slide_saves_about_and_impressum():
    """AB6.2g: слайд texts — «Über uns» (about_*) + Impressum (LegalDoc дефолт-локали)."""
    from apps.core.models import LegalDoc

    tenant = TenantFactory(schema_name="public", slug="tx", name="Tx", business_type="bakery")
    onboarding.goto(tenant, "texts")
    core_views.setup_view(
        _req(
            "post",
            {"about_title": "Über uns", "about_text": "Wir backen.", "impressum": "Tx GmbH, Weg 1"},
            tenant,
        )
    )
    tenant.refresh_from_db()
    assert tenant.site_config["about_text"] == "Wir backen."
    assert LegalDoc.objects.filter(kind="impressum").first().text == "Tx GmbH, Weg 1"


def test_menu_slide_picks_header_style():
    """AB6.2e: слайд menu — выбор вида шапки (classic/centered/minimal) → config nav.style."""
    tenant = TenantFactory(schema_name="public", slug="mn", name="Mn", business_type="bakery")
    onboarding.goto(tenant, "menu")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="nav_style"' in html and "Menüpunkte bearbeiten" in html
    core_views.setup_view(_req("post", {"nav_style": "centered"}, tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["nav"]["style"] == "centered"


def test_company_slide_saves_name_city_and_shows_logo_field():
    """AB6.2f: слайд company — название/город правятся в мастере (первыми) + поле лого."""
    tenant = TenantFactory(schema_name="public", slug="co", name="Alt", business_type="bakery")
    onboarding.goto(tenant, "company")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="name"' in html and 'name="city"' in html and 'name="logo"' in html
    core_views.setup_view(
        _req("post", {"name": "Bäckerei Neu", "city": "Hilden", "address": "Weg 1"}, tenant)
    )
    tenant.refresh_from_db()
    assert tenant.name == "Bäckerei Neu" and tenant.city == "Hilden"
    # пустое имя не затирает (обязательное поле)
    onboarding.goto(tenant, "company")
    core_views.setup_view(_req("post", {"name": "", "city": "Köln"}, tenant))
    tenant.refresh_from_db()
    assert tenant.name == "Bäckerei Neu" and tenant.city == "Köln"


def test_home_slide_saves_hero_texts():
    tenant = TenantFactory(business_type="bakery")
    onboarding.goto(tenant, "home")
    core_views.setup_view(_req("post", {"hero_title": "Moin", "hero_text": "Frisch"}, tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Moin"
    assert tenant.site_config["hero_text"] == "Frisch"


def test_live_save_persists_without_advancing():
    """action=live сохраняет поля шага (204), шаг не сменился."""
    tenant = TenantFactory(business_type="bakery")
    onboarding.goto(tenant, "home")
    resp = core_views.setup_view(
        _req("post", {"action": "live", "hero_title": "Live!", "hero_text": "Sofort"}, tenant)
    )
    assert resp.status_code == 204
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Live!"
    assert onboarding.get_state(tenant)["step"] == "home"


def test_offer_slide_shows_archetype_presets_and_cta():
    tenant = TenantFactory(
        business_type="bakery", disabled_modules=modules.default_disabled_for("bakery")
    )
    onboarding.goto(tenant, "offer")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "preset=feierabend" in html and "Add your first product" in html


def test_offer_cta_is_archetype_aware():
    """W3: у friseur (booking primary) CTA — услуга, не «товар»."""
    tenant = TenantFactory(
        business_type="friseur", disabled_modules=modules.default_disabled_for("friseur")
    )
    onboarding.goto(tenant, "offer")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Add your first service" in html and "Add your first product" not in html


def test_offer_slide_loads_and_clears_demo_content():
    from apps.tenants import demo

    tenant = TenantFactory(
        schema_name="public", slug="wiz-demo", name="WizDemo", business_type="bakery"
    )
    onboarding.goto(tenant, "offer")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Beispiel-Inhalte laden" in html
    response = core_views.setup_view(_req("post", {"action": "load_demo"}, tenant))
    assert response.status_code == 302
    assert demo.has_demo(tenant) is True
    assert onboarding.get_state(tenant)["step"] == "offer"  # остаёмся на шаге
    core_views.setup_view(_req("post", {"action": "clear_demo"}, tenant))
    assert demo.has_demo(tenant) is False


def test_offer_slide_creates_first_product():
    """AB6.2c: мини-форма слайда offer создаёт первый товар (bakery → catalog) и
    показывает его в списке «✏️»; остаёмся на слайде."""
    from decimal import Decimal

    from apps.catalog.models import Product

    tenant = TenantFactory(
        schema_name="public",
        slug="wiz-off",
        name="WizOff",
        business_type="bakery",
        disabled_modules=modules.default_disabled_for("bakery"),
    )
    onboarding.goto(tenant, "offer")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="offer_name"' in html and 'value="create_offer"' in html
    resp = core_views.setup_view(
        _req(
            "post",
            {"action": "create_offer", "offer_name": "Roggenbrot", "offer_price": "3,50"},
            tenant,
        )
    )
    assert resp.status_code == 302  # остаёмся на слайде, можно добавить ещё
    product = Product.objects.get(name__de="Roggenbrot")
    assert product.base_price == Decimal("3.50")
    assert onboarding.get_state(tenant)["step"] == "offer"
    # позиция появляется в списке с ссылкой на родную форму правки
    html2 = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Roggenbrot" in html2 and str(product.pk) in html2


def test_offer_slide_creates_event_with_date():
    """AB6.2c: у events-архетипа мини-форма показывает поле даты и создаёт
    опубликованное событие с распарсенным starts_at + ценой в центах."""
    from apps.events.models import Event

    tenant = TenantFactory(
        schema_name="public",
        slug="wiz-ev",
        name="WizEv",
        business_type="events",
        disabled_modules=modules.default_disabled_for("events"),
    )
    onboarding.goto(tenant, "offer")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="offer_starts_at"' in html  # поле даты только у события
    core_views.setup_view(
        _req(
            "post",
            {
                "action": "create_offer",
                "offer_name": "Sommerkonzert",
                "offer_price": "12",
                "offer_starts_at": "2026-08-20T19:30",
            },
            tenant,
        )
    )
    ev = Event.objects.get(title="Sommerkonzert")
    assert ev.status == Event.STATUS_PUBLISHED and ev.price_cents == 1200
    assert ev.starts_at.year == 2026 and ev.starts_at.month == 8


def test_category_slide_picks_catalog_layout():
    """AB6.2d: слайд category — выбор раскладки каталога → catalog_layout.preset."""
    tenant = TenantFactory(schema_name="public", slug="cat", name="Cat", business_type="bakery")
    onboarding.goto(tenant, "category")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="catalog_preset"' in html and "Kategorien verwalten" in html
    core_views.setup_view(_req("post", {"catalog_preset": "cols4"}, tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["catalog_layout"]["preset"] == "cols4"


def test_payment_slide_reuses_shared_form_and_saves():
    """AB6.2-payment: слайд payment переиспользует форму W4-3 (партиал _payment_fields)
    и общий save-диспетчер — секция по сентинелу сохраняется тем же путём, что экран."""
    tenant = TenantFactory(
        schema_name="public",
        slug="pay",
        name="Pay",
        business_type="bakery",
        disabled_modules=[],  # orders активен → секции доставки/Vorkasse рендерятся
    )
    onboarding.goto(tenant, "payment")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert 'name="sec_delivery"' in html and 'name="vorkasse_enabled"' in html
    core_views.setup_view(
        _req(
            "post",
            {"sec_delivery": "1", "delivery_enabled": "on", "delivery_fee_eur": "4,50"},
            tenant,
        )
    )
    tenant.refresh_from_db()
    assert tenant.delivery_enabled is True and tenant.delivery_fee_cents == 450


# --- рельса прогресса + прыжок ----------------------------------------------------


def test_get_step_param_jumps_and_persists():
    tenant = TenantFactory(schema_name="public", slug="jump", name="Jump", business_type="bakery")
    html = core_views.setup_view(_req("get", {"step": "home"}, tenant)).content.decode()
    assert "Banner" in html or "Startseite" in html
    assert onboarding.get_state(tenant)["step"] == "home"


def test_rail_shows_visible_steps_with_status_marks():
    tenant = TenantFactory(schema_name="public", slug="rail", name="Rail", business_type="bakery")
    onboarding.save_state(
        tenant,
        {"v": 2, "step": "menu", "done": ["company"], "skipped": ["stil"], "completed": False},
    )
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    for key in onboarding.visible_keys(tenant):
        assert f"?step={key}" in html
    assert "business" not in [s["key"] for s in onboarding.steps_with_status(tenant)]
    assert "⏭" in html and "✓" in html
    assert 'aria-current="step"' in html


def test_handlers_registry_matches_step_keys():
    """Замок: реестр handler'ов покрывает ровно STEP_KEYS (нет слайдов-сирот)."""
    from apps.core import setup_steps

    assert set(setup_steps.HANDLERS) == set(onboarding.STEP_KEYS)


def test_every_visible_slide_renders():
    """Замок AB6.2a: каждый видимый слайд (вкл. стабы menu/category/payment/texts)
    рендерится 200 — все {% url %} в стабах реверсятся."""
    tenant = TenantFactory(
        schema_name="public", slug="render", name="Render", business_type="bakery"
    )
    for key in onboarding.visible_keys(tenant):
        resp = core_views.setup_view(_req("get", {"step": key}, tenant))
        assert resp.status_code == 200, key


# --- дашборд (AB4-плашка + AB5-редирект) ------------------------------------------


def test_dashboard_shows_progress_until_completed():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(
        tenant,
        {"v": 2, "step": "menu", "done": ["company"], "skipped": ["stil"], "completed": False},
    )
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt" in html
    onboarding.save_state(tenant, {"v": 2, "step": "done", "completed": True})
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Setup-Fortschritt" not in html


def test_done_slide_shows_step_summary_with_fillin_links():
    """AB6.2: финиш-слайд — сводка шагов ✓/⏭/○; пропущенный кликабелен (?step=<key>)."""
    tenant = TenantFactory(schema_name="public", slug="fin", name="Fin", business_type="bakery")
    onboarding.save_state(
        tenant,
        {"v": 2, "step": "done", "done": ["company"], "skipped": ["stil"], "completed": True},
    )
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "?step=stil" in html  # пропущенный шаг → ссылка дозаполнения
    assert "Firma" in html  # выполненный шаг company в сводке (метка «Firma & Logo»)
    assert "Geschafft" in html  # заголовок финиша


def test_dashboard_redirects_fresh_owner_to_wizard():
    """AB5: нетронутый мастер (свежая регистрация) → дашборд уводит в Wizard."""
    tenant = TenantFactory()
    response = core_views.dashboard(_req(tenant=tenant))
    assert response.status_code == 302
    assert response.url == "/dashboard/setup/"


def test_dashboard_renders_once_wizard_touched():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"v": 2, "step": "stil", "done": ["company"], "completed": False})
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200
    onboarding.save_state(tenant, {"v": 2, "step": "done", "completed": True})
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200


# --- AB7-B2: блочная главная (плитки задач + встроенный канбан) --------------------


def test_dashboard_shows_task_tiles_gated_by_module():
    """AB7-B2: плитки задач — offer/Kategorien/Startseite/Zahlung/Recht по модулям."""
    from apps.core import dashboard as dash

    tenant = TenantFactory(
        schema_name="public",
        slug="tiles",
        name="Tiles",
        business_type="bakery",
        disabled_modules=modules.default_disabled_for("bakery"),
    )
    onboarding.save_state(
        tenant, {"v": 2, "step": "company", "done": ["company"], "completed": False}
    )
    urls = {t["url_name"] for t in dash.dashboard_tiles(tenant)}
    assert {"catalog:category-list", "site-home", "payment-settings", "legal-docs"} <= urls
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Categories" in html and "Design homepage" in html and "Payment &amp; shipping" in html
    # В Простом режиме у friseur (ARCHETYPE_SIMPLE_HIDDEN) catalog скрыт → нет плитки
    # Kategorien (тот же гейт simple_hidden_modules, что у сайдбара).
    simple_friseur = TenantFactory.build(
        business_type="friseur",
        disabled_modules=modules.default_disabled_for("friseur"),
        site_config={"ui_mode": "simple"},
    )
    hidden_urls = {t["url_name"] for t in dash.dashboard_tiles(simple_friseur)}
    assert "catalog:category-list" not in hidden_urls


def test_dashboard_tile_badge_links_to_incomplete_step():
    """AB7-B2: невыполненный шаг → бейдж «Not set up» с ?step=<key> (дозаполнение)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="badge",
        name="Badge",
        business_type="bakery",
        disabled_modules=modules.default_disabled_for("bakery"),
    )
    onboarding.save_state(
        tenant, {"v": 2, "step": "company", "done": ["company"], "completed": False}
    )
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Not set up" in html and "?step=offer" in html


def test_dashboard_embeds_kanban_board_when_channel_active():
    """AB7-B2: канбан входящих встроен в главную (тот же партиал/DnD) при активном канале."""
    from decimal import Decimal

    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    tenant = TenantFactory(
        schema_name="public",
        slug="brd",
        name="Brd",
        business_type="restaurant",
        disabled_modules=[],
    )
    onboarding.save_state(tenant, {"v": 2, "step": "done", "completed": True})
    product = ProductFactory(base_price=Decimal("8.00"))
    order = create_order(items=[(product, 1)], name="Max", email="max@test.de")
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "data-drop-stage" in html and order.reference_code in html
    assert "/dashboard/board/" in html  # ссылка «Full view» на большую доску


def test_fresh_setup_snaps_to_first_visible_step():
    """Свежий тенант (позиция business, скрыт) → GET мастера показывает первый видимый
    шаг (company), не escape-hatch."""
    tenant = TenantFactory(schema_name="public", slug="snap", name="Snap", business_type="bakery")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert onboarding.get_state(tenant)["step"] == "start"  # AB6.9: первый видимый = start
    assert 'name="business_type"' not in html  # не слайд выбора отрасли
    assert "Mit Beispielen starten" in html  # приглашение добавить демо


def test_site_view_save_keeps_wizard_state():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(tenant, {"v": 2, "step": "stil", "completed": False})
    response = core_views.site_view(_req("post", {"hero_title": "Hallo"}, tenant))
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Hallo"
    assert onboarding.get_state(tenant)["step"] == "stil"


# --- business escape-hatch: пресеты модулей (гибрид) ------------------------------


def test_business_slide_keeps_custom_modules_on_same_type():
    tenant = TenantFactory(business_type="bakery", disabled_modules=[])
    onboarding.goto(tenant, "business")
    core_views.setup_view(_req("post", {"business_type": "bakery"}, tenant))
    tenant.refresh_from_db()
    assert tenant.disabled_modules == []


def test_business_slide_reapplies_preset_on_type_change():
    tenant = TenantFactory(business_type="cafe", disabled_modules=["crm"])
    onboarding.goto(tenant, "business")
    core_views.setup_view(_req("post", {"business_type": "retail"}, tenant))
    tenant.refresh_from_db()
    assert sorted(tenant.disabled_modules) == sorted(modules.default_disabled_for("retail"))


def test_back_button_steps_back_over_visible():
    tenant = TenantFactory(business_type="bakery")
    onboarding.save_state(
        tenant,
        {"v": 2, "step": "menu", "done": ["company"], "skipped": ["stil"], "completed": False},
    )
    core_views.setup_view(_req("post", {"action": "back"}, tenant))
    state = onboarding.get_state(tenant)
    assert (
        state["step"] == "stil" and state["skipped"] == []
    )  # назад к предыдущему видимому, ⏭ снят
    # «Zurück» с финального экрана не раз-завершает мастер
    onboarding.save_state(tenant, {"v": 2, "step": "done", "completed": True})
    core_views.setup_view(_req("post", {"action": "back"}, tenant))
    assert onboarding.get_state(tenant)["completed"] is True


# --- живое превью + карточки архетипа --------------------------------------------


def test_setup_shows_live_preview_iframe_on_content_steps():
    tenant = TenantFactory(schema_name="public", slug="prev", name="Prev", business_type="cafe")
    onboarding.goto(tenant, "stil")
    html = core_views.setup_view(_req("get", tenant=tenant)).content.decode()
    assert "Live preview" in html
    assert "data-setup-preview" in html and 'src="/"' in html
    assert 'set("action", "live")' in html


def test_setup_no_preview_on_business_escape_hatch():
    tenant = TenantFactory(schema_name="public", slug="prev1", name="Prev1", business_type="cafe")
    html = core_views.setup_view(_req("get", {"step": "business"}, tenant)).content.decode()
    assert "Live preview" not in html  # на выборе отрасли превью не нужно


# --- AB6.9: focused first-run лейаут + «Später fertigstellen» ----------------------


def test_setup_uses_focused_layout_without_cabinet_sidebar():
    """AB6.9: мастер — полноэкранный focused-экран (extends _base_setup), БЕЗ сайдбара
    кабинета (nav-группы/«Funktion hinzufügen» не рендерятся)."""
    tenant = TenantFactory(schema_name="public", slug="focus", name="Focus", business_type="bakery")
    html = core_views.setup_view(_req(tenant=tenant)).content.decode()
    assert "Später fertigstellen" in html  # мини-шапка focused-лейаута
    assert 'id="sidebar"' not in html  # сайдбар кабинета отсутствует
    assert "Funktion hinzufügen" not in html


def test_exit_marks_touched_and_redirects_to_dashboard():
    """AB6.9 «Später»: выход помечает мастер тронутым (⏭ текущего) и ведёт в кабинет;
    AB5-редирект больше не возвращает в мастер."""
    tenant = TenantFactory(schema_name="public", slug="later", name="Later", business_type="bakery")
    resp = core_views.setup_view(_req("post", {"action": "exit"}, tenant))
    assert resp.status_code == 302 and resp.url == "/dashboard/"
    state = onboarding.get_state(tenant)
    assert state["skipped"]  # текущий шаг помечен ⏭ → мастер тронут
    assert not state["completed"]
    # дашборд теперь рендерится (не зациклен на мастер).
    assert core_views.dashboard(_req(tenant=tenant)).status_code == 200


def test_business_type_cards_cover_all_types_with_icon_and_blurb():
    from apps.tenants.models import Tenant

    cards = onboarding.business_type_cards()
    assert {c["value"] for c in cards} == {v for v, _ in Tenant.BUSINESS_TYPES}
    assert all(c["icon"] and c["label"] and c["blurb"] for c in cards)
