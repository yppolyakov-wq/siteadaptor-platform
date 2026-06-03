"""Тесты формы акции (наличие полей цены/скидки/витрины)."""

from apps.promotions.forms import PromotionForm


def test_promotion_form_exposes_pricing_and_display_fields():
    fields = PromotionForm().fields
    for name in (
        "compare_at_price",
        "discount_percent",
        "price_override",
        "strikethrough_old_price",
        "show_countdown",
    ):
        assert name in fields
