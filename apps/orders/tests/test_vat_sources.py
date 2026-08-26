"""VAT-2/VAT-3: ставка позиции берётся из карточки того, что продали.

Требование владельца 2026-08-26: «рассчитывай налог в зависимости от указанного
налога… если у товара нет настройки налога — нужно добавить в настройках товара
или услуги и выводить именно тот параметр, который там указан».

До волны ставка молча дефолтилась на 19 % у набора, у свободной сборки блюд и у
услуги, выбранной через пикер, — гастро декларировал 19 % вместо 7 % на реальных
продажах.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Combo, Product
from apps.orders import editing
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def speisen():
    return Category.objects.create(name="Speisen")


def test_combo_carries_its_own_rate_into_the_order(speisen):
    """Меню-сет гастро — еда по 7 %, а не дефолтные 19 %."""
    combo = Combo.objects.create(
        name="Menü Klassik",
        price=Decimal("40.00"),
        category=speisen,
        vat_rate=Decimal("7.00"),
    )

    order = create_order(items=[], combos=[(combo, [], 1)], name="Gast")

    assert order.items.get().vat_rate == Decimal("7.00")


def test_free_line_takes_the_rate_it_was_given(speisen):
    """Свободная сборка блюд: ставка приходит от набора, а не дефолтом."""
    order = create_order(
        items=[],
        custom_lines=[("Freie Auswahl", Decimal("30.00"), 1, None, None, [], Decimal("7.00"))],
        name="Gast",
    )

    assert order.items.get().vat_rate == Decimal("7.00")


def test_free_line_without_rate_keeps_the_model_default(speisen):
    """Замок совместимости: строка без ставки ведёт себя как раньше."""
    order = create_order(
        items=[],
        custom_lines=[("Beratung", Decimal("50.00"), 1)],
        name="Gast",
    )

    assert order.items.get().vat_rate == Decimal("19.00")


def test_product_rate_wins_over_a_passed_one(speisen):
    """У строки с товаром ставка всегда его — переданная не может её подменить."""
    product = Product.objects.create(
        category=speisen, name="Brot", base_price=Decimal("3.00"), vat_rate=Decimal("7.00")
    )
    order = create_order(items=[(product, None, 1)], name="Gast")

    editing.add_item(order, product=product, qty=1, vat_rate=Decimal("19.00"))

    assert {i.vat_rate for i in order.items.all()} == {Decimal("7.00")}


def test_added_free_line_can_carry_a_service_rate(speisen):
    """Услуга из пикера едет в заказ со ставкой своей карточки."""
    product = Product.objects.create(
        category=speisen, name="Brot", base_price=Decimal("3.00"), vat_rate=Decimal("7.00")
    )
    order = create_order(items=[(product, None, 1)], name="Gast")

    editing.add_item(
        order,
        qty=1,
        title="Haarschnitt",
        unit_price=Decimal("58.00"),
        vat_rate=Decimal("19.00"),
    )

    added = order.items.get(title_snapshot="Haarschnitt")
    assert added.vat_rate == Decimal("19.00")


def test_mixed_order_splits_the_tax_by_rate(speisen):
    """Смешанный чек: разбивка по ставкам, а не одна усреднённая."""
    from apps.orders.totals import order_totals

    food = Product.objects.create(
        category=speisen, name="Kuchen", base_price=Decimal("10.70"), vat_rate=Decimal("7.00")
    )
    drink = Product.objects.create(
        category=speisen, name="Cocktail", base_price=Decimal("11.90"), vat_rate=Decimal("19.00")
    )

    order = create_order(items=[(food, None, 1), (drink, None, 1)], name="Gast")
    totals = order_totals(order)

    assert [r["rate"] for r in totals["rows"]] == [Decimal("19.00"), Decimal("7.00")]
    assert totals["gross"] == Decimal("22.60")
    # Каждая ставка выделяет свой налог: 11,90 → 1,90 и 10,70 → 0,70.
    assert {r["rate"]: r["vat"] for r in totals["rows"]} == {
        Decimal("19.00"): Decimal("1.90"),
        Decimal("7.00"): Decimal("0.70"),
    }
