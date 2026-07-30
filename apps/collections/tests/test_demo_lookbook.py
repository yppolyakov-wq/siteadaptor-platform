"""M4-B: демо-кит бутика получает лукбук-подборки (страница /lookbook/<slug>/)."""

import pytest

pytestmark = pytest.mark.django_db


def test_clothing_kit_declares_lookbook():
    from apps.tenants.demo_kits import KITS

    kit = KITS["clothing"]
    named = dict(kit.collections)
    assert "Herbst-Looks" in named
    assert named["Herbst-Looks"]["photos"], "у лука должны быть фото — иначе нет страницы"
    assert named["Herbst-Looks"]["products"]
    assert not named["Basics"].get("photos")  # обычный фасет-чип без страницы
