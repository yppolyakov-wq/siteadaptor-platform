"""STU-1 — реестр «тип страницы витрины → её настройки» (`apps.core.studio_pages`).

Замки этого файла держат три инварианта, на которых стоит вся Студия v2:

1. **Каждый url_name реестра существует в `config.urls_tenant`.** Опечатка или
   переименованный роут иначе молча выключили бы целый тип страницы: панель
   показывала бы общий уровень вместо настроек этой страницы, и никто бы не
   заметил (класс дефектов «узел молча выпал», уроки ST-8/hero_tiles).
2. **Каждый код настройки, на который ссылается тип, есть в `SETTINGS`.**
3. **`resolve_page` действительно узнаёт страницу** — включая три ловушки:
   товар живёт на трёх роутах (uuid/слаг/категория+слаг), группа акций — тот же
   роут, что обзор, но с `?gruppe=`, а мусорный путь обязан давать `other`,
   а не 500 (редактор должен открываться где угодно).
"""

import pytest
from django.urls import get_resolver

from apps.core import studio_pages as sp


def _tenant_url_names() -> set[str]:
    resolver = get_resolver("config.urls_tenant")
    return {k for k in resolver.reverse_dict if isinstance(k, str)}


def test_every_url_name_in_registry_resolves():
    known = _tenant_url_names()
    missing = sorted(
        f"{pt.code}:{name}" for pt in sp.PAGE_TYPES for name in pt.url_names if name not in known
    )
    assert not missing, f"url_name из реестра нет в config.urls_tenant: {missing}"


def test_every_setting_code_referenced_exists():
    missing = sorted(
        f"{pt.code}:{code}"
        for pt in sp.PAGE_TYPES
        for code in pt.settings
        if code not in sp.SETTINGS
    )
    assert not missing, f"тип ссылается на несуществующую настройку: {missing}"


def test_setting_codes_match_dict_keys():
    for code, setting in sp.SETTINGS.items():
        assert setting.code == code


def test_object_scope_is_declared_in_pairs():
    """`object_kind` без `object_field` (и наоборот) — настройка, у которой пилюля
    охвата нарисовалась бы, а писать «только здесь» было бы некуда."""
    for setting in sp.SETTINGS.values():
        assert bool(setting.object_kind) == bool(setting.object_field), setting.code


def test_page_types_have_unique_codes():
    codes = [pt.code for pt in sp.PAGE_TYPES]
    assert len(codes) == len(set(codes))
    assert sp.OTHER.code not in codes


def test_block_hosts_are_valid():
    from apps.tenants.siteconfig import is_page_block_host

    for pt in sp.PAGE_TYPES:
        if pt.block_host:
            assert is_page_block_host(pt.block_host), f"{pt.code}: {pt.block_host}"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/", "home"),
        ("/sortiment/", "catalog"),
        ("/sortiment/brot/", "category"),
        ("/aktionen/", "promos"),
        ("/warenkorb/", "cart"),
        ("/warenkorb/bestellen/", "checkout"),
        ("/termin/", "services"),
        ("/unterkunft/", "stays"),
        ("/veranstaltung/", "events"),
        ("/ueber-uns/", "text"),
        ("/impressum/", "legal"),
        ("/blog/", "blog"),
    ],
)
def test_resolve_page_recognises_types(path, code):
    assert sp.resolve_page(path).code == code


def test_unknown_path_falls_back_to_other():
    """Редактор обязан открыться и на пути, которого нет в urls_tenant."""
    ctx = sp.resolve_page("/kein-solcher-pfad/xyz/")
    assert ctx.code == "other"
    assert ctx.settings == []


def test_product_is_recognised_on_all_three_routes():
    uuid = "11111111-1111-1111-1111-111111111111"
    by_pk = sp.resolve_page(f"/sortiment/{uuid}/")
    assert by_pk.code == "product" and by_pk.object_ref == uuid

    by_slug = sp.resolve_page("/sortiment/p/roggenbrot/")
    assert by_slug.code == "product" and by_slug.object_ref == "roggenbrot"

    seo = sp.resolve_page("/sortiment/brot/roggenbrot/")
    assert seo.code == "product" and seo.object_ref == "roggenbrot"


def test_category_gets_its_own_block_host():
    ctx = sp.resolve_page("/sortiment/brot/")
    assert ctx.object_ref == "brot"
    assert ctx.block_host == "catalog:brot"


def test_promo_group_is_the_same_route_with_gruppe():
    plain = sp.resolve_page("/aktionen/")
    assert plain.code == "promos" and plain.object_ref == ""

    group = sp.resolve_page("/aktionen/?gruppe=raeumung")
    assert group.code == "promo_group"
    assert group.object_ref == "raeumung"

    # пустой параметр — это по-прежнему обзор, а не безымянная группа
    assert sp.resolve_page("/aktionen/?gruppe=").code == "promos"


def test_query_can_be_passed_separately():
    ctx = sp.resolve_page("/aktionen/", {"gruppe": "sale"})
    assert ctx.code == "promo_group" and ctx.object_ref == "sale"


def test_settings_for_returns_registry_order():
    codes = [s.code for s in sp.settings_for("category")]
    assert codes == list(sp.page_type("category").settings)


def test_object_scope_only_where_the_object_exists():
    """Охват «только здесь» предлагается лишь там, где страница знает свой объект."""
    for pt in sp.PAGE_TYPES:
        for setting in sp.settings_for(pt.code):
            if setting.has_object_scope and setting.object_kind == pt.object_kind:
                assert pt.object_args, f"{pt.code}: объект не из чего достать"


# ── связь реестра с реальными формой и конфигом ──────────────────────────────
#
# Оба замка ловят «тихий» класс дефектов: переименовали ключ в normalize или поле
# в форме Studio — реестр молча начинает читать/писать не туда, а панель выглядит
# рабочей (контрол есть, значение всегда дефолтное).


def test_every_site_key_resolves_in_normalized_config():
    from apps.tenants import siteconfig

    raw = {
        "catalog_page_style": "regale",
        "site_defaults": {
            "category_page_style": "magazin",
            "card_style": "regal",
            "promo_card": "coupon",
            "promo_group_style": "prospekt",
        },
        "product_detail": {"layout": "tabs"},
        "promo_page_style": "kompakt",
        "promo_layout": "slider",
        "promo_grouping": "time",
        "service_index_layout": {"preset": "cols3"},
    }
    cfg = siteconfig.normalize(raw)
    missing = []
    for setting in sp.SETTINGS.values():
        node, ok = cfg, True
        for part in setting.site_key:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                ok = False
                break
        if not ok:
            missing.append((setting.code, setting.site_key))
    assert not missing, f"site_key реестра не резолвится в normalize: {missing}"


def test_every_form_field_exists_in_the_studio_template():
    """Поля-шаблоны (`order_*`) проверяем по префиксу — их имена динамические."""
    import re
    from pathlib import Path

    from django.conf import settings as dj_settings

    tpl = Path(dj_settings.BASE_DIR) / "templates" / "tenant" / "site_home.html"
    names = set(re.findall(r'name="([a-z_0-9]+)"', tpl.read_text(encoding="utf-8")))

    missing = []
    for setting in sp.SETTINGS.values():
        field = setting.form_field
        if field.endswith("*"):
            prefix = field[:-1]
            # динамические поля рисуются в шаблоне через {{ }} — ищем префикс в теле
            if prefix not in tpl.read_text(encoding="utf-8"):
                missing.append((setting.code, field))
        elif field not in names:
            missing.append((setting.code, field))
    assert not missing, f"поля реестра нет в форме Studio: {missing}"


# ── STU-2: витрина сообщает редактору, ЧТО открыто ───────────────────────────


@pytest.mark.django_db
def test_storefront_body_carries_page_type(settings):
    """Без этой подсказки панель «Эта страница» показывала бы настройки наугад:
    по пути тип не читается (`/sortiment/<uuid>/` — товар, `/sortiment/<slug>/` —
    категория), а второй разбор пути на каждом рендере витрины — лишняя плата,
    поэтому берём УЖЕ разобранный `resolver_match`."""
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory
    from django.urls import resolve

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory()
    request = RequestFactory().get("/aktionen/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    request.resolver_match = resolve("/aktionen/", urlconf="config.urls_tenant")

    html = public_views.promotion_list(request).content.decode()
    assert 'data-stu-page="promos"' in html


def test_resolve_match_tolerates_no_match():
    """Страница вне urlconf (обработчик ошибки, статика) — честный `other`."""
    ctx = sp.resolve_match(None, {}, path="/whatever/")
    assert ctx.code == "other"


# ── STU-2: уровень «Эта страница» в Studio ───────────────────────────────────


def _builder_html(tenant):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views

    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.home_builder_view(req)
    assert resp.status_code == 200
    return resp.content.decode()


@pytest.fixture
def builder_html(settings):
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    return _builder_html(TenantFactory())


@pytest.mark.django_db
def test_rail_offers_two_levels(builder_html):
    """Запрос владельца: «отдельная настройка слева "Общий макет", и далее уже
    детально об этой [странице]». Раньше слева были ОБЛАСТИ, не совпадавшие с
    содержимым панели."""
    assert 'data-st-level="design"' in builder_html
    assert 'data-st-level="page"' in builder_html
    assert 'data-bld-area="page"' in builder_html
    assert 'data-area="page"' in builder_html


@pytest.mark.django_db
def test_page_settings_are_tagged_by_type(builder_html):
    """Настройки страницы акций и шаблона категории раньше жили в области «Тема» —
    то есть были видны на ЛЮБОЙ странице, кроме своей."""
    for marker in (
        'data-stu-page="category"',
        'data-stu-page="promo_group"',
        'data-stu-page="promos promo_group"',
    ):
        assert marker in builder_html, marker


@pytest.mark.django_db
def test_no_control_is_lost_or_duplicated(builder_html):
    """Инвариант W0/W6: перенос контролов между областями не имеет права ни потерять
    поле (Save запишет дефолт вместо значения), ни удвоить его (в POST уедет
    последнее, а владелец правил первое)."""
    import re

    for field in (
        "catalog_preset",
        "catalog_page_style",
        "catalog_sort",
        "catalog_show_filters",
        "catalog_subcats_first",
        "promo_page_style",
        "promo_layout",
        "promo_grouping",
        "sd_category_page_style",
        "sd_promo_group_style",
        "sd_card_style",
        "sd_promo_card",
        "pd_layout",
        "cart_show_upsell",
        "pb_present",
    ):
        n = len(re.findall(rf'name="{field}"', builder_html))
        assert n == 1, f"поле {field}: найдено {n} раз (ожидалось ровно одно)"


@pytest.mark.django_db
def test_type_labels_reach_the_client(builder_html):
    """Подпись уровня = тип страницы на канве; коды приходят с <body> кадра, а
    человеческие названия — картой из реестра."""
    assert "studio_page_labels" not in builder_html, "переменная не подставлена"
    for code in ("home", "category", "product", "promos", "other"):
        assert f'"{code}"' in builder_html


# ── STU-4: клик по содержимому страницы открывает её настройки ────────────────


@pytest.mark.django_db
def test_builder_binds_click_on_page_content(builder_html):
    """Раньше клик работал только там, где есть секция главной с одноимённой строкой
    формы: на листинге акций, странице группы, детали товара кликать было не по чему."""
    assert "[data-listing-root], [data-stu-area]" in builder_html
    # клик не имеет права перехватывать ссылки и поля витрины
    assert 'e.target.closest("a,button,input,textarea,select,[contenteditable]")' in builder_html


@pytest.mark.django_db
def test_listing_and_detail_carry_click_anchors(settings):
    """Якоря — уже существующий каркас листингов (KAT-5) и корень детали: витрине
    добавлена ровно одна новая метка, а не по метке на каждый тип страницы."""
    from importlib import import_module

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    from apps.catalog.models import Category, Product
    from apps.promotions.public_views import product_detail, product_list
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory()
    Category.objects.create(name={"de": "Brot"}, slug="brot", is_active=True)
    product = Product.objects.create(name={"de": "Roggen"}, slug="roggen", base_price="3.20")

    def _get(view, *args, **kw):
        req = RequestFactory().get("/sortiment/")
        req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
        req.tenant = tenant
        return view(req, *args, **kw).content.decode()

    assert "data-listing-root" in _get(product_list)
    assert 'data-stu-area="detail"' in _get(product_detail, pk=product.pk)


# ── попутный дефект класса W6, найденный разведкой Студии ─────────────────────


@pytest.mark.django_db
def test_builder_save_keeps_section_cover_and_gallery(settings):
    """Загрузил обложку раздела → нажал Save в билдере → обложка исчезла.

    `normalize` хранит у архетипа восемь ключей (label/blurb/hidden + intro,
    hero_image, button_label, button_url, gallery), а сохранение билдера
    пересобирало словарь ровно из трёх: остальные писал ДРУГОЙ экран (загрузчик
    обложек), и любое сохранение конструктора их стирало. Тот же класс, что
    чинил W6 для ui_mode/board/seo.
    """
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory()
    tenant.site_config = {
        "archetypes": {
            "catalog": {
                "label": "Sortiment",
                "blurb": "",
                "hidden": False,
                "intro": "Frisch jeden Tag",
                "hero_image": "/media/cover.webp",
                "button_label": "Ansehen",
                "button_url": "/sortiment/",
                "gallery": [],
            }
        }
    }
    tenant.save(update_fields=["site_config"])

    req = RequestFactory().post("/dashboard/site/home/", {"arch_visible_catalog": "on"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    views.home_builder_view(req)

    tenant.refresh_from_db()
    saved = (tenant.site_config.get("archetypes") or {}).get("catalog") or {}
    assert saved.get("hero_image") == "/media/cover.webp", "обложка раздела стёрта"
    assert saved.get("intro") == "Frisch jeden Tag"
    assert saved.get("button_label") == "Ansehen"
    assert saved.get("button_url") == "/sortiment/"


# ── STU-5: страница «Pages» умерла, её настройки живут в Студии ───────────────


@pytest.mark.django_db
def test_dead_pages_screen_redirects_to_studio(settings):
    """Прецедент W10-6/W11-5: экран умер, но старые ссылки и закладки не ломаются."""
    from types import SimpleNamespace

    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    req = RequestFactory().get("/dashboard/site/pages/")
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = TenantFactory()
    resp = views.pages_view(req)
    assert resp.status_code == 302
    assert resp.url == "/dashboard/site/home/"


@pytest.mark.django_db
def test_settings_moved_from_pages_screen_still_save(settings):
    """Экран «Pages» был ВТОРЫМ писателем раскладок, но держал три настройки, которых
    в Студии не было. Схлопнуть его, не перенеся их, значило бы потерять настройки —
    поэтому замок проверяет именно сохранение из формы Студии."""
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=["orders"], business_type="restaurant")
    req = RequestFactory().post(
        "/dashboard/site/home/",
        {
            "cl_present": "1",
            "menu_labels": "on",
            # чекбокс СНЯТ: ключ presence-minimal и хранится только когда цены скрыты
            "related_preset": "cols4",
        },
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    views.home_builder_view(req)

    tenant.refresh_from_db()
    cfg = tenant.site_config
    assert cfg.get("menu_labels") is True
    assert cfg.get("menu_show_prices") is False, "снятый чекбокс обязан скрыть цены"
    assert cfg.get("detail_related_layout", {}).get("preset") == "cols4"


@pytest.mark.django_db
def test_moved_settings_are_scoped_to_their_page_type(builder_html):
    assert 'data-stu-page="catalog category"' in builder_html
    assert 'data-stu-page="product"' in builder_html


# ── STU-6: покрытие ВСЕХ типов страниц ───────────────────────────────────────


def test_every_page_type_resolves_from_its_own_route():
    """Сильнейший из дешёвых замков: каждый тип реестра обязан узнаваться по АДРЕСУ,
    собранному из его же url_name.

    Класс дефектов «узел молча выпал» (меню демо, hero-плитки): переименовали роут или
    добавили тип без рабочего адреса — панель тихо показывает «Seite» вместо настроек,
    и никто не замечает. Здесь адрес строится реверсом, а не руками, поэтому замок
    ломается ровно тогда, когда ломается связь «тип ↔ роут».
    """
    from uuid import uuid4

    from django.urls import NoReverseMatch, reverse

    # Возможные наборы аргументов роутов витрины; берём ПЕРВЫЙ, которым адрес
    # собирается, и проверяем, что реестр узнаёт по нему тот же тип.
    arg_sets = (
        {},
        {"pk": uuid4()},
        {"slug": "probe"},
        {"pslug": "probe"},
        {"cslug": "kategorie", "pslug": "probe"},
    )

    def _paths(name):
        for kwargs in arg_sets:
            try:
                yield reverse(name, kwargs=kwargs, urlconf="config.urls_tenant")
            except NoReverseMatch:
                continue

    unresolved = []
    for pt in sp.PAGE_TYPES:
        if pt.code == "promo_group":
            continue  # тот же роут, что обзор; отличается ?gruppe= (свой замок выше)
        ok = any(
            sp.resolve_page(path).code == pt.code for name in pt.url_names for path in _paths(name)
        )
        if not ok:
            unresolved.append(pt.code)
    assert not unresolved, f"тип не узнаётся по собственному адресу: {unresolved}"


def test_registry_covers_the_pages_the_owner_named():
    """Владелец перечислил типы явно: «главная, категория, категория акции, вложенная
    категория, страница товара, страница акции, текстовые страницы, корзина,
    оформление заказа и т.д.». Замок держит именно этот состав."""
    codes = {pt.code for pt in sp.PAGE_TYPES}
    for required in (
        "home",
        "catalog",
        "category",
        "product",
        "promos",
        "promo_group",
        "promo",
        "text",
        "cart",
        "checkout",
        "legal",
    ):
        assert required in codes, required


@pytest.mark.django_db
def test_home_block_rows_are_scoped_by_page_type(builder_html):
    """STU-6 (нашёл стенд): «главная ли это» решает ТИП страницы.

    Прежняя эвристика считала главной любую страницу без группы и без хоста
    C-блоков — на `/galerie/` и `/kombi/` панель показывала блоки ГЛАВНОЙ, и
    владелец правил бы не ту страницу. Тип известен всегда, кроме 404 — там
    осталось прежнее поведение.
    """
    assert 'var isHome = curStuPage ? curStuPage === "home"' in builder_html


# ── STU-7: канва держит страницу с параметром ─────────────────────────────────


@pytest.mark.django_db
def test_page_query_whitelist_reaches_the_client(builder_html):
    """Список «параметров, задающих страницу» клиент получает ИЗ РЕЕСТРА, а не хранит
    свой: иначе серверный санитайзер и канва разойдутся, и страница группы акций снова
    начнёт сбрасываться на обзор при первой же смене настройки."""
    assert "studio_page_query_keys_json" not in builder_html, "переменная не подставлена"
    for key in sp.PAGE_QUERY_KEYS:
        assert f'"{key}"' in builder_html


def test_canvas_keeps_query_in_preview_path():
    """Скан-замок: previewPath собирается из пути И отфильтрованных параметров. Голая
    location.pathname возвращает дефект STU-7 (перерисовка уводит на обзор), а тесты
    рендера его не видят — он живёт только в браузере."""
    from pathlib import Path

    from django.conf import settings as dj_settings

    tpl = (Path(dj_settings.BASE_DIR) / "templates" / "tenant" / "site_home.html").read_text()
    assert "previewPath = fPath + stuPageQuery(" in tpl
    assert "var STU_PAGE_QUERY_KEYS = {{ studio_page_query_keys_json|safe }};" in tpl


def test_unknown_page_is_not_treated_as_home():
    """STU-7: пустой тип = «неизвестная страница», а НЕ «главная». Замер обходом на два
    уровня по четырём демо: тип сообщают 258 страниц из 258, единственное исключение —
    кастомный 404 (SF-3 сделал его standalone намеренно). Прежний `!group` показывал на нём блоки ГЛАВНОЙ: владелец
    правил бы не ту страницу — тот же класс, что закрыт на /galerie/ и /kombi/."""
    from pathlib import Path

    from django.conf import settings as dj_settings

    tpl = (Path(dj_settings.BASE_DIR) / "templates" / "tenant" / "site_home.html").read_text()
    assert (
        'var isHome = curStuPage ? curStuPage === "home" : (group === "home" && !curPbHost);' in tpl
    )


def test_custom_404_stays_standalone():
    """Пара к замку выше: страница-страховка НЕ должна тянуть хром витрины ради
    `data-stu-page` — она обязана рендериться, даже если хром сломан. Если 404 когда-то
    начнёт наследовать базовый шаблон, фолбэк выше можно упростить осознанно."""
    from pathlib import Path

    from django.conf import settings as dj_settings

    page = (Path(dj_settings.BASE_DIR) / "templates" / "404.html").read_text()
    assert "{% extends" not in page
    assert "data-stu-page" not in page


def test_page_ribbon_matches_chip_by_bare_path():
    """STU-7 (нашло ревью ветки): чипы ленты страниц — голые пути, а previewPath теперь
    может нести `?gruppe=`. Без среза параметра на странице группы не подсвечивался ни
    один чип: лента показывала «мы нигде», хотя канва внутри «Aktionen»."""
    from pathlib import Path

    from django.conf import settings as dj_settings

    tpl = (Path(dj_settings.BASE_DIR) / "templates" / "tenant" / "site_home.html").read_text()
    assert '.value || "/").split("?")[0];' in tpl
