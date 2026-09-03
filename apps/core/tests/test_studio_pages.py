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
