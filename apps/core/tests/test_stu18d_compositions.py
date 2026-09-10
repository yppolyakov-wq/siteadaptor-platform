"""STU-18d: композиция страницы на девяти листингах (решение владельца Р-2).

План — `docs/stu18-panel-ia-plan-2026-09-10.md` §11. Замки написаны ДО правок
витрины и краснеют на текущем коде: реестр композиций знает только каталог и
акции, ключа хранения нет вовсе, а каркас листинга не рисует ни вкладок, ни
полок, ни боковой колонки.

Главный инвариант волны — тот же, что у STU-9/STU-17, и проверяется в ОБЕ
стороны: не предлагать неисполнимого и не исполнять необъявленного.
"""

import pytest
from django.template.loader import get_template

from apps.core import compositions
from apps.core import studio_pages as sp
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


# ── реестр ───────────────────────────────────────────────────────────────────


def test_every_listing_surface_has_a_page_type_and_a_setting():
    """Поверхность без типа страницы недостижима из панели — обещание в пустоту."""
    types = {pt.code: pt for pt in sp.PAGE_TYPES}
    for surface in compositions.LISTING_SURFACES:
        assert surface in types, f"нет типа страницы «{surface}»"
        code = f"{surface}_page_style"
        assert code in sp.SETTINGS, f"нет настройки {code}"
        assert code in types[surface].settings, f"тип «{surface}» не объявляет {code}"
        assert sp.SETTINGS[code].axis == sp.AXIS_COMPOSITION
        # хранение — ОДИН ключ на девять поверхностей (план §11.3)
        assert sp.SETTINGS[code].site_key == ("page_styles", surface)


def test_surface_declares_composition_only_if_its_page_uses_the_shell():
    """Хром композиции рисует каркас `listing.html` — страница обязана быть НА НЁМ.

    Замок, которого не хватало: реестр и каркас можно согласовать между собой и
    всё равно ничего не показать владельцу, если сама страница наследуется от
    `_base.html`. Ровно это и вскрылось: из девяти листингов волны на каркасе
    четыре, а пять (наборы, лукбук, мерклист, блог, отзывы) — нет.

    Карта «тип → шаблон» выводится (url_name → вьюха → её `render`), как в
    STU-17: рукописная протухла бы на первой же новой странице.
    """
    import inspect
    import re

    from django.urls import get_resolver

    views = {}

    def walk(patterns):
        for pat in patterns:
            if hasattr(pat, "url_patterns"):
                walk(pat.url_patterns)
            elif getattr(pat, "name", None):
                views[pat.name] = pat.callback

    walk(get_resolver("config.urls_tenant").url_patterns)
    render_re = re.compile(r'(?:^|[^\w])\w*render\w*\(\s*request,\s*"([^"]+\.html)"')
    types = {pt.code: pt for pt in sp.PAGE_TYPES}

    for surface in compositions.LISTING_SURFACES:
        templates = set()
        for url_name in types[surface].url_names:
            view = views.get(url_name)
            if view is None:
                continue
            try:
                templates |= set(render_re.findall(inspect.getsource(view)))
            except (OSError, TypeError):
                continue
        assert templates, f"{surface}: не нашли шаблон страницы"
        on_shell = any(
            'extends "storefront/listing.html"'
            in open(get_template(name).origin.name, encoding="utf-8").read()
            for name in templates
        )
        assert on_shell, (
            f"{surface}: композиция объявлена, но страница не на каркасе listing.html — "
            "хром рисовать некому"
        )
    # d3 свёл последние пять страниц на каркас — отложенных не осталось; словарь
    # причин пуст, но существует: он и есть место для будущих исключений.
    assert not (set(compositions.PENDING_SURFACES) & compositions.LISTING_SURFACES)
    assert len(compositions.LISTING_SURFACES) == 9


def test_in_grid_compositions_are_not_offered_on_listings():
    """«Витрина/Журнал/Мозаика» меняют САМ ЭЛЕМЕНТ — это оси сетки и карточки.

    Объявить их композицией листинга значило бы пообещать то, чего каркас не
    рисует: цикл карточек у каждого листинга свой (план §11.1).
    """
    for surface in compositions.LISTING_SURFACES:
        offered = {code for code, _l, _h in compositions.styles_for(surface)}
        assert not (offered & {"schaufenster", "magazin", "mosaik", "preisliste", "sets"}), (
            f"{surface}: предложена композиция, которую каркас не рисует"
        )


def test_listing_navigator_needs_sub_entities():
    """Боковая колонка без под-сущностей на листинге была бы пустой.

    На каталоге тот же код осмыслен и без подкатегорий (там богатые фасеты) —
    поэтому требование ПОВЕРХНОСТНОЕ, а не общее.
    """
    off = {code for code, _l, _h in compositions.available_for("services", has_children=False)}
    assert "navigator" not in off and "kompakt" not in off
    on = {code for code, _l, _h in compositions.available_for("services", has_children=True)}
    assert {"navigator", "kompakt", "tabs", "regale"} <= on
    # каталог не тронут
    cat = {code for code, _l, _h in compositions.available_for("category", has_children=False)}
    assert "navigator" in cat


def test_resolve_is_fail_safe():
    """Код, которому нечего показать, проваливается в обычную сетку, а не в пустую
    страницу: владелец мог удалить последнюю подборку уже после выбора «Полок»."""
    assert compositions.resolve("services", "regale", has_children=False) == ""
    assert compositions.resolve("services", "mosaik") == ""  # чужая поверхность
    assert compositions.resolve("services", "erfunden") == ""
    assert compositions.resolve("services", "tabs") == "tabs"


# ── хранение ─────────────────────────────────────────────────────────────────


def test_page_styles_key_is_presence_minimal():
    assert siteconfig.normalize_page_styles({"services": "tabs"}) == {"services": "tabs"}
    assert siteconfig.normalize_page_styles({"services": "mosaik"}) == {}  # чужой код
    assert siteconfig.normalize_page_styles({"catalog": "tabs"}) == {}  # не листинг
    assert siteconfig.normalize_page_styles("мусор") == {}
    cfg = siteconfig.normalize({"page_styles": {"services": ""}})
    assert "page_styles" not in cfg, "пустой словарь не имеет права материализоваться"
    cfg = siteconfig.normalize({"page_styles": {"services": "regale"}})
    assert cfg["page_styles"] == {"services": "regale"}


# ── каркас ───────────────────────────────────────────────────────────────────


def _shell() -> str:
    return open(get_template("storefront/listing.html").origin.name, encoding="utf-8").read()


def test_shell_emits_one_composition_attribute():
    """Третий атрибут для той же композиции = каша, которую разбирала LAY."""
    src = _shell()
    assert 'data-sf-page="{{ page_composition }}"' in src


def test_shell_renders_chrome_of_every_offered_listing_composition():
    """Обещание ⇒ исполнение: каждая предложенная композиция листинга рисуется.

    Замок fail-closed по построению: новый код в `applies_to` листинга без ветки
    в каркасе краснит его сразу.
    """
    src = _shell()
    rendered = {
        "": True,  # обычная сетка — ветка не нужна
        "kopfbild": "composition/_hero.html" in src,
        "tabs": 'page_composition == "tabs"' in src,
        "regale": 'page_composition == "regale"' in src,
        "kompakt": 'page_composition == "kompakt"' in src,
        "navigator": 'page_composition == "navigator"' in src,
    }
    for surface in compositions.LISTING_SURFACES:
        for code, _l, _h in compositions.styles_for(surface):
            assert rendered.get(code), f"{surface}: каркас не рисует композицию «{code}»"


def test_navigator_wraps_the_facets_of_the_page():
    """Колонка «Navigator» обязана обнимать ИМЕННО блок фасетов страницы.

    Фасеты приходят блоком шаблона (у каждого листинга свои), поэтому обёртка —
    вокруг `{% block listing_facets %}`, а не вокруг всего подряд.
    """
    src = _shell()
    open_i = src.index('{% if page_composition == "navigator" %}<aside')
    facets_i = src.index("{% block listing_facets %}")
    close_i = src.index('{% if page_composition == "navigator" %}</aside>')
    assert open_i < facets_i < close_i


def test_catalog_does_not_use_the_new_chrome():
    """Каталог остаётся на своей разметке (паритет-замки d-pre) — иначе хром
    отрисовался бы дважды."""
    src = open(get_template("storefront/products.html").origin.name, encoding="utf-8").read()
    assert "page_composition" not in src


# ── витрина: пилот на листинге услуг (d1) ────────────────────────────────────


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _services_page(page_styles, *, with_collection=True, hero=""):
    """Рендер /termin/ у тенанта с одной услугой и (опционально) подборкой."""
    import uuid
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.booking.models import Service
    from apps.collections.models import Collection
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug=f"stu18d{uuid.uuid4().hex[:6]}")
    cfg = dict(tenant.site_config or {})
    cfg["page_styles"] = page_styles
    if hero:
        cfg["hero_image"] = hero
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])

    svc = Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3000)
    if with_collection:
        coll = Collection.objects.create(name={"de": "Damen"}, slug="damen", is_active=True)
        svc.collections.add(coll)

    req = RequestFactory().get("/termin/")
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=False)
    req.tenant = tenant
    resp = public_views.termin_index(req)
    assert resp.status_code == 200
    return resp.content.decode()


def test_services_listing_renders_tabs():
    body = _services_page({"services": "tabs"})
    assert 'data-sf-page="tabs"' in body
    assert "data-category-tabs" in body
    assert "?kollektion=damen" in body


def test_services_listing_renders_shelves():
    body = _services_page({"services": "regale"})
    assert 'data-shelf="damen"' in body
    assert "Haarschnitt" in body


def test_services_listing_renders_side_column():
    body = _services_page({"services": "navigator"})
    assert 'data-sf-page="navigator"' in body
    assert "data-cat-side" in body


def test_composition_falls_back_when_the_data_is_gone():
    """Владелец выбрал «Полки», потом удалил последнюю подборку — страница обязана
    вернуться к обычной сетке, а не показать пустоту."""
    body = _services_page({"services": "regale"}, with_collection=False)
    assert "data-sf-page" not in body
    assert "Haarschnitt" in body  # выдача на месте


def test_cover_without_a_photo_falls_back_to_the_grid():
    """«С обложкой» на листинге показывает фото САЙТА: без него — обычная сетка."""
    assert "data-comp-hero" not in _services_page({"services": "kopfbild"})


def test_cover_renders_the_site_photo():
    body = _services_page({"services": "kopfbild"}, hero="/media/x.jpg")
    assert "data-comp-hero" in body and "/media/x.jpg" in body


# ── витрина: номера, события, поездки (d2) ───────────────────────────────────


def _render_listing(view, path, page_styles, seed, config=None):
    """Общий стенд листинга: тенант с выбранной композицией + данные из `seed`."""
    import uuid
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug=f"stu18d{uuid.uuid4().hex[:6]}")
    cfg = dict(tenant.site_config or {})
    cfg.update(config or {})
    cfg["page_styles"] = page_styles
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    seed()

    req = RequestFactory().get(path)
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=False)
    req.tenant = tenant
    resp = view(req)
    assert resp.status_code == 200
    return resp.content.decode()


def test_stays_listing_renders_tabs():
    from apps.collections.models import Collection
    from apps.stays import public_views
    from apps.stays.models import StayUnit

    def _seed():
        # два номера: с одним листинг сразу редиректит на его страницу
        unit = StayUnit.objects.create(name="Doppelzimmer", price_cents=9000)
        StayUnit.objects.create(name="Einzelzimmer", price_cents=6000)
        coll = Collection.objects.create(name={"de": "Seeblick"}, slug="seeblick", is_active=True)
        unit.collections.add(coll)

    body = _render_listing(public_views.unterkunft_index, "/unterkunft/", {"stays": "tabs"}, _seed)
    assert 'data-sf-page="tabs"' in body and "?kollektion=seeblick" in body


def test_events_listing_renders_shelves_by_theme():
    """Под-сущность событий — ТЕМА (`Event.category`), та же, что даёт фасет ?cat=."""
    from django.utils import timezone

    from apps.events import public_views
    from apps.events.models import Event

    def _seed():
        Event.objects.create(
            title="Waldbaden",
            category="yoga",
            status=Event.STATUS_PUBLISHED,
            starts_at=timezone.now() + __import__("datetime").timedelta(days=7),
        )

    body = _render_listing(
        public_views.veranstaltung_index, "/veranstaltung/", {"events": "regale"}, _seed
    )
    assert 'data-shelf="yoga"' in body and "Waldbaden" in body


def test_tours_offer_only_the_cover():
    """У поездок страница САМА группирует по странам (MT-D2) — вкладки и полки
    дублировали бы встроенную группировку, поэтому не предлагаются."""
    offered = {code for code, _l, _h in compositions.styles_for("tours")}
    assert offered == {"", "kopfbild"}
    # чтение ШИРЕ предложения (инвариант LAY: живые сайты не меняем), но вьюха
    # поездок под-сущностей не отдаёт — значит «Полки» и там проваливаются в сетку
    assert compositions.resolve("tours", "regale", has_children=False) == ""


# ── витрина: пять сведённых на каркас страниц (d3) ───────────────────────────


def test_combos_listing_renders_tabs_by_category():
    """Под-сущность наборов — НАПРАВЛЕНИЕ (`Combo.category`), ключ фасета ?kategorie=."""
    from apps.catalog.models import Category, Combo
    from apps.orders import public_views

    def _seed():
        cat = Category.objects.create(name={"de": "Menüs"}, slug="menues", is_active=True)
        Combo.objects.create(name="Menü A", price="15.00", is_active=True, category=cat)

    body = _render_listing(public_views.combo_list_public, "/kombi/", {"combos": "tabs"}, _seed)
    assert 'data-sf-page="tabs"' in body and "?kategorie=menues" in body


def test_cover_only_pages_get_the_cover():
    """У блога под-сущностей нет — но обложка работает, если у сайта есть фото."""
    from apps.events import public_views
    from apps.events.models import BlogPost

    def _seed():
        BlogPost.objects.create(title="Post", slug="post", is_published=True)

    body = _render_listing(
        public_views.blog_index,
        "/blog/",
        {"blog": "kopfbild"},
        _seed,
        config={"hero_image": "/media/hero.jpg"},
    )
    assert "data-comp-hero" in body and "/media/hero.jpg" in body


def test_panel_hides_the_cover_without_a_site_photo():
    """Плитка «С обложкой» не должна обещать то, чего страница не отрисует."""
    from apps.core import views as core_views

    off = core_views._composition_gate({})
    assert "kopfbild" in off["blog"]
    on = core_views._composition_gate({"hero_image": "/media/hero.jpg"})
    assert "kopfbild" not in on["blog"]
    # у категории «С обложкой» берёт СВОЁ фото — гейт по фото сайта её не трогает
    assert "kopfbild" not in core_views._composition_gate({})["category"]


def test_composition_takes_the_entry_chips_over():
    """Стенд поймал дубль: над вкладками «Damen · Herren» висел точно такой же ряд
    чипов подборок. Композиция, выводящая под-сущности, забирает их себе."""
    body = _services_page({"services": "tabs"})
    assert "data-category-tabs" in body
    # чип подборки исчез из ряда фасетов (он теперь вкладка), «Alle» остался
    assert body.count("?kollektion=damen") == 1


def test_without_composition_the_chips_stay():
    """Обратная сторона: без композиции ряд чипов прежний (второй тенант — в своём
    тесте: у стенда схема одна на прогон)."""
    plain = _services_page({})
    assert "?kollektion=damen" in plain and "data-category-tabs" not in plain
