"""LAY-3a — ось вывода ДЕЙСТВУЕТ на каждой поверхности листинга.

Разведка волны LAY нашла класс «обещание без исполнения» (правило STU-9):
у `/termin/`, `/unterkunft/`, `/veranstaltung/` ключ раскладки в конфиге ЕСТЬ и
Studio показывает контролы «Verteilen / Volle Reihen», но шаблоны эмитят только
классы Tailwind (`grid_class_string`) и ни одного `data-sf-*`. Значит хвост
неполного ряда и авто-колонки (DL-11/DL-14/DL-15) там мертвы: владелец крутит
настройку, а на витрине не меняется ничего.

То же у секции главной `archetypes`: ключ `sections[archetypes].layout` есть,
атрибутов нет.

Замки написаны ДО правок и краснеют на текущем коде. План —
`docs/lay-unified-output-plan-2026-09-09.md §10`.
"""

import re

import pytest

pytestmark = pytest.mark.django_db

# Поверхность → шаблон, который обязан эмитить атрибуты сетки.
LISTING_TEMPLATES = {
    "services": "templates/storefront/service_index.html",
    "stays": "templates/storefront/stay_index.html",
    "events": "templates/storefront/event_index.html",
    "archetypes": "templates/storefront/sections/_archetypes.html",
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("surface,path", sorted(LISTING_TEMPLATES.items()))
def test_listing_emits_grid_attributes(surface, path):
    """Сетка поверхности несёт data-sf-* — иначе tail/авто-колонки не работают."""
    body = _read(path)
    assert re.search(r"(sf_grid_attrs|grid_attrs)\b", body), (
        f"{surface}: шаблон не эмитит атрибуты сетки — контрол хвоста ничего не делает"
    )


@pytest.mark.parametrize("surface,path", sorted(LISTING_TEMPLATES.items()))
def test_listing_still_emits_grid_classes(surface, path):
    """Паритет: классы Tailwind остаются — вид без новых ключей прежний."""
    body = _read(path)
    assert (
        re.search(r"(grid_class_string|grid_classes|sf_grid_classes)", body) or "grid-cols" in body
    )


def test_every_page_layout_key_has_a_surface_that_reads_it():
    """Инвариант волны: ключ раскладки существует ⇒ его кто-то ЧИТАЕТ в разметке.

    Обратная сторона правила STU-9: настройка без исполнения — это ложь интерфейса.
    """
    from apps.tenants import siteconfig

    assert set(siteconfig._PAGE_LAYOUT_KEYS) == {
        "catalog_layout",
        "events_index_layout",
        "stay_index_layout",
        "service_index_layout",
    }
