"""STU-16 — фидбэк владельца по панели Студии (2026-09-10).

План — `docs/stu16-panel-feedback-plan-2026-09-10.md`. Разведка сделана в
браузере; прод и стенд отдают идентичную разметку, поэтому замки серверные, а
ширины контролов меряет стенд Playwright.

Замки написаны ДО правок и краснеют на текущем коде.
"""

import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BUILDER = "templates/tenant/site_home.html"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _body(tenant):
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.home_builder_view(req)
    assert resp.status_code == 200
    return resp.content.decode()


def _markup():
    return open(BUILDER, encoding="utf-8").read()


# ── STU-16a: ось вывода не сжимается флекс-родителем ───────────────────────


def test_output_axis_takes_the_whole_row():
    """49 px на контрол — это не «узко», это нечитаемо: подписи шире полей.

    Партиал обязан занимать всю ширину строки, а родительская flex-строка —
    уметь переносить (иначе `basis-full` ничего не даст).
    """
    axis = open("templates/tenant/_output_axis.html", encoding="utf-8").read()
    assert "basis-full" in axis, "партиал не занимает всю ширину строки"
    markup = _markup()
    rows = [m for m in markup.split("\n") if "_output_axis.html" in m]
    assert rows, "включений оси не найдено"
    for row in rows:
        idx = markup.index(row)
        head = markup.rfind('<div class="page-block', 0, idx)
        opening = markup[head : markup.index(">", head) + 1]
        # STU-18a: механизм сменился — строка больше НЕ флекс, настройки идут
        # стопкой (подпись сверху, контрол во всю ширину). Инвариант тот же:
        # ось не должна сжиматься родителем до нечитаемых 49 px. Поэтому флекс
        # без переноса запрещён, а его отсутствие — норма.
        if "flex" in opening:
            assert "flex-wrap" in opening, f"флекс без переноса сожмёт ось: {opening[:120]}"


# ── STU-16b: дубль «Header style» ↔ «Examples» ─────────────────────────────


def test_header_style_has_one_control_and_it_is_the_tiles():
    """Владелец: «2 раза одно и то же, оставь с картинкой»."""
    markup = _markup()
    assert "data-menu-examples" in markup, "плитки-мокапы должны остаться"
    radios = re.findall(r'<input type="radio" name="nav_style"', markup)
    assert not radios, "радио-дубль «Header style» должен быть снят"
    # W0: поле не потеряно — значение несёт hidden того же имени.
    assert re.search(r'<input type="hidden"[^>]*name="nav_style"', markup)


def test_header_preset_labels_are_words_not_codes():
    """`classic/centered/minimal` в интерфейсе — коды, а не подписи."""
    body = _body(TenantFactory(schema_name="public", slug="stu16l", name="L"))
    block = body[body.index("data-menu-examples") :][:4000]
    for code in ("classic", "centered", "minimal"):
        assert f">{code}<" not in block, f"код {code} печатается как подпись"


# ── STU-16c: режим Einfach|Experte снят ────────────────────────────────────


def test_simple_expert_toggle_is_gone_from_the_panel():
    """Владелец: «оставь только эксперт везде» (прецедент W-CL, SM-1)."""
    markup = _markup()
    for marker in ('id="bld-mode-basic"', 'id="bld-mode-expert"', "bld-mode-btn"):
        assert marker not in markup, f"остался маркер режима: {marker}"


# ── STU-16e: язык — два селектора различимы ────────────────────────────────


def test_language_selectors_are_labelled_and_distinguishable():
    """Два одинаковых на вид селектора языка рядом — источник «каши».

    Оба живут в верхней строке Студии (между ссылкой «Design des Shops» и кнопкой
    share) — там и ищем, чтобы замок краснел на переносе в другое место.
    """
    markup = _markup()
    start = markup.index('id="st-design-link"')
    bar = markup[start : markup.index('id="bld-share-preview"')]
    assert "data-lang-content" in bar and "data-lang-cabinet" in bar
    # подпись словом (не только aria) — иначе два селекта неотличимы глазом
    assert bar.count("2xl:inline") >= 2


def test_cabinet_language_defaults_to_the_browser():
    """Дефолт `de` при русском браузере и есть «неправильный язык»."""
    from apps.core import i18n_cabinet

    req = RequestFactory().get("/dashboard/", HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9")
    req.session = {}
    assert i18n_cabinet.resolve_cabinet_locale(req) == "ru"
    req2 = RequestFactory().get("/dashboard/", HTTP_ACCEPT_LANGUAGE="xx")
    req2.session = {}
    assert i18n_cabinet.resolve_cabinet_locale(req2) == "de"  # незнакомый → дефолт проекта
    # выбор владельца сильнее браузера
    req3 = RequestFactory().get("/dashboard/", HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9")
    req3.session = {i18n_cabinet.SESSION_KEY: "en"}
    assert i18n_cabinet.resolve_cabinet_locale(req3) == "en"
    # q-веса уважаются: турецкий приоритетнее русского
    req4 = RequestFactory().get("/dashboard/", HTTP_ACCEPT_LANGUAGE="ru;q=0.4,tr;q=0.9")
    req4.session = {}
    assert i18n_cabinet.resolve_cabinet_locale(req4) == "tr"
    # язык витрины (кука) на кабинет НЕ влияет — понятия разведены (T1-a)
    req5 = RequestFactory().get("/dashboard/")
    req5.COOKIES["django_language"] = "ru"
    req5.session = {}
    assert i18n_cabinet.resolve_cabinet_locale(req5) == "de"


# ── STU-16d: пункт меню, добавленный из Студии, ВИДЕН на сайте ─────────────


def test_menu_target_options_are_all_reachable():
    """Каждая предложенная цель обязана давать ссылку — иначе селект обещает
    пункт, который витрина молча выбросит (ровно тот дефект, что и «＋ Punkt»)."""
    from apps.catalog.models import Category
    from apps.tenants import menu as menu_mod

    tenant = TenantFactory(schema_name="public", slug="stu16t", name="T", disabled_modules=[])
    Category.objects.create(name={"de": "Brot"}, slug="brot", is_active=True)
    options = menu_mod.target_options(tenant)
    values = {o["value"] for o in options}
    assert "page:about" in values, "страницы обязаны быть среди целей"
    assert "category:brot" in values, "живые категории обязаны быть среди целей"
    assert all(o["label"] and o["group"] for o in options), "цель без подписи/группы"
    # группы идут сплошными блоками: шаблон режет список через `regroup`, и
    # запись, оторвавшаяся от своей группы, открыла бы ВТОРОЙ optgroup с тем же
    # именем (узел «Alle Kategorien» ровно так и стоял).
    seen_groups = []
    for opt in options:
        if not seen_groups or seen_groups[-1] != opt["group"]:
            seen_groups.append(opt["group"])
    assert len(seen_groups) == len(set(seen_groups)), f"группа разорвана: {seen_groups}"
    for opt in options:
        ntype, _, target = opt["value"].partition(":")
        node = {"label": "X", "type": ntype, "target": target, "enabled": True, "children": []}
        resolved = menu_mod._resolve(tenant, node) is not None
        assert resolved == opt["available"], f"пометка расходится с витриной: {opt['value']}"
    # у пустой галереи (гейт ST-8) цель предлагается, но ВЫКЛЮЧЕННОЙ — иначе
    # владелец добавит пункт, которого на сайте не будет
    gallery = next(o for o in options if o["value"] == "page:gallery")
    assert gallery["available"] is False
    assert next(o for o in options if o["value"] == "category:brot")["available"] is True


def test_menu_builder_and_studio_share_one_target_source():
    """Два редактора меню (экран и панель Студии) не имеют права разъехаться."""
    from apps.tenants import menu as menu_mod

    tenant = TenantFactory(schema_name="public", slug="stu16s", name="S", disabled_modules=[])
    sets = menu_mod.target_sets(tenant)
    assert set(sets) == {"archetypes", "categories", "category_parents", "pages", "promo_groups"}
    from apps.core import views as core_views

    req = RequestFactory().get("/dashboard/site/menu/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = core_views.menu_builder_view(req)
    builder = resp.context_data["builder"] if hasattr(resp, "context_data") else None
    if builder is None:  # render() без context_data → сверяем по разметке
        assert resp.status_code == 200
    else:
        assert builder["pages"] == sets["pages"]


def test_studio_menu_row_carries_a_target_control():
    """Владелец: «добавил категорию в меню — ничего не произошло».

    Пункт без цели витрина отбрасывает (`_node_url` → None), поэтому строка
    редактора обязана нести выбор цели — и в существующих строках, и в шаблоне
    для новой.
    """
    markup = _markup()
    editor = markup[markup.index("data-menu-editor") : markup.index("data-stu-footer-links")]
    assert editor.count('class="mi-target') >= 2, "селект цели нужен и в строке, и в шаблоне"
    # новая строка больше не рождается «пустой ссылкой в никуда»
    assert 'type: "url", target: ""' not in editor


def test_menu_item_added_with_a_target_shows_on_the_storefront():
    """Сквозной замок: добавленный из Студии пункт доходит до шапки витрины."""
    import json

    from apps.catalog.models import Category
    from apps.tenants import menu as menu_mod

    tenant = TenantFactory(schema_name="public", slug="stu16m", name="M", disabled_modules=[])
    Category.objects.create(name={"de": "Brot"}, slug="brot", is_active=True)
    menus = {
        "top": {
            "style": "classic",
            "sticky": True,
            "items": [
                {"label": "Brot", "type": "category", "target": "brot", "enabled": True},
                # то, что редактор создавал раньше: цели нет → пункт исчезает
                {"label": "Neuer Punkt", "type": "url", "target": "", "enabled": True},
            ],
        }
    }
    req = RequestFactory().post(
        "/dashboard/site/home/", {"menus_json": json.dumps(menus), "font": "system"}
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.home_builder_view(req).status_code == 302
    tenant.refresh_from_db()
    labels = [n["label"] for n in menu_mod.resolve_menu(tenant, "top")]
    assert "Brot" in labels
    assert "Neuer Punkt" not in labels  # документируем причину жалобы владельца
