"""STU-12j (F9): форма карточки для ОДНОЙ категории.

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12j). Дизайн-ревью волны
поймало неточность макета: пилюля «Nur hier» на странице категории обещала выбор формы
карточки только для этой категории, а поля для такого выбора не существовало — категория
могла лишь наследовать дефолт сайта.

Три слоя резолвера: своя форма товара → форма его категории (на странице категории —
категория страницы) → дефолт сайта. Мусор в любом слое проваливается в следующий, а не
роняет страницу.
"""

import pytest

from apps.catalog.models import Category, Product
from apps.core import card_forms, studio_pages
from apps.tenants.tests.factories import TenantFactory  # noqa: F401  (фикстура схемы)

pytestmark = pytest.mark.django_db


def _cat(**kw):
    return Category.objects.create(name="Probe", slug=kw.pop("slug", "probe"), **kw)


def test_category_carries_its_own_card_form():
    cat = _cat(card_style="deal")
    assert cat.card_style == "deal"


def test_resolver_prefers_product_then_category_then_site():
    cat = _cat(slug="c1", card_style="deal")
    p = Product(name="P", base_price=1, category=cat, card_style="lookbook")
    assert card_forms.card_form(p, "regal") == "lookbook", "своё у товара сильнее всех"
    p.card_style = ""
    assert card_forms.card_form(p, "regal") == "deal", "затем — форма его категории"
    cat.card_style = ""
    assert card_forms.card_form(p, "regal") == "regal", "затем — дефолт сайта"


def test_garbage_falls_through_instead_of_breaking():
    cat = _cat(slug="c2", card_style="nonsense")
    p = Product(name="P", base_price=1, category=cat, card_style="ерунда")
    assert card_forms.card_form(p, "regal") == "regal"
    assert card_forms.card_form(p, "тоже мусор") == ""


def test_registry_binds_the_setting_by_page_type():
    """На странице товара пилюля пишет товар, на странице категории — категорию."""
    setting = studio_pages.SETTINGS["product_card_form"]  # реестр — словарь по коду
    assert setting.object_for("product") == (studio_pages.OBJECT_PRODUCT, "card_style")
    assert setting.object_for("category") == (studio_pages.OBJECT_CATEGORY, "card_style")
    assert setting.object_for("home") == ("", ""), "на главной объекта нет — только сайт"


def test_scope_writes_the_object_of_the_open_page_type():
    """Пилюля «Nur hier» на категории пишет КАТЕГОРИЮ, а на товаре — товар (STU-9/W6)."""
    from apps.core import studio_scope

    tenant = TenantFactory(
        slug="stcc1", name="StCc1", site_config={"site_defaults": {"card_style": "regal"}}
    )
    cat = _cat(slug="accessoires")
    p = Product.objects.create(name="P", base_price=1, category=cat, slug="p-1")

    studio_scope.write_value(tenant, "product_card_form", "accessoires", "deal", "category")
    cat.refresh_from_db()
    p.refresh_from_db()
    assert cat.card_style == "deal"
    assert p.card_style == "", "товар не тронут"
    tenant.refresh_from_db()
    assert tenant.site_config["site_defaults"]["card_style"] == "regal", "сайт не тронут"

    studio_scope.write_value(tenant, "product_card_form", "p-1", "lookbook", "product")
    p.refresh_from_db()
    cat.refresh_from_db()
    assert p.card_style == "lookbook" and cat.card_style == "deal"


def test_scope_without_page_keeps_the_legacy_path():
    """Старый клиент (без `page`) обязан работать как раньше — писать товар."""
    from apps.core import studio_scope

    tenant = TenantFactory(slug="stcc2", name="StCc2")
    p = Product.objects.create(name="P2", base_price=1, slug="p-2")
    studio_scope.write_value(tenant, "product_card_form", "p-2", "regal")
    p.refresh_from_db()
    assert p.card_style == "regal"
