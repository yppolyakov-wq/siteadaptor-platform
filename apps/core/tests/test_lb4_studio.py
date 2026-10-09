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
    "promotions": {"type", "endet", "rabatt", "sort", "card"},
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
    body = _builder(_tenant())
    fields = _sl_fields(body)
    for key, expected in WHAT.items():
        assert fields[key] == expected, key
        if expected:
            assert f'name="sl_{key}_present"' in _row(body, key), key


def test_products_row_has_one_place_for_which_items():
    body = _builder(_tenant(sections=[{"key": "products", "source": "featured_only"}]))
    row = _row(body, "products")
    assert 'name="source_products"' not in row  # легаси-селект ушёл
    assert _selected(_select(row, "sl_products_only")) == ["featured"]
    assert _selected(_select(row, "sl_products_sort")) == ["newest"]
    default = _row(_builder(_tenant()), "products")
    assert _selected(_select(default, "sl_products_sort")) == ["featured"]


def _save(tenant, **fields):
    post = {f"sl_{k}": v for k, v in fields.items()}
    for key in {k.split("_", 1)[0] if not k.startswith("stay_") else "stay_rooms" for k in fields}:
        post[f"sl_{key}_present"] = "1"
    return _post_builder(tenant, post)


def _row_of(cfg, key):
    return next(s for s in cfg["sections"] if s["key"] == key)


def test_save_keeps_the_what_of_every_builtin_row():
    cfg = _save(
        _tenant(),
        promotions_type="Woche",
        promotions_endet="heute",
        promotions_card="coupon",
        services_collection="haar",
        services_only="video",
        stay_rooms_collection="meerblick",
        events_event_category="yoga",
        events_only="soon",
        tours_country="Nepal",
        categories_category="feinkost",
    )
    assert _row_of(cfg, "promotions")["data"] == {
        "type": "Woche",
        "endet": "heute",
        "card": "coupon",
    }
    assert _row_of(cfg, "services")["data"] == {"collection": "haar", "only": "video"}
    assert _row_of(cfg, "stay_rooms")["data"] == {"collection": "meerblick"}
    assert _row_of(cfg, "events")["data"] == {"event_category": "yoga", "only": "soon"}
    assert _row_of(cfg, "tours")["data"] == {"country": "Nepal"}
    assert _row_of(cfg, "categories")["data"] == {"category": "feinkost"}
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
    cfg = _save(_tenant(), products_sort=sort, products_only=only)
    row = _row_of(cfg, "products")
    assert row["source"] == source
    assert row.get("data") == data


def test_products_filter_and_card_survive_save_next_to_the_legacy_source():
    cfg = _save(_tenant(), products_sort="newest", products_category="brot", products_card="regal")
    row = _row_of(cfg, "products")
    assert row["source"] == "newest"
    assert row["data"] == {"category": "brot", "card": "regal"}


def test_save_without_the_sentinel_keeps_the_rows_data():
    """Вкладка Студии, открытая до деплоя, полей «ЧТО» не шлёт — Save их не стирает."""
    tenant = _tenant(sections=[{"key": "products", "data": {"category": "brot"}}])
    cfg = _post_builder(tenant, {})
    assert _row_of(cfg, "products")["data"] == {"category": "brot"}


def test_orphan_filter_value_stays_selected():
    body = _builder(_tenant(sections=[{"key": "products", "data": {"category": "weg"}}]))
    select = _select(_row(body, "products"), "sl_products_category")
    assert _selected(select) == ["weg"]


def test_card_form_of_the_row_is_selected():
    body = _builder(_tenant(sections=[{"key": "promotions", "data": {"card": "coupon"}}]))
    assert _selected(_select(_row(body, "promotions"), "sl_promotions_card")) == ["coupon"]


def test_live_draft_carries_every_what_field():
    draft = set(re.findall(r'"(\w+)"', _segment(TPL.read_text("utf-8"), "var SL_DATA_FIELDS", "]")))
    missing = sorted(set().union(*WHAT.values()) - draft)
    assert not missing, f"черновик не несёт поля встроенных списков: {missing}"
    # один список полей на Save и черновик — без расхождения
    assert draft == set(list_blocks.BUILTIN_WHAT_FIELDS)


def test_copy_builtin_row_puts_a_list_block_next_to_it():
    tenant = _tenant()
    cfg = _post_builder(
        tenant,
        {
            "action": "copy_builtin:products",
            "sl_products_present": "1",
            "sl_products_category": "brot",
            "sl_products_sort": "price_asc",
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
    фикс-секций только поля своего белого списка — фильтр без Save на канве не
    действовал. Замок класса «клиент шлёт → сервер не роняет»."""
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
    assert rows["products"]["data"] == {"category": "torten", "sort": "newest"}
    assert rows["promotions"]["data"] == {"type": "Woche", "card": "coupon"}
    assert "data" not in rows["faq"]
