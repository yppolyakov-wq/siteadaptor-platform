"""DL-11 «Volle Reihen»: ряды плиток заполнены на всех шаблонах и ширинах.

Слой 1 (движок): ключ `tail` раскладки presence-minimal, триплет колонок —
единственный источник чисел, атрибуты data-sf-cols/data-sf-tail рядом с
Tailwind-классами (сами классы не меняются — замки test_layout целы).
Слой 2 (CSS): блок quantity-queries в static/src/app.css совпадает с выводом
генератора (правки — только через scripts/gen_fill_rows_css.py).
"""

from __future__ import annotations

import importlib.util
import re
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.template import Context, Template
from django.test import RequestFactory

from apps.catalog.models import Category
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


# --- normalize / триплет / атрибуты --------------------------------------------


def test_tail_presence_minimal():
    assert "tail" not in siteconfig.normalize_layout({})
    assert "tail" not in siteconfig.normalize_layout({"tail": ""})
    assert "tail" not in siteconfig.normalize_layout({"tail": "trim"})  # дефолт не пишем
    assert "tail" not in siteconfig.normalize_layout({"tail": "garbage"})
    assert siteconfig.normalize_layout({"tail": "show"})["tail"] == "show"
    assert siteconfig.normalize_layout({"tail": "fill"})["tail"] == "fill"


def test_tail_survives_normalize_of_home_section():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "layout": {"tail": "show"}}]}
    )
    lay = siteconfig.section_layout(cfg, "products")
    assert lay["tail"] == "show"
    # и не появляется у секций без ключа (golden-инвариант)
    assert "tail" not in siteconfig.section_layout(cfg, "categories")


@pytest.mark.parametrize(
    ("layout", "triplet"),
    [
        ({"preset": "cols4"}, (2, 3, 4)),
        ({"preset": "cols3"}, (2, 2, 3)),
        ({"preset": "cols3", "mobile": 1}, (1, 2, 3)),
        ({"preset": "cols2"}, (1, 2, 2)),
        ({"preset": "list"}, (1, 1, 1)),
        ({"preset": "cols6"}, (2, 3, 6)),
        ({"preset": "cols4", "tablet": 4}, (2, 4, 4)),  # SE-3c явный планшет
    ],
)
def test_grid_cols_triplet_matches_class_string(layout, triplet):
    assert siteconfig.grid_cols_triplet(layout) == triplet
    classes = siteconfig.grid_class_string(layout)
    m, s, lg = triplet
    assert f"grid-cols-{m} sm:grid-cols-{s} lg:grid-cols-{lg}" in classes


def test_grid_attr_string_default_trim():
    assert (
        siteconfig.grid_attr_string({"preset": "cols4"})
        == 'data-sf-cols="2/3/4" data-sf-tail="trim"'
    )
    assert 'data-sf-tail="show"' in siteconfig.grid_attr_string({"preset": "cols4", "tail": "show"})


def test_grid_attr_string_overrides_and_validation():
    # хардкоженные сетки задают триплет сами; мусор → расчёт из раскладки
    assert 'data-sf-cols="1/2/3"' in siteconfig.grid_attr_string({"preset": "cols4"}, cols="1/2/3")
    assert 'data-sf-cols="2/3/4"' in siteconfig.grid_attr_string({"preset": "cols4"}, cols="9/x")
    # листинги принудительно fill — контент прятать нельзя
    assert 'data-sf-tail="fill"' in siteconfig.grid_attr_string({"tail": "show"}, tail="fill")
    assert 'data-sf-tail="trim"' in siteconfig.grid_attr_string({"tail": "show"}, tail="trim")


def test_grid_attr_string_empty_for_scroll_and_balance():
    # DS-5: своя механика (лента / центрирование) — атрибутов «полных рядов» нет;
    # DL-16.1: лента несёт маркер слайдера-примитива (стрелки/точки), balance — ничего.
    assert siteconfig.grid_attr_string({"scroll": True}) == 'data-sf-slider="1"'
    assert siteconfig.grid_attr_string({"balance": True}) == ""


def test_grid_attrs_tag():
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True}]})
    html = Template("{% load siteui %}<div {% grid_attrs site 'products' %}></div>").render(
        Context({"site": cfg})
    )
    assert html == '<div data-sf-cols="2/3/4" data-sf-tail="trim"></div>'
    html = Template(
        "{% load siteui %}<div {% grid_attrs site 'categories' cols='1/2/3' %}></div>"
    ).render(Context({"site": cfg}))
    assert 'data-sf-cols="1/2/3"' in html


# --- CSS: блок в app.css = вывод генератора ---------------------------------------


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_fill_rows_css", ROOT / "scripts" / "gen_fill_rows_css.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_app_css_fill_rows_block_is_fresh():
    gen = _load_generator()
    src = (ROOT / "static" / "src" / "app.css").read_text(encoding="utf-8")
    assert gen.START in src and gen.END in src, "блок DL-11 отсутствует в app.css"
    block = src[src.index(gen.START) : src.index(gen.END) + len(gen.END)] + "\n"
    assert block == gen.generate(), (
        "app.css отстал от генератора — python scripts/gen_fill_rows_css.py"
    )


def test_generated_css_covers_every_breakpoint_and_width():
    gen = _load_generator()
    css = gen.generate()
    # trim: на каждом окне для каждого N ∈ 2..6 — правило первого элемента неполного ряда
    for n in range(2, 7):
        assert f'[data-sf-cols^="{n}/"][data-sf-tail="trim"]' in css  # телефон
        assert f'[data-sf-cols*="/{n}/"][data-sf-tail="trim"]' in css  # планшет
        assert f'[data-sf-cols$="/{n}"]:not([data-density])[data-sf-tail="trim"]' in css  # десктоп
        assert f'[data-grid][data-density="{n}"][data-sf-tail="trim"]' in css  # KAT-4
        # fill: плитка-подсказка растягивается на остаток ряда и прячется при полном ряде
        assert f".sf-filler:nth-child({n}n+1) {{ display: none; }}" in css
        if n > 2:
            assert f".sf-filler:nth-child({n}n+2) {{ grid-column: span {n - 1}; }}" in css
    # единственный неполный ряд (элементов меньше колонок) остаётся виден
    assert ":not(:first-child)" in css
    # посетительский «список» (<768) — хвост не режем, подсказку прячем
    assert ":not(.is-list)" in css and "[data-grid].is-list > .sf-filler { display: none; }" in css


# --- рендер главной: атрибуты стоят у сеток-превью ---------------------------------


def _home(tenant):
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def test_home_grids_carry_fill_rows_attrs():
    tenant = TenantFactory(schema_name="fillrows")
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": True}, {"key": "products", "enabled": True}]}
    )
    tenant.save()
    for i in range(5):
        Category.objects.create(name={"de": f"Kat {i}"}, slug=f"kat-{i}", is_active=True)
    html = _home(tenant)
    grids = re.findall(r'data-grid="categories"[^>]*', html)
    assert grids, html[:400]
    assert any('data-sf-cols="2/3/4" data-sf-tail="trim"' in g for g in grids)


def test_home_grid_tail_show_from_config():
    tenant = TenantFactory(schema_name="fillrows2")
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": True, "layout": {"tail": "show"}}]}
    )
    tenant.save()
    Category.objects.create(name={"de": "Kat"}, slug="kat", is_active=True)
    html = _home(tenant)
    assert 'data-grid="categories"' in html
    assert re.search(r'data-grid="categories"[^>]*data-sf-tail="show"', html)


# --- Studio: селект «Reihen» round-trip ---------------------------------------------


def _builder_request(data, tenant):
    from types import SimpleNamespace  # noqa: PLC0415

    from django.contrib.messages.middleware import MessageMiddleware  # noqa: PLC0415
    from django.contrib.sessions.middleware import SessionMiddleware  # noqa: PLC0415

    req = RequestFactory().post("/dashboard/site/home/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def test_builder_save_writes_tail_presence_minimal(settings):
    """Save билдера: пусто → ключа нет (golden цел); "show" → пишется; мусор → нет."""
    from apps.core import views  # noqa: PLC0415

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug="fr3", name="FR3", site_config={})
    base = {"order_products": "1", "enabled_products": "on", "layout_preset_products": "cols4"}
    for sent, expect in (("", None), ("show", "show"), ("garbage", None)):
        resp = views.home_builder_view(_builder_request({**base, "tail_products": sent}, tenant))
        assert resp.status_code == 302
        tenant.refresh_from_db()
        lay = siteconfig.section_layout(siteconfig.normalize(tenant.site_config), "products")
        assert lay.get("tail") == expect, (sent, lay)


# --- демо-киты: ряды плиток полные на десктопе у всех китов -------------------------


def test_demo_kits_rows_full_on_desktop():
    """DL-11 (владелец: «делать 4 или 8, но по типу вывода»): у КАЖДОГО кита число
    элементов каждой секции-превью кратно колонкам десктопа (или меньше одного
    ряда) — на витрине-образце trim ничего не прячет. Планшет допускает остаток
    (обрезка там — платформенное правило, не дефект данных)."""
    spec = importlib.util.spec_from_file_location(
        "demo_rows_audit", ROOT / "scripts" / "demo_rows_audit.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from apps.tenants import demo_kits  # noqa: PLC0415

    kits = demo_kits.KITS if hasattr(demo_kits, "KITS") else demo_kits.DEMO_KITS
    bad = []
    for key, kit in kits.items():
        for row in mod.audit(kit):
            if row["rem"]["lg"]:
                bad.append((key, row["section"], row["grid_n"], row["cols"]))
    assert not bad, bad


# --- ось сборки section_layouts: пресет побеждает материализованные cols -------------


def test_bundle_section_layouts_axis_applies_preset_over_normalized_layout():
    from apps.tenants import sitetemplates  # noqa: PLC0415

    cfg = siteconfig.normalize({"sections": [{"key": "categories", "enabled": True}]})
    assert siteconfig.section_layout(cfg, "categories")["cols"] == 4  # дефолт
    out = sitetemplates.apply_preview_bundle(cfg, "deal_frisch")
    lay = siteconfig.normalize_layout(siteconfig.section_layout(out, "categories"))
    assert lay["preset"] == "cols3" and lay["cols"] == 3, lay
    assert siteconfig.grid_cols_triplet(lay) == (2, 2, 3)
