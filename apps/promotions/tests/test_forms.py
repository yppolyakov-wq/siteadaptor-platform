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


def test_group_translation_fields_appear_per_extra_locale_and_save_overlay(db):
    """Метка группы редактируема, поэтому у неё есть per-locale ввод: базовая
    локаль — поле `group`, прочие — динамические `group_<loc>` → `group_i18n`."""
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="pgf", enabled_locales=["de", "en"])
    assert "group_en" in PromotionForm(tenant=tenant).fields
    assert "group_de" not in PromotionForm(tenant=tenant).fields  # база — само поле `group`

    form = PromotionForm(
        {
            "title_de": "Deal",
            "title_en": "Deal",
            "promo_type": "discount",
            "max_per_customer": 1,
            "reservation_ttl_hours": 24,
            "group": "Wochenangebote",
            "group_en": "Weekly offers",
        },
        tenant=tenant,
    )
    assert form.is_valid(), form.errors
    promo = form.save(commit=False)
    assert promo.group == "Wochenangebote"
    assert promo.group_i18n == {"en": "Weekly offers"}


def test_blank_group_translation_clears_overlay(db):
    from apps.promotions.models import Promotion
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="pgf2", enabled_locales=["de", "en"])
    promo = Promotion(title={"de": "x"}, group="Wochenangebote", group_i18n={"en": "Weekly"})
    form = PromotionForm(
        {
            "title_de": "x",
            "promo_type": "discount",
            "max_per_customer": 1,
            "reservation_ttl_hours": 24,
            "group": "Wochenangebote",
            "group_en": "",
        },
        instance=promo,
        tenant=tenant,
    )
    assert form.is_valid(), form.errors
    assert form.save(commit=False).group_i18n == {}  # пусто → фолбэк на базовую метку
