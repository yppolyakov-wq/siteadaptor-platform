"""Аудит переводов демо 2026-08-13: замки НОВЫХ путей перевода демо-контента.

Класс дефектов, который эти тесты закрывают, в проекте уже случался трижды
(акции в HF-волне, полоса преимуществ/роли команды в аудите 2026-08-06,
параметры товара в I18N-10): перевод ЛЕЖИТ в словаре, но не доезжает до витрины,
потому что обход о нём не знает. Здесь проверяется именно ДОСТАВКА:

  * C-блоки главной (`sections`) и страниц (`page_blocks`) получают оверлей,
    причём переводятся только текстовые поля данных — служебные токены целы;
  * оверлей строится по НОРМАЛИЗОВАННОМУ списку (позиционный merge не должен
    промахнуться мимо блока, если normalize дописал фикс-секции в конец);
  * описание направления категории (лендинг `/bereich/<slug>/`) переводится;
  * виды мероприятия формы заявки переводятся ТОЛЬКО в показе — value <option>
    остаётся немецким, иначе POST не прошёл бы fail-closed валидацию вьюхи.
"""

from __future__ import annotations

import pytest

from apps.tenants import demo_i18n, siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_map(monkeypatch):
    """Подменить словари демо на предсказуемый набор (тест не зависит от наполнения)."""
    words = {
        "Events pro Jahr": "Событий в год",
        "Unsere Geschichte": "Наша история",
        "Zwei Sätze über den Betrieb.": "Два предложения о заведении.",
        "Hochzeit": "Свадьба",
        "Firmenfeier": "Корпоратив",
        "Fingerfood für Ihre Feier.": "Фингерфуд для вашего праздника.",
    }
    monkeypatch.setattr(demo_i18n, "_MAPS", {"ru": words})
    return words


def test_cblock_overlay_translates_text_but_not_service_tokens(fake_map):
    cfg = {
        "sections": [
            {"key": "products", "enabled": True},
            {
                "key": "stats",
                "id": "demo-block-1",
                "enabled": True,
                "data": {"rows": [{"value": "200+", "label": "Events pro Jahr"}]},
            },
        ]
    }
    demo_i18n.overlay_config(cfg, ["ru"])
    ov = cfg["i18n"]["ru"]["sections"]

    # Индекс блока в оверлее = индекс в НОРМАЛИЗОВАННОМ списке.
    norm = siteconfig.normalize_sections(cfg["sections"])
    idx = next(i for i, s in enumerate(norm) if s.get("key") == "stats")
    assert ov[idx]["data"]["rows"][0]["label"] == "Событий в год"
    # Число под подписью — не текст: перевод его не трогает.
    assert "value" not in ov[idx]["data"]["rows"][0]
    # Служебные поля блока (ключ/enabled/id) в оверлей не попадают.
    assert set(ov[idx]) == {"data"}
    # Секция без переводимых данных остаётся no-op ({} мерджится в ничто).
    assert ov[0] == {}


def test_cblock_overlay_lands_on_the_right_block_after_normalize(fake_map):
    """normalize дописывает недостающие фикс-секции В КОНЕЦ — оверлей обязан
    считать индексы по нормализованному списку, иначе перевод сядет на чужой блок."""
    cfg = {
        "sections": [
            {
                "key": "text",
                "id": "b1",
                "enabled": True,
                "data": {"title": "Unsere Geschichte", "body": "Zwei Sätze über den Betrieb."},
            }
        ]
    }
    demo_i18n.overlay_config(cfg, ["ru"])
    localized = siteconfig.localize(siteconfig.normalize(cfg), "ru")
    block = next(s for s in localized["sections"] if s.get("id") == "b1")
    assert block["data"]["title"] == "Наша история"
    assert block["data"]["body"] == "Два предложения о заведении."
    # Ни одна другая секция не получила чужой текст.
    others = [s for s in localized["sections"] if s.get("id") != "b1"]
    assert all("Наша история" not in str(s.get("data") or {}) for s in others)


def test_page_blocks_overlay_is_generated_per_host(fake_map):
    cfg = {
        "page_blocks": {
            "info": [
                {
                    "key": "text",
                    "id": "p1",
                    "enabled": True,
                    "data": {"title": "Unsere Geschichte", "body": ""},
                }
            ]
        }
    }
    demo_i18n.overlay_config(cfg, ["ru"])
    localized = siteconfig.localize(siteconfig.normalize(cfg), "ru")
    assert localized["page_blocks"]["info"][0]["data"]["title"] == "Наша история"


def test_anfrage_event_types_are_translated_in_overlay(fake_map):
    cfg = {"anfrage": {"fields": ["event_type"], "event_types": ["Hochzeit", "Firmenfeier"]}}
    demo_i18n.overlay_config(cfg, ["ru"])
    localized = siteconfig.localize(siteconfig.normalize(cfg), "ru")
    assert localized["anfrage"]["event_types"] == ["Свадьба", "Корпоратив"]
    # База (DE) не тронута — по ней вьюха валидирует присланное значение.
    assert siteconfig.normalize(cfg)["anfrage"]["event_types"] == ["Hochzeit", "Firmenfeier"]


def test_anfrage_choices_keep_german_value_and_localized_label(fake_map, rf):
    """Тег отдаёт пары (value, подпись): value — немецкий (ключ записи Job)."""
    from django.template import Context, Template
    from django.utils import translation

    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory()
    tenant.site_config = {"anfrage": {"fields": ["event_type"], "event_types": ["Hochzeit"]}}
    demo_i18n.overlay_config(tenant.site_config, ["ru"])
    request = rf.get("/anfrage/")
    request.tenant = tenant
    tpl = Template("{% load siteui %}{% anfrage_event_choices as c %}{{ c }}")
    with translation.override("ru"):
        out = tpl.render(Context({"request": request}))
    assert "Hochzeit" in out and "Свадьба" in out


def test_category_description_gets_translated(fake_map):
    """Описание направления (DS-7a) — единственный текст лендинга /bereich/<slug>/."""
    from types import SimpleNamespace

    cat = SimpleNamespace(description={"de": "Fingerfood für Ihre Feier."})
    assert demo_i18n._fill_full(cat, "description", ["ru"]) is True
    assert cat.description["ru"] == "Фингерфуд для вашего праздника."


def test_every_overlay_field_is_reachable_by_the_seeder():
    """Замок класса дефектов «поле есть, а обход его не заполняет» (I18N-12).

    Стенд поймал это дважды за одну волну: `BusinessReview.comment_i18n` (SHARED —
    не попадал в цикл по TENANT-моделям) и `Tenant.opening_hours_i18n`. Тест
    проверяет намерение статически: у каждой модели проекта, где ЕСТЬ пара
    «плоское поле + `<поле>_i18n`», имя этого оверлея должно упоминаться в
    `apps/tenants/demo_i18n.py` — либо прямо, либо через кортеж полей цикла.
    Новое поле без обхода = красный тест, а не немецкая витрина в проде.
    """
    import pathlib

    from django.apps import apps as django_apps

    source = pathlib.Path("apps/tenants/demo_i18n.py").read_text(encoding="utf-8")
    unreachable = []
    for model in django_apps.get_models():
        if not model._meta.app_label.startswith(("catalog", "booking", "stays", "events")) and (
            model._meta.app_label
            not in ("core", "loyalty", "reviews", "aggregator", "jobs", "tenants", "promotions", "collections")
        ):
            continue
        names = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}
        for name in sorted(names):
            if not name.endswith("_i18n"):
                continue
            base = name[: -len("_i18n")]
            if base not in names:  # full-JSON поля (Product.name) — другая схема
                continue
            # обход упоминает либо сам оверлей, либо базовое имя в кортеже полей
            if name in source or f'"{base}"' in source:
                continue
            unreachable.append(f"{model._meta.label}.{name}")
    assert not unreachable, (
        "оверлеи не заполняются demo_i18n (перевод ляжет мёртвым грузом): " + ", ".join(unreachable)
    )
