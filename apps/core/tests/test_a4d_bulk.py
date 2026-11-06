# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-4d: «alle Kuchen 10 % teurer / скрой все товары категории Торты» (план §13).

Замки: детектор на пяти языках без ИИ, только со словом «все» и существующей категорией;
категория разворачивается сервером (она + прямые подкатегории) в обычные пункты цены/
видимости ≤ 50; формула цены — общая с экраном «Sortiment» (WR-6); без направления у
процента — не угадываем; товар с вариантами пропускается; >50 — без кнопки; откат — пакетом.
"""

from decimal import Decimal

import pytest

from apps.catalog import bulk_price, writers
from apps.catalog.models import Product
from apps.core import assistant_bulk, assistant_changes
from apps.core.models import AssistantTurn
from apps.core.tests.test_a4_actions import _apply, _html, _undo
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _ask,
    _clean,
    _req,
    _urlconf,
    _user,
    bakery,
    isolated_ratelimit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


@pytest.fixture
def kuchen(bakery):
    cat = writers.create_category(bakery, {"name_de": "Kuchen"})
    sub = writers.create_category(bakery, {"name_de": "Torten", "parent": str(cat.pk)})
    a = writers.create_product(
        bakery, {"name_de": "Apfelkuchen", "base_price": "3,00", "category": str(cat.pk)}
    )
    b = writers.create_product(
        bakery, {"name_de": "Sachertorte", "base_price": "4,50", "category": str(sub.pk)}
    )
    writers.create_product(bakery, {"name_de": "Brot", "base_price": "2,00"})
    return cat, a, b


def _prices():
    return {p.get_i18n("name"): p.base_price for p in Product.objects.all()}


def _take_all(n):
    return {"items_present": "1", **{f"take_{i}": "1" for i in range(n)}}


@pytest.mark.parametrize(
    "phrase",
    [
        "alle Kuchen 10 % teurer",
        "Preise aller Produkte in Kuchen um 10 % erhöhen",
        "make all products in Kuchen 10 % more, increase",
        "все товары категории Kuchen подними на 10 %",
        "усі товари Kuchen підвищ на 10 %",
        "Kuchen tüm ürünler %10 artır",
    ],
)
def test_percent_in_five_languages(ai_off, bakery, kuchen, phrase):
    assert assistant_bulk.intent(bakery, _user(), phrase)
    user, got = _ask(bakery, phrase)
    _apply(bakery, user, got["job"], _take_all(2))
    prices = _prices()
    assert prices["Apfelkuchen"] == Decimal("3.30")
    assert prices["Sachertorte"] == Decimal("4.95")  # прямая подкатегория — тоже
    assert prices["Brot"] == Decimal("2.00")  # чужая категория не тронута


def test_same_math_as_sortiment_screen():
    """Одна формула с массовой правкой экрана (WR-6): процент, сумма, «= X», не ниже нуля."""
    assert bulk_price.new_price(Decimal("3.33"), "pct", Decimal("10")) == Decimal("3.66")
    assert bulk_price.new_price(Decimal("1.00"), "eur", Decimal("-2")) == Decimal("0.00")
    assert bulk_price.new_price(Decimal("9.99"), "set", Decimal("5")) == Decimal("5.00")
    assert not bulk_price.valid("pct", Decimal("-95"))
    assert not bulk_price.valid("eur", Decimal("1e30"))


def test_euro_down_and_set(ai_off, bakery, kuchen):
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen 0,50 € billiger")
    assert {it["values"]["price"] for it in items} == {"2,50", "4,00"}
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen auf 5 €")
    assert {it["values"]["price"] for it in items} == {"5,00"}


def test_percent_without_direction_is_not_guessed(ai_off, bakery, kuchen):
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen 10 %")
    assert len(items) == 1 and items[0]["blocked"]
    user, got = _ask(bakery, "alle Kuchen 10 %")
    assert "data-assistant-apply-btn" not in _html(bakery, user, got["job"])


def test_without_all_is_not_bulk(ai_off, bakery, kuchen):
    """«blende Kuchen aus» — сама категория (A-4b), а не все её товары."""
    assert not assistant_bulk.intent(bakery, _user(), "blende Kuchen aus")
    assert assistant_changes.intent(bakery, _user(), "blende Kuchen aus")


def test_hide_all_products_then_undo(ai_off, bakery, kuchen):
    cat, a, b = kuchen
    user, got = _ask(bakery, "blende alle Produkte in Kuchen aus")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-bulk-rows" in html and "Apfelkuchen" in html
    _apply(bakery, user, got["job"], _take_all(2))
    assert not Product.objects.filter(pk__in=[a.pk, b.pk], is_active=True).exists()
    cat.refresh_from_db()
    assert cat.is_active  # категория не скрыта — скрыты её товары
    _undo(bakery, user, got["job"])
    assert Product.objects.filter(pk__in=[a.pk, b.pk], is_active=True).count() == 2


def test_unchecked_row_is_not_applied(ai_off, bakery, kuchen):
    user, got = _ask(bakery, "скрой все товары категории Kuchen")
    _apply(bakery, user, got["job"], {"items_present": "1", "take_0": "1"})
    assert Product.objects.filter(is_active=False).count() == 1


def test_variant_product_is_skipped(ai_off, bakery, kuchen):
    from apps.catalog.models import ProductVariant

    _cat, a, _b = kuchen
    ProductVariant.objects.create(product=a, label="groß", price=Decimal("5"))
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen 10 % teurer")
    assert [it["values"]["name"] for it in items] == ["Sachertorte"]
    assert "Varianten" in " ".join(assistant_bulk.meta(items)["skipped"])


def test_more_than_fifty_has_no_button(ai_off, bakery, kuchen):
    cat, _a, _b = kuchen
    for i in range(assistant_bulk.BULK_MAX):
        writers.create_product(
            bakery, {"name_de": f"Kuchen Nr {i}", "base_price": "1", "category": str(cat.pk)}
        )
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    html = _html(bakery, user, got["job"])
    assert "52" in html and "data-assistant-apply-btn" not in html
    _apply(bakery, user, got["job"], _take_all(1))
    assert Product.objects.get(pk=_a.pk).base_price == Decimal("3.00")


def test_price_needs_preise_edit(ai_off, bakery, kuchen, monkeypatch):
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, perm: perm != "preise.edit" and real(user, perm)
    )
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-apply-btn" not in html and "3,00" not in html
    _apply(bakery, user, got["job"], _take_all(2))
    assert _prices()["Apfelkuchen"] == Decimal("3.00")


def test_no_view_right_no_detection(ai_off, bakery, kuchen, monkeypatch):
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, perm: perm != "sortiment.view" and real(user, perm)
    )
    assert not assistant_bulk.intent(bakery, _user(), "alle Kuchen 10 % teurer")


def test_question_is_not_a_change(ai_off, bakery, kuchen):
    assert not assistant_bulk.intent(bakery, _user(), "Wie mache ich alle Kuchen 10 % teurer?")


def test_history_keeps_one_summary_row(ai_off, bakery, kuchen):
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    turn = AssistantTurn.objects.get(job=got["job"])
    assert len(turn.entry["summary"]) == 1 and "Kuchen" in turn.entry["summary"][0]["name"]


def test_decrease_warns_once(ai_off, bakery, kuchen):
    user, got = _ask(bakery, "alle Kuchen 10 % günstiger")
    assert _html(bakery, user, got["job"]).count("data-assistant-pangv") == 1


def test_changed_after_preview_is_refused(ai_off, bakery, kuchen):
    """Всё или ничего: одну цену поменяли в форме после предпросмотра — пакет не проходит."""
    _cat, a, _b = kuchen
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    Product.objects.filter(pk=a.pk).update(base_price=Decimal("9.00"))
    _apply(bakery, user, got["job"], _take_all(2))
    assert _prices()["Sachertorte"] == Decimal("4.50")


def test_show_as_list_is_a_page_setting_not_bulk(ai_off, bakery, kuchen):
    """«покажи все товары Kuchen 4 в ряд» — вид страницы (A-4c), а не «включить все товары»."""
    from apps.core import assistant_pages

    phrase = "покажи все товары Kuchen 4 в ряд"
    assert assistant_pages.intent(bakery, _user(), phrase)
    assert not assistant_bulk.intent(bakery, _user(), phrase)
    assert assistant_bulk.intent(bakery, _user(), "покажи снова все товары Kuchen")


def test_error_after_change_is_shown_in_the_row(ai_off, bakery, kuchen):
    _cat, a, _b = kuchen
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    Product.objects.filter(pk=a.pk).update(base_price=Decimal("9.00"))
    _apply(bakery, user, got["job"], _take_all(2))
    html = _html(bakery, user, got["job"])
    assert "data-assistant-bulk-error" in html and 'role="alert"' in html


def test_posted_price_is_ignored(ai_off, bakery, kuchen):
    """Цену массового пункта посчитал сервер: подменённое поле POST не записывается."""
    user, got = _ask(bakery, "alle Kuchen 10 % teurer")
    _apply(bakery, user, got["job"], {**_take_all(2), "f_0_price": "0,01", "f_1_price": "0,01"})
    assert set(_prices().values()) == {Decimal("3.30"), Decimal("4.95"), Decimal("2.00")}


@pytest.mark.parametrize(
    ("phrase", "mode", "value"),
    [
        ("alle Kuchen auf 1.250 €", "set", Decimal("1250")),
        ("alle Kuchen- 10 % erhöhen", "pct", Decimal("10")),
        ("Kuchen tüm ürünler %10 artır", "pct", Decimal("10")),
    ],
)
def test_amount_parsing(phrase, mode, value):
    assert assistant_bulk.price_change(phrase)[:2] == (mode, value)


@pytest.mark.parametrize(
    "phrase",
    [
        "alle Kuchen +10 % billiger",  # знак и слово спорят
        "все товары Kuchen на 2 €",  # «на» без направления
        "tüm Kuchen zaman %10",  # «zaman» — не «zam»
    ],
)
def test_ambiguous_direction_is_asked(phrase):
    mode, _value, reason = assistant_bulk.price_change(phrase)
    assert not mode and reason


def test_hide_with_price_filter_is_not_ours(ai_off, bakery, kuchen):
    assert not assistant_bulk.intent(bakery, _user(), "blende alle Kuchen unter 2 € aus")


def test_plain_show_all_is_viewing_not_enabling(ai_off, bakery, kuchen):
    assert not assistant_bulk.intent(bakery, _user(), "покажи все товары категории Kuchen")


def test_deleted_subcategory_is_left_alone(ai_off, bakery, kuchen):
    from apps.catalog.models import Category

    Category.objects.filter(name__de="Torten").update(deleted_at="2026-01-01T00:00:00Z")
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen 10 % teurer")
    assert [it["values"]["name"] for it in items] == ["Apfelkuchen"]


def test_never_silently_free(ai_off, bakery, kuchen):
    items = assistant_bulk.build(bakery, _user(), "alle Kuchen 3 € billiger")
    assert [it["values"]["name"] for it in items] == ["Sachertorte"]
    assert "0 €" in " ".join(assistant_bulk.meta(items)["skipped"])
