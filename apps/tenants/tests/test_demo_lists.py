"""LB-4d-3: у демо-кита ни один список не обещает пустую витрину.

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §12.3. Список главной
(«Unsere Zimmer», «Aktionen», «Neu im Sortiment» …) и блок «Liste» любой страницы —
выборка по данным: опечатка в фильтре, источник без модуля или подборка, под которую
кит не засеял ни одной позиции, не падают — они молча рисуют пустое место (а витрина
секцию без карточек просто прячет, и дыру никто не видит). Замок засевает каждый кит и
спрашивает выборку тем же движком, что рисует витрину.
"""

import pytest

from apps.core import list_blocks
from apps.tenants import demo_kits, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _list_rows(cfg):
    """(место, данные блока) — встроенные списки главной и блоки «Liste» всех страниц."""
    out = []
    for row in cfg.get("sections") or []:
        if not row.get("enabled"):
            continue
        key = row.get("key")
        if key in siteconfig.BUILTIN_LIST_SOURCES:
            out.append((f"home:{key}", list_blocks.section_data(row), row))
        elif siteconfig.cblock_type(key) == "list":
            out.append((f"home:{row.get('id')}", row.get("data") or {}, None))
    for host, blocks in (cfg.get("page_blocks") or {}).items():
        for block in blocks or []:
            if siteconfig.is_main_marker(block) or not block.get("enabled", True):
                continue
            if siteconfig.cblock_type(block.get("key")) == "list":
                out.append((f"{host}:{block.get('id')}", block.get("data") or {}, None))
    return out


@pytest.mark.parametrize("key", sorted(demo_kits.KITS))
def test_every_list_of_the_kit_shows_something(key):
    tenant = TenantFactory(slug=f"lists-{key}", name="Lists")
    assert demo_kits.apply_kit(tenant, key) is True
    cfg = siteconfig.normalize(tenant.site_config)
    empty = []
    for place, data, row in _list_rows(cfg):
        source = list_blocks._source(data)
        if not tenant.is_module_active(list_blocks.SOURCE_MODULES[source]):
            empty.append(f"{place} (модуль {source} выключен)")
            continue
        if row is not None:
            shown = list_blocks.resolve_section(cfg, row)["items"]
        else:
            shown = list_blocks.resolve(cfg, data, tenant)["items"]
        if not shown:
            empty.append(f"{place} {data}")
    assert not empty, f"{key}: пустые списки — {empty}"


@pytest.mark.parametrize("key", sorted(k for k, kit in demo_kits.KITS.items() if kit.section_data))
def test_kit_section_data_survives_normalize(key):
    """Ось «ЧТО» кита, которую normalize выбросил бы, молча не действует — секция
    «Neu im Sortiment» показывала бы избранное, а не новинки."""
    kit = demo_kits.KITS[key]
    rows = {
        r["key"]: r
        for r in siteconfig.normalize({"sections": demo_kits._kit_sections(kit)})["sections"]
    }
    for section, what in kit.section_data.items():
        assert rows[section].get("data") == what, (key, section)
