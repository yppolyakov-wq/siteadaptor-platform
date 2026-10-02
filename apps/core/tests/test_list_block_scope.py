"""LB-1b: пилюля охвата блока «Liste» — «Nur diesen Block · Den ganzen Typ».

План — `docs/lb-list-blocks-plan-2026-10-02.md` §9.8 и §10 (решение владельца Р-2: вид
у блока, с наследованием и переключателем охвата). Замки написаны ДО кода.

Во втором режиме те же контролы вида пишут настройки ТИПА акции —
`promo_groups[тип].layout/card`, то есть то же хранение, что экран «Aktionstypen» и
страница типа. Поэтому «Den ganzen Typ» меняет сразу все блоки этого типа и его
страницу, а у самого блока оси очищаются (иначе он «запомнил» бы значение и перестал
следовать за типом). Одна функция для Save и для черновика — превью и сохранение не
расходятся.

Плюс два дефекта класса W0, найденные при разборе: селектор типа/категории терял
значение блока, когда тип сейчас без акций (Save молча делал блок «все акции»), и
экран «Aktionstypen» стирал темп ленты, заданный из блока.
"""

import itertools
import json
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import list_blocks
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block(bid=None, **data):
    return {"key": "list", "id": bid or f"sc{next(_N)}", "enabled": True, "data": data}


def _tenant(**cfg):
    # Схема НЕ public: context-processor витрины для public-схемы молчит (урок ST-3).
    t = TenantFactory(slug=f"sc{next(_N)}", name="Sc")
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    return t


def _req(method, path, tenant, data=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _promo(title, **kw):
    kw.setdefault("promo_type", "discount")
    kw.setdefault("discount_percent", 30)
    return Promotion.objects.create(title={"de": title}, status="active", **kw)


def _home(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _builder(tenant):
    from apps.core import views

    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _selected(body, name):
    """Значение, которое браузер отправит из `<select name=…>` (выбранный пункт)."""
    m = re.search(rf'<select name="{re.escape(name)}"[^>]*>(.*?)</select>', body, re.S)
    assert m, name
    options = re.findall(r'<option value="([^"]*)"([^>]*)>', m.group(1))
    chosen = [value for value, attrs in options if re.search(r"\bselected\b", attrs)]
    return chosen[-1] if chosen else (options[0][0] if options else "")


# ───────────────────────── перенос вида в тип ─────────────────────────


def test_type_scope_moves_the_view_to_the_type_and_clears_the_block():
    cfg = {
        "sections": [
            _block(
                "b1",
                source="promotions",
                type="Räumung",
                scope="type",
                out="slider",
                cols="4",
                rows="2",
                speed="6",
                card="coupon",
                title="Restposten",
            )
        ],
        "promo_groups": {"Räumung": "countdown", "Andere": {"card": "ring"}},
    }
    list_blocks.apply_type_scope(cfg)
    block = cfg["sections"][0]["data"]
    # у блока остались только «ЧТО» и тексты — вид теперь у типа
    assert block == {"source": "promotions", "type": "Räumung", "title": "Restposten"}
    own = siteconfig.normalize(cfg)["promo_groups"]["Räumung"]
    # шаблон страницы типа (style) не тронут — пилюля правит только оси вида
    assert own["style"] == "countdown"
    assert own["card"] == "coupon"
    assert own["layout"]["scroll"] is True
    assert own["layout"]["cols"] == 4 and own["layout"]["rows"] == 2
    assert own["layout"]["speed"] == 6
    # чужой тип не тронут
    assert siteconfig.normalize(cfg)["promo_groups"]["Andere"] == {"card": "ring"}


def test_empty_values_in_type_scope_mean_the_type_inherits_again():
    cfg = {
        "page_blocks": {"info": [_block("b2", source="promotions", type="Räumung", scope="type")]},
        "promo_groups": {
            "Räumung": {
                "style": "countdown",
                "card": "ring",
                "layout": {"preset": "cols4", "cols": 4, "scroll": True},
            }
        },
    }
    list_blocks.apply_type_scope(cfg)
    # тип снова наследует страницу: ни своей сетки, ни своей формы карточки
    assert siteconfig.normalize(cfg)["promo_groups"]["Räumung"] == "countdown"
    assert "scope" not in cfg["page_blocks"]["info"][0]["data"]


def test_scope_is_ignored_without_a_type_or_for_products():
    cfg = {
        "sections": [
            _block("p1", source="products", scope="type", cols="3"),
            _block("p2", source="promotions", scope="type", cols="3"),
        ]
    }
    list_blocks.apply_type_scope(cfg)
    assert cfg["sections"][0]["data"]["cols"] == "3"
    assert cfg["sections"][1]["data"]["cols"] == "3"
    assert "promo_groups" not in siteconfig.normalize(cfg)
    # служебное поле не переживает разбор ни в каком случае
    assert all("scope" not in s["data"] for s in cfg["sections"])


def test_scope_is_never_stored():
    data = siteconfig._clean_cblock_data("list", {"source": "promotions", "scope": "type"})
    assert "scope" not in data


def test_type_layout_starts_from_the_page_layout():
    """Слой раскладки у типа «всё или ничего» (`base_view` берёт раскладку типа целиком).
    Поэтому пустая ось в режиме типа значит «как на странице», а не «дефолт секции»:
    подпись «wie die Seite: 4» обязана совпасть с результатом."""
    cfg = {
        "promo_index_layout": {"preset": "cols4", "cols": 4},
        "sections": [_block("m1", source="promotions", type="Räumung", scope="type", out="slider")],
    }
    list_blocks.apply_type_scope(cfg)
    own = siteconfig.normalize(cfg)["promo_groups"]["Räumung"]
    assert own["layout"]["scroll"] is True
    assert own["layout"]["cols"] == 4  # колонки страницы, а не дефолтные 3


def test_raster_over_a_lane_page_is_expressible_for_the_type():
    """Страница акций — лента (легаси `promo_layout`). «Raster» в режиме типа обязан
    дать типу сетку: без раскладки тип просто унаследовал бы ленту страницы."""
    cfg = {
        "promo_layout": "slider",
        "sections": [_block("g1", source="promotions", type="Räumung", scope="type", out="grid")],
    }
    list_blocks.apply_type_scope(cfg)
    cfg = siteconfig.normalize(cfg)
    view = list_blocks.effective_view(cfg, {"source": "promotions", "type": "Räumung"})
    assert view["mode"] == "grid"


# ───────────────────────── Save и черновик ─────────────────────────


def test_builder_save_in_type_scope_updates_all_blocks_of_the_type():
    from apps.core import views

    t = _tenant(
        sections=[
            _block("a1", source="promotions", type="Räumung"),
            _block("a2", source="promotions", type="Räumung", title="Zweiter"),
        ],
        promo_groups={"Räumung": "countdown"},
    )
    post = {
        "cb_id": ["a1", "a2"],
        "cb_type_a1": "list",
        "cb_type_a2": "list",
        "enabled_cb_a1": "on",
        "enabled_cb_a2": "on",
        "order_cb_a1": "1",
        "order_cb_a2": "2",
        "cb_a1_source": "promotions",
        "cb_a1_type": "Räumung",
        "cb_a1_scope": "type",
        "cb_a1_out": "slider",
        "cb_a1_card": "coupon",
        "cb_a2_source": "promotions",
        "cb_a2_type": "Räumung",
        "cb_a2_title": "Zweiter",
    }
    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", t, post))
    assert resp.status_code == 302
    t.refresh_from_db()
    cfg = siteconfig.normalize(t.site_config)
    assert cfg["promo_groups"]["Räumung"]["card"] == "coupon"
    assert cfg["promo_groups"]["Räumung"]["layout"]["scroll"] is True
    assert cfg["promo_groups"]["Räumung"]["style"] == "countdown"
    a1 = next(s for s in cfg["sections"] if s.get("id") == "a1")
    assert "card" not in a1["data"] and "out" not in a1["data"]
    # ВТОРОЙ блок того же типа тоже стал лентой купонов — он наследует тип
    _promo("Rest", group="Räumung")
    body = _home(t)
    assert body.count("data-promo-strip") == 2
    assert body.count('data-card-form="coupon"') == 2


def test_type_scope_reaches_the_live_draft():
    """Превью обязано показать то же, что покажет Save: одна функция на оба пути."""
    from apps.core import views

    t = _tenant(sections=[_block("d1", source="promotions", type="Räumung")])
    payload = {
        "sections": [
            {
                "key": "list",
                "id": "d1",
                "enabled": True,
                "data": {
                    "source": "promotions",
                    "type": "Räumung",
                    "scope": "type",
                    "card": "ring",
                },
            }
        ]
    }
    req = RequestFactory().post(
        "/dashboard/site/preview-draft/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    req.user = SimpleNamespace(is_authenticated=True)
    views.site_preview_draft(req)
    draft = req.session["site_preview_draft"]
    assert draft["promo_groups"]["Räumung"]["card"] == "ring"
    block = next(s for s in draft["sections"] if s.get("id") == "d1")
    assert "card" not in block["data"]


# ───────────────────────── редактор ─────────────────────────


def test_editor_row_carries_the_scope_control():
    t = _tenant(sections=[_block("e1", source="promotions", type="Räumung")])
    body = _builder(t)
    assert 'name="cb_e1_scope"' in body
    assert "data-lb-scope-row" in body
    # карта видов типов для переключения режима — один раз на страницу
    assert body.count('id="lb-type-views"') == 1


def test_type_views_map_carries_the_type_values_and_page_labels():
    t = _tenant(
        sections=[_block("v1", source="promotions", type="Räumung")],
        promo_groups={
            "Räumung": {"card": "coupon", "layout": {"preset": "cols4", "cols": 4, "scroll": True}}
        },
    )
    body = _builder(t)
    raw = re.search(
        r'<script id="lb-type-views" type="application/json">(.*?)</script>', body, re.S
    )
    views_map = json.loads(raw.group(1))
    own = views_map["types"]["Räumung"]
    assert own == {"out": "slider", "cols": "4", "rows": "", "speed": "", "card": "coupon"}
    # подписи пустых пунктов в режиме типа — откуда тип возьмёт значение (страница)
    assert set(views_map["page"]) >= {"out", "cols", "rows", "card", "mode"}


# ───────────────────── дефекты класса W0 (попутно) ─────────────────────


def test_block_type_survives_save_when_the_type_has_no_live_promotions():
    """Селектор строился из ЖИВЫХ типов: у блока, чей тип сейчас без акций, браузер
    отправлял «Alle Aktionen», и Save молча делал из него блок «все акции»."""
    t = _tenant(sections=[_block("o1", source="promotions", type="Räumung")])
    _promo("Sonst", group="Wochenangebote")  # живой тип есть, но не этот
    body = _builder(t)
    assert _selected(body, "cb_o1_type") == "Räumung"


def test_block_category_survives_save_when_the_category_is_gone():
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Käse"}, slug="kaese")
    t = _tenant(sections=[_block("o2", source="products", category="alt-kategorie")])
    body = _builder(t)
    assert _selected(body, "cb_o2_category") == "alt-kategorie"


def test_types_screen_keeps_the_lane_speed_set_from_a_block():
    """Экран «Aktionstypen» пересобирал раскладку из трёх своих полей — темп ленты,
    заданный из блока, стирался его Save."""
    from django.contrib.auth import get_user_model

    from apps.promotions import views as promo_views

    t = _tenant(
        promo_groups={
            "Räumung": {"layout": {"preset": "cols4", "cols": 4, "scroll": True, "speed": 6}}
        }
    )
    _promo("Rest", group="Räumung")
    req = _req(
        "post",
        "/promotions/typen/speichern/",
        t,
        {"mode:Räumung": "slider", "cols:Räumung": "4", "rows:Räumung": ""},
    )
    req.user = get_user_model()(is_active=True)
    promo_views.promo_type_save(req)
    t.refresh_from_db()
    layout = siteconfig.normalize(t.site_config)["promo_groups"]["Räumung"]["layout"]
    assert layout["speed"] == 6
    assert layout["scroll"] is True and layout["cols"] == 4
