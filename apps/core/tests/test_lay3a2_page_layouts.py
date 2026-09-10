"""LAY-3a-2 — ось вывода на страницах, где сетка была захардкожена.

Разведка (план LAY §13) нашла восемь поверхностей и 12 грид-контейнеров, у которых
число колонок зашито литералом в шаблоне: обзор акций, наборы, поездки, лукбук,
отзывы, Merkzettel, блог. Владелец не мог задать там ни колонки, ни ряды, ни хвост —
при том что на соседних листингах эта ось есть с LAY-3a/3b.

Ключи presence-minimal (образец `service_index_layout`): ключа нет → шаблон рисует
прежние классы, страница пиксельно не меняется. Замки написаны ДО правок.
"""

import pytest
from django.template.loader import render_to_string

from apps.core import studio_pages
from apps.tenants import siteconfig

OPTIONAL_KEYS = (
    "promo_index_layout",
    "combos_layout",
    "tours_layout",
    "lookbook_layout",
    "reviews_page_layout",
    "wishlist_layout",
    "blog_index_layout",
)


def test_keys_are_presence_minimal():
    """Пустой конфиг не материализует ни один новый ключ (golden-паритет)."""
    cfg = siteconfig.normalize({})
    for key in OPTIONAL_KEYS:
        assert key not in cfg, f"{key} материализуется — golden-эталоны поедут"


def test_keys_survive_normalize_with_all_output_axis_fields():
    """Заданная раскладка переживает normalize вместе с параметрами типа вывода."""
    raw = {
        key: {"preset": "cols5", "rows": 2, "tail": "fill", "scroll": True, "speed": 7}
        for key in OPTIONAL_KEYS
    }
    cfg = siteconfig.normalize(raw)
    for key in OPTIONAL_KEYS:
        assert cfg[key]["cols"] == 5, key
        assert cfg[key]["rows"] == 2, key
        assert cfg[key]["tail"] == "fill", key
        assert cfg[key]["speed"] == 7, key


def test_garbage_does_not_crash_and_falls_back():
    """Мусор в ключе не роняет витрину — раскладка берётся дефолтная."""
    cfg = siteconfig.normalize({key: "nonsense" for key in OPTIONAL_KEYS})
    for key in OPTIONAL_KEYS:
        assert key not in cfg or isinstance(cfg[key], dict)


def test_every_new_key_has_a_default_for_the_recommendation_rule():
    """LAY-5 (Р-3) сравнивает раскладку с дефолтом — дефолт обязан быть известен."""
    for key in OPTIONAL_KEYS:
        assert key in siteconfig.PAGE_LAYOUT_DEFAULTS, f"{key} без дефолта: правило Р-3 слепо"


@pytest.mark.parametrize(
    "code,setting",
    [
        ("promos", "promo_index_layout"),
        ("combos", "combos_layout"),
        ("tours", "tours_layout"),
        ("lookbook", "lookbook_layout"),
        ("reviews", "reviews_page_layout"),
        ("wishlist", "wishlist_layout"),
        ("blog", "blog_index_layout"),
    ],
)
def test_studio_offers_the_axis_on_that_page(code, setting):
    """Настройка объявлена у СВОЕГО типа страницы (иначе её негде задать)."""
    assert setting in studio_pages.page_type(code).settings, f"{code}: оси вывода нет в панели"


def test_panel_renders_a_control_for_each_new_setting():
    """Реестр и разметка панели обязаны сходиться (замок STU-8): у каждой новой
    настройки есть своя строка с селектом пресета и параметрами типа вывода."""
    with open("templates/tenant/site_home.html", encoding="utf-8") as fh:
        panel = fh.read()
    for key in OPTIONAL_KEYS:
        field = key.replace("_layout", "")
        assert f'data-stu-setting="{key}"' in panel, f"{key}: строки в панели нет"
        assert f'name="{field}_preset"' in panel, f"{key}: селект раскладки не выведен"
    axis = render_to_string(
        "tenant/_output_axis.html",
        {"field": "promo_index", "layout": {"preset": "cols3", "cols": 3}},
    )
    assert 'name="promo_index_mode"' in axis


@pytest.mark.parametrize(
    "template,ctx,legacy",
    [
        ("storefront/promotions_list.html", {}, "lg:grid-cols-3"),
        ("storefront/combos.html", {}, "lg:grid-cols-4"),
        ("storefront/blog_index.html", {}, "lg:grid-cols-3"),
    ],
)
def test_pages_keep_their_markup_without_the_key(template, ctx, legacy):
    """Без ключа разметка прежняя — это и есть гарантия пиксельной неизменности."""
    with open("templates/" + template, encoding="utf-8") as fh:
        body = fh.read()
    assert legacy in body, f"{template}: легаси-классы пропали"
    assert "|default:" in body, f"{template}: сетка не переведена на движок с фолбэком"


@pytest.mark.django_db
def test_promo_listing_renders_the_chosen_grid(settings):
    """Выбранная раскладка ДЕЙСТВУЕТ на витрине (а не только сохраняется)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.promotions.models import Promotion
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="lay3a2", name="LAY3A2")
    Promotion.objects.create(title={"de": "Deal"}, status="active")
    req = RequestFactory().get("/aktionen/")
    req.tenant = tenant
    assert "lg:grid-cols-3" in public_views.promotion_list(req).content.decode()

    tenant.site_config = siteconfig.normalize({"promo_index_layout": {"preset": "cols5"}})
    tenant.save(update_fields=["site_config"])
    body = public_views.promotion_list(req).content.decode()
    assert "lg:grid-cols-5" in body, "раскладка сохранена, но витрина её не читает"
    assert 'data-sf-cols="2/2/5"' in body or "data-sf-cols" in body
