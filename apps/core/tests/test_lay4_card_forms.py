"""LAY-4 — ось «Форма карточки» действует на ВСЕХ поверхностях.

Разведка волны LAY: Studio предлагает 7 форм карточки на страницах услуг,
номеров, событий и лукбука, а `_sellable_card.html` понимает ДВЕ (`compact`,
`overlay`); `_combo_card.html` и `_tour_card.html` — ни одной. Вдобавок
`sellable_ui` берёт ТОЛЬКО сайтовый дефолт (`context["storefront_card_style"]`),
поэтому выбор «только для этого товара/этой категории» на таких страницах не
действует вовсе — пилюля охвата там обманывает.

Это ровно класс «обещание без исполнения», который волна и закрывает
(правило STU-9). Замки написаны ДО правок и краснеют на текущем коде.
"""

import re

import pytest

pytestmark = pytest.mark.django_db


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── 4a. Резолвер: объект → категория → сайт (а не только сайт) ───────────────


def test_sellable_card_resolves_the_object_layer():
    """Тег карточки обязан звать общий резолвер, иначе слои объекта мертвы."""
    body = _read("apps/core/templatetags/sellable_ui.py")
    assert "card_forms" in body, "sellable_ui не знает про реестр форм карточки"
    assert not re.search(r'"card_style":\s*context\.get\("storefront_card_style"', body), (
        "форма берётся напрямую из сайтового дефолта — слой объекта недостижим"
    )


# ── 4a. Формы, обещанные Studio, реализованы в общей карточке ────────────────

SELLABLE_FORMS = ["regal", "lookbook", "deal", "etikett"]


@pytest.mark.parametrize("form", SELLABLE_FORMS)
def test_sellable_card_implements_every_promised_form(form):
    body = _read("templates/storefront/_sellable_card.html")
    assert f'card_style == "{form}"' in body, (
        f"форма {form} предлагается Studio на услугах/номерах/событиях, но карточка её не знает"
    )


def test_sellable_card_keeps_its_legacy_branches():
    """Паритет: прежние ветки на месте — вид без выбора формы не менялся."""
    body = _read("templates/storefront/_sellable_card.html")
    assert 'card_style == "compact"' in body
    assert 'card_style == "overlay"' in body


# ── 4b. Наборы и туры ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["templates/storefront/_combo_card.html", "templates/storefront/_tour_card.html"]
)
def test_combo_and_tour_cards_know_the_axis(path):
    body = _read(path)
    assert "card_style" in body, f"{path}: карточка не знает про форму вывода"


# ── Инвариант волны: обещание = исполнение ──────────────────────────────────


def test_no_page_type_promises_a_card_form_without_a_card():
    """Тип страницы объявляет `*_card_form` ⇒ его разметка рисует карточку.

    Именно этот замок не даст каше вернуться: сегодня `events`, `event` и `stay`
    объявляют форму карточки, а рисуют карточки инлайн-разметкой без неё.
    """
    from apps.core import studio_pages

    CARD_TEMPLATES = {
        "catalog": ["templates/storefront/products.html"],
        "category": ["templates/storefront/products.html"],
        "product": ["templates/storefront/product_detail.html"],
        "services": ["templates/storefront/service_index.html"],
        "service": ["templates/storefront/sections/detail/_service_upsell.html"],
        "stays": ["templates/storefront/stay_index.html"],
        "stay": ["templates/storefront/sections/detail/_stay_similar.html"],
        "events": ["templates/storefront/event_index.html"],
        "lookbook": ["templates/storefront/lookbook.html"],
        "promos": ["templates/storefront/promotions_list.html"],
        "promo_group": ["templates/storefront/promo_group/_grid.html"],
        "promo": ["templates/storefront/promotion_detail.html"],
        # STU-17: пять типов, у которых ось действовала, но панель её не предлагала.
        # Замок фейл-клоузед (тип без записи = нарушитель) — и правильно: каждая
        # строка ниже проверена глазами, что карточка там РЕАЛЬНО рисуется.
        "tours": ["templates/storefront/tour_index.html"],
        "combos": ["templates/storefront/_combo_grid.html"],
        "wishlist": ["templates/storefront/wishlist.html"],
        "finder": ["templates/storefront/finder.html"],
        "cart": ["templates/storefront/cart.html"],
    }
    CARD_MARKERS = (
        "_product_card.html",
        "_promo_card.html",
        "sellable_card",
        "_combo_card.html",
        "_tour_card.html",  # STU-17: карточка тура читает ту же ось (LAY-4b)
    )
    offenders = []
    for page in studio_pages.PAGE_TYPES:
        forms = [c for c in page.settings if c.endswith("_card_form")]
        if not forms:
            continue
        paths = CARD_TEMPLATES.get(page.code)
        if paths is None:
            offenders.append(f"{page.code}: тип не описан в карте шаблонов замка")
            continue
        if not any(any(m in _read(p) for m in CARD_MARKERS) for p in paths):
            offenders.append(f"{page.code}: обещает {forms}, но карточку не рисует")
    assert not offenders, offenders
