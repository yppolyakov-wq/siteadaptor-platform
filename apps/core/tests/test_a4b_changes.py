# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-4b: «измени цену / скрой / перенеси» существующего объекта (план §11).

Замки: детектор на пяти языках без ИИ; фраза создания — не изменение; цена только из
текста и правом `preise.edit`; товар с вариантами — без кнопки; оптимистичная проверка
(значение сменилось после предпросмотра — отказ); направление «скрыть/показать» не из
POST; неоднозначное имя — без кнопки; снижение цены — предупреждение § 11 PAngV;
откат возвращает прежнее значение; из истории пакет не применить.
"""

from decimal import Decimal

import pytest

from apps.catalog import writers
from apps.catalog.models import Category, PriceLog, Product
from apps.core import assistant_changes, assistant_views
from apps.core.models import AssistantChange, AssistantTurn
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
def cake(bakery):
    return writers.create_product(bakery, {"name_de": "Käsekuchen", "base_price": "3,20"})


TAKE = {"items_present": "1", "take_0": "1"}


@pytest.mark.parametrize(
    "phrase",
    [
        "Setze den Preis von Käsekuchen auf 3,50 €",
        "поменяй цену Käsekuchen на 3,50 евро",
        "зміни ціну Käsekuchen на 3,50 євро",
        "change the price of Käsekuchen to 3.50 €",
        "Käsekuchen fiyatı 3,50 € olsun",
    ],
)
def test_price_change_in_five_languages(ai_off, bakery, cake, phrase):
    assert assistant_changes.intent(bakery, None, phrase)
    user, got = _ask(bakery, phrase)
    _apply(bakery, user, got["job"], TAKE)
    cake.refresh_from_db()
    assert cake.base_price == Decimal("3.50")


def test_create_phrase_is_not_a_change(ai_off, bakery, cake):
    assert not assistant_changes.intent(bakery, None, "lege Produkt Käsekuchen 4 € an")
    assert not assistant_changes.intent(bakery, None, "добавь товар Käsekuchen 4 евро")


def test_price_preview_then_undo(ai_off, bakery, cake):
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-before" in html and "3,20 €" in html and "3,50 €" in html
    assert Product.objects.get().base_price == Decimal("3.20")  # до клика ничего
    _apply(bakery, user, got["job"], TAKE)
    assert PriceLog.objects.filter(product=cake, price=Decimal("3.50")).exists()
    _undo(bakery, user, got["job"])
    assert Product.objects.get().base_price == Decimal("3.20")


def test_price_decrease_warns_about_pangv(ai_off, bakery, cake):
    user, got = _ask(bakery, "Preis Käsekuchen auf 2,90 €")
    assert "data-assistant-pangv" in _html(bakery, user, got["job"])


def test_price_needs_preise_edit(ai_off, bakery, cake, monkeypatch):
    from apps.core import permissions

    real = permissions.has_perm
    monkeypatch.setattr(
        permissions, "has_perm", lambda user, perm: perm != "preise.edit" and real(user, perm)
    )
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    assert "data-assistant-apply-btn" not in _html(bakery, user, got["job"])
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get().base_price == Decimal("3.20")


def test_variant_product_has_no_button(ai_off, bakery, cake):
    from apps.catalog.models import ProductVariant

    ProductVariant.objects.create(product=cake, label="groß", price=Decimal("5"))
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    html = _html(bakery, user, got["job"])
    assert "Varianten" in html and "data-assistant-apply-btn" not in html


def test_changed_after_preview_is_refused(ai_off, bakery, cake):
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    Product.objects.update(base_price=Decimal("4.00"))  # кто-то поменял в форме
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get().base_price == Decimal("4.00")
    assert not AssistantChange.objects.exists()


def test_hide_and_undo(ai_off, bakery, cake):
    user, got = _ask(bakery, "скрой Käsekuchen")
    # направление из кэша: подмена POST «показать» не проходит
    _apply(bakery, user, got["job"], {**TAKE, "f_0_visible": "1"})
    assert Product.objects.get().is_active is False
    _undo(bakery, user, got["job"])
    assert Product.objects.get().is_active is True


def test_move_to_existing_category(ai_off, bakery, cake):
    torten = writers.create_category(bakery, {"name_de": "Torten"})
    user, got = _ask(bakery, "verschiebe Käsekuchen nach Torten")
    _apply(bakery, user, got["job"], TAKE)
    assert Product.objects.get().category_id == torten.pk
    _undo(bakery, user, got["job"])
    assert Product.objects.get().category_id is None


def test_ambiguous_name_has_no_button(ai_off, bakery, cake):
    writers.create_product(bakery, {"name_de": "Käsekuchen", "base_price": "4"})
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    html = _html(bakery, user, got["job"])
    assert "Mehrere" in html and "data-assistant-apply-btn" not in html


def test_history_keeps_only_a_summary(ai_off, bakery, cake):
    user, got = _ask(bakery, "Preis Käsekuchen auf 3,50 €")
    turn = AssistantTurn.objects.get(job=got["job"])
    assert turn.kind == "actions" and "actions" not in turn.entry and turn.entry["summary"]
    page = assistant_views.assistant_view(_req(bakery, user=user)).content.decode()
    assert "data-assistant-summary" in page


def test_category_hide(ai_off, bakery):
    writers.create_category(bakery, {"name_de": "Saisonware"})
    user, got = _ask(bakery, "blende Saisonware aus")
    _apply(bakery, user, got["job"], TAKE)
    assert Category.objects.get().is_active is False


@pytest.mark.parametrize(
    "question",
    [
        "Wie ändere ich den Preis von Käsekuchen?",
        "Wo kann ich Käsekuchen ausblenden?",
        "как изменить цену Käsekuchen?",
    ],
)
def test_question_is_not_a_change(ai_off, bakery, cake, question):
    assert not assistant_changes.intent(bakery, None, question)
