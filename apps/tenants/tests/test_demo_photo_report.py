"""F-14 (план `docs/online-shop-demo-plan-2026-09-03.md`): обход демо-фото обязан
видеть ВСЕ поверхности, куда кит кладёт кадры.

Отчёт `demo_photo_report` — единственный измеритель покрытия: ключ, которого он не
видит, молча остаётся на плейсхолдере, и «100 %» врёт. До этой правки обход знал
товары/герои/галерею/номера/события/туры/блог/обложки, но НЕ знал фото вариантов,
комплектов, подборок и акций — а именно ими живёт магазин (M4-A, MEN-6, M4-B).

Замок держит и второй, уже случавшийся класс: обход падал на нестандартной форме
спеки (4-й элемент категории строкой — DS-2). Поэтому здесь же — проход по ВСЕМ
китам реестра."""

import pytest

from apps.tenants import demo_kits
from apps.tenants.management.commands.demo_photo_report import kit_keywords


def _kit(**kw):
    # hero_image_kw пустой: `add` пропускает пустые строки, поэтому в выдаче
    # остаются ТОЛЬКО ключи проверяемой поверхности.
    return demo_kits.DemoKit(
        key="probe",
        label="Probe",
        subdomain="probe",
        business_type="online_shop",
        accent="#26303f",
        hero_image_kw="",
        hero_title="",
        hero_text="",
        **kw,
    )


def _keys(kit):
    return [k for k, _where in kit_keywords(kit)]


def test_variant_photos_are_counted():
    """M4-A: фото варианта подменяет главный кадр при выборе цвета — оно такое же
    «настоящее» фото витрины, как кадр товара."""
    kit = _kit(
        categories=[
            (
                "Mode",
                "mode",
                [
                    {
                        "name": "Shirt",
                        "price": "39.00",
                        "img": "shirt-basis",
                        "variants": [
                            {"size": "M", "color": "Sand", "images": ["shirt-basis-sand"]},
                            {"size": "L", "color": "Petrol", "images": ["shirt-basis-petrol"]},
                        ],
                    }
                ],
            )
        ]
    )
    keys = _keys(kit)
    assert "shirt-basis-sand" in keys
    assert "shirt-basis-petrol" in keys


def test_variant_tuple_shape_does_not_break_the_walk():
    """Вариант может быть кортежем (label, price) — у него фото нет, и обход
    обязан пройти мимо, а не упасть."""
    kit = _kit(
        categories=[
            ("Mode", "mode", [{"name": "Shirt", "price": "39.00", "variants": [("M", "39.00")]}])
        ]
    )
    assert _keys(kit) == []


def test_combo_photos_are_counted():
    kit = _kit(combos=[{"name": "Set", "price": "59.00", "photos": ["set-abend-tisch"]}])
    assert "set-abend-tisch" in _keys(kit)


def test_collection_photos_are_counted():
    """M4-B Lookbook: кадр образа — обложка страницы /lookbook/<slug>/."""
    kit = _kit(collections=[("Neu im Herbst", {"products": [0], "photos": ["look-herbst"]})])
    assert "look-herbst" in _keys(kit)


def test_promotion_photos_are_counted_in_both_shapes():
    """Спека акции несёт либо один `image`, либо галерею `images` (2026-07-29)."""
    kit = _kit(
        promotions_spec=[
            {"title": "Einzel", "image": "aktion-einzel"},
            {"title": "Galerie", "images": ["aktion-a", "aktion-b"]},
        ]
    )
    keys = _keys(kit)
    assert {"aktion-einzel", "aktion-a", "aktion-b"} <= set(keys)


@pytest.mark.parametrize("key", sorted(demo_kits.KITS))
def test_every_kit_walks_without_error(key):
    """Форма спеки у китов разная — обход не имеет права падать ни на одном."""
    pairs = kit_keywords(demo_kits.KITS[key])
    assert all(isinstance(kw, str) and kw.strip() for kw, _w in pairs)
