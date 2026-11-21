"""LB-4b: строка встроенного списка главной в Студии = поля «ЧТО» блока «Liste».

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §5. Замки написаны ДО кода:

* у каждой из восьми списочных строк ровно те поля «ЧТО», что у блока «Liste» её
  источника (фильтры реестра + сортировка, если она есть, + форма карточки, если она
  есть), с префиксом `sl_<ключ>_` и сентинелом присутствия;
* у товаров селект «Which items» уступает место общим «Auswahl» + «Sortierung» (одно
  место на одну настройку), легаси-значение их предзаполняет;
* Save сохраняет «ЧТО» в `row["data"]`, а выразимое легаси-полем `source` — им
  (данные строки не растут у тех, кто ничего не менял); без сентинела (вкладка до
  деплоя) — данные строки целы (W0); сирота фильтра остаётся выбранной (W0);
* черновик несёт все поля; «Als eigenen Block kopieren» кладёт рядом блок «Liste» с
  той же выборкой.
"""

import itertools
import re

import pytest

from apps.core import list_blocks
from apps.core.tests.test_stu12_groups import TPL, _builder, _post_builder, _row, _segment
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()

# Поля «ЧТО» строки по ключу секции — ровно поля блока «Liste» её источника.
WHAT = {
    # LB-4d (осознанно): + «Gilt für» — цель акции
    "promotions": {"type", "endet", "rabatt", "ziel", "sort", "card"},
    "products": {"category", "collection", "only", "sort", "card"},
    "services": {"collection", "only", "sort", "card"},
    "stay_rooms": {"collection", "sort", "card"},
    "events": {"event_category", "only", "sort", "card"},
    "tours": {"country", "card"},
    "categories": {"category"},
    "blog": set(),
}


def _tenant(**cfg):
    return TenantFactory(slug=f"lb4s{next(_N)}", name="LB4S", disabled_modules=[], site_config=cfg)


def _sl_fields(body) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for key in siteconfig.BUILTIN_LIST_SOURCES:
        names = set(re.findall(rf'name="sl_{key}_([a-z_]+)"', body))
        out[key] = names - {"present"}
    return out


def _select(html, name):
    i = html.index(f'name="{name}"')
    return html[i : html.index("</select>", i)]


def _selected(select_html) -> list[str]:
    return re.findall(r'value="([^"]*)"[^>]*selected', select_html)


def test_what_fields_are_derived_from_the_source_registry():
    """Таблица выше — не вкусовщина: фильтры реестра (у акций «Demnächst» — пункт
    селекта срока, а не своё поле) + сортировка + форма карточки источника."""
    for key, source in siteconfig.BUILTIN_LIST_SOURCES.items():
        spec = siteconfig.LIST_SOURCES[source]
        derived = set(spec["filters"]) - {"phase"}
        if siteconfig.list_sort_keys(source):
            derived.add("sort")
        if spec["card"]:
            derived.add("card")
        assert WHAT[key] == derived, key


def test_each_builtin_row_offers_exactly_the_what_of_its_source():
    """FB-33 M4b (осознанная переписка): оси «ЧТО» всех восьми строк правит окно блока —
    в строке Студии их (и сентинела) нет, остаётся «Als eigenen Block kopieren»."""
    body = _builder(_tenant())
    fields = _sl_fields(body)
    for key in WHAT:
        assert fields[key] == set(), key
        assert f'name="sl_{key}_present"' not in body, key
        assert f"copy_builtin:{key}" in _row(body, key), key


def test_products_row_has_one_place_for_which_items():
    """FB-33 M4b (осознанная переписка): выбор товаров — одно место, окно блока."""
    body = _builder(_tenant(sections=[{"key": "products", "source": "featured_only"}]))
    row = _row(body, "products")
    assert 'name="source_products"' not in row  # легаси-селект ушёл
    assert 'name="sl_products_only"' not in row and 'name="sl_products_sort"' not in row
    assert "tab=wie" in row  # ссылка в окно блока


def _save(tenant, **fields):
    post = {f"sl_{k}": v for k, v in fields.items()}
    for key in {k.split("_", 1)[0] if not k.startswith("stay_") else "stay_rooms" for k in fields}:
        post[f"sl_{key}_present"] = "1"
    return _post_builder(tenant, post)


def _row_of(cfg, key):
    return next(s for s in cfg["sections"] if s["key"] == key)


SAVED_WHAT = {
    "promotions": {"type": "Woche", "endet": "heute", "card": "coupon"},
    "services": {"collection": "haar", "only": "video"},
    "stay_rooms": {"collection": "meerblick"},
    "events": {"event_category": "yoga", "only": "soon"},
    "tours": {"country": "Nepal"},
    "categories": {"category": "feinkost"},
}


def test_save_keeps_the_what_of_every_builtin_row():
    """LB-4b → FB-33 M4b (осознанная переписка): «ЧТО» встроенных списков правит окно
    блока «Seitenaufbau»; присланное Студией (устаревшая или подделанная форма с
    сентинелом) не действует — данные строк остаются сохранёнными."""
    tenant = _tenant(sections=[{"key": k, "data": dict(v)} for k, v in SAVED_WHAT.items()])
    cfg = _save(
        tenant,
        promotions_type="Andere",
        promotions_endet="woche",
        services_only="",
        events_event_category="tanz",
        tours_country="Peru",
        categories_category="brot",
        blog_sort="newest",
    )
    for key, data in SAVED_WHAT.items():
        assert _row_of(cfg, key)["data"] == data, key
    assert "data" not in _row_of(cfg, "blog")


@pytest.mark.parametrize(
    "sort,only,source,data",
    [
        ("featured", "", "featured_first", None),
        ("newest", "", "newest", None),
        ("newest", "featured", "featured_only", None),
        ("price_asc", "", "featured_first", {"sort": "price_asc"}),
        ("featured", "sale", "featured_first", {"sort": "featured", "only": "sale"}),
    ],
)
def test_products_choice_expressible_by_the_legacy_source_stays_there(sort, only, source, data):
    """FB-33 M4b (осознанная переписка): тот же расклад — теперь у писателя окна
    (`site_schema._update_builtin`), Студия выбор товаров не пишет."""
    from apps.core import site_schema

    tenant = _tenant()
    site_schema.apply(tenant, "home", "update", ref="products", fields={"sort": sort, "only": only})
    row = _row_of(siteconfig.normalize(_fresh(tenant).site_config), "products")
    assert row["source"] == source
    assert row.get("data") == data
    cfg = _save(_fresh(tenant), products_sort="price_desc", products_only="available")
    assert _row_of(cfg, "products").get("data") == data  # Студия не перебивает окно


def test_products_filter_and_card_survive_save_next_to_the_legacy_source():
    from apps.core import site_schema

    tenant = _tenant()
    fields = {"sort": "newest", "category": "brot", "card": "regal"}
    site_schema.apply(tenant, "home", "update", ref="products", fields=fields)
    cfg = _post_builder(_fresh(tenant), {})  # «Speichern» Студии без полей «ЧТО» (W0)
    row = _row_of(cfg, "products")
    assert row["source"] == "newest"
    assert row["data"] == {"category": "brot", "card": "regal"}


def _fresh(tenant):
    tenant.refresh_from_db()
    return tenant


def test_save_without_the_sentinel_keeps_the_rows_data():
    """Вкладка Студии, открытая до деплоя, полей «ЧТО» не шлёт — Save их не стирает."""
    tenant = _tenant(sections=[{"key": "products", "data": {"category": "brot"}}])
    cfg = _post_builder(tenant, {})
    assert _row_of(cfg, "products")["data"] == {"category": "brot"}


def test_orphan_filter_value_stays_selected():
    """FB-33 M4b (осознанная переписка): сирота фильтра — W0 «Speichern» Студии: поля нет,
    значение остаётся (выбранной её держит окно, `list_panel._select`)."""
    tenant = _tenant(sections=[{"key": "products", "data": {"category": "weg"}}])
    cfg = _post_builder(tenant, {"order_products": "1"})
    assert _row_of(cfg, "products")["data"] == {"category": "weg"}


def test_card_form_of_the_row_is_selected():
    """FB-33 M4b (осознанная переписка): форма карточки — вкладка «Karte» окна; «Speichern»
    Студии её не стирает."""
    tenant = _tenant(sections=[{"key": "promotions", "data": {"card": "coupon"}}])
    cfg = _post_builder(tenant, {"order_promotions": "1"})
    assert _row_of(cfg, "promotions")["data"] == {"card": "coupon"}


def test_live_draft_carries_every_what_field():
    draft = set(re.findall(r'"(\w+)"', _segment(TPL.read_text("utf-8"), "var SL_DATA_FIELDS", "]")))
    missing = sorted(set().union(*WHAT.values()) - draft)
    assert not missing, f"черновик не несёт поля встроенных списков: {missing}"
    # один список полей на Save и черновик — без расхождения
    assert draft == set(list_blocks.BUILTIN_WHAT_FIELDS)


def test_copy_builtin_row_puts_a_list_block_next_to_it():
    """FB-33 M4b (осознанная переписка): копия берёт выборку строки как СОХРАНЕНО — полей
    «ЧТО» в Студии больше нет, присланные (устаревшая вкладка) не действуют."""
    tenant = _tenant(
        sections=[{"key": "products", "data": {"category": "brot", "sort": "price_asc"}}]
    )
    cfg = _post_builder(
        tenant,
        {
            "action": "copy_builtin:products",
            "sl_products_present": "1",
            "sl_products_category": "torten",
            "sl_products_sort": "newest",
        },
    )
    keys = [s["key"] for s in cfg["sections"]]
    i = keys.index("products")
    block = cfg["sections"][i + 1]
    assert block["key"] == "list"
    assert block["data"]["source"] == "products"
    assert block["data"]["category"] == "brot" and block["data"]["sort"] == "price_asc"


def test_draft_endpoint_keeps_the_what_of_builtin_rows():
    """Стенд LB-4b: клиент слал `data` строки товаров, а эндпоинт черновика пропускал у
    фикс-секций только поля своего белого списка. FB-33 M4b: «ЧТО» правит окно блока —
    присланное черновиком не действует (превью = результат «Speichern»)."""
    import json

    from apps.core import views
    from apps.core.tests.test_stu12_groups import _req

    tenant = _tenant()
    payload = {
        "sections": [
            {"key": "products", "enabled": True, "data": {"category": "torten", "sort": "newest"}},
            {"key": "promotions", "enabled": True, "data": {"type": "Woche", "card": "coupon"}},
            {"key": "faq", "enabled": True, "data": {"sort": "x"}},  # не список — не несёт
        ]
    }
    req = _req("post", "/dashboard/site/preview/draft/", tenant)
    req._body = json.dumps(payload).encode()
    req.META["CONTENT_TYPE"] = "application/json"
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    draft = siteconfig.normalize(req.session["site_preview_draft"])
    rows = {s["key"]: s for s in draft["sections"] if "id" not in s}
    # FB-33 M4b (осознанная переписка): «ЧТО» встроенных списков правит окно блока —
    # черновик Студии показывает то же, что сохранит её «Speichern»: сохранённое.
    assert "data" not in rows["products"] and "data" not in rows["promotions"]
    assert "data" not in rows["faq"]
