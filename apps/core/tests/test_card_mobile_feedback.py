"""Фидбэк владельца 2026-08-26 (вечер): карточка клиента и мобильная вёрстка.

«Убери кнопку написать клиенту в заказе — ниже всё равно есть открытое поле.
Убери кнопку Kundendaten bearbeiten отдельным полем, поставь карандаш возле
имени клиента… На мобильном состав заказа выглядит ужасно… В продуктах тоже не
адаптировано… Язык админки в мобильной версии нельзя переключить.»

Мобильную раскладку задаёт CSS (`.dl-row` в static/src/app.css), но она держится
на семантических классах ячеек — без них строка молча развалится обратно.
Поэтому здесь замки на разметку, а не на пиксели.
"""

from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
CSS = Path(__file__).resolve().parents[3] / "static" / "src" / "app.css"

# Файлы, которые рисуют строку состава: у брони/записи/билета общий партиал,
# у заказа и сметы — свои настоящие строки.
LINE_TEMPLATES = (
    "core/_deal_items_head.html",
    "core/_deal_lines.html",
    "orders/order_detail.html",
    "jobs/detail.html",
)


def _read(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", LINE_TEMPLATES)
def test_every_line_cell_carries_its_semantic_class(name):
    """Мобильная раскладка адресует ячейки по классам — они обязаны быть везде."""
    html = _read(name)

    for cls in ("dl-idx", "dl-name", "dl-unit", "dl-qty", "dl-sum"):
        assert cls in html, f"{name}: нет класса {cls}"


def test_mobile_rules_lay_the_row_out_instead_of_squeezing_it():
    css = CSS.read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 639px)", 1)[1]

    # строка раскладывается переносом, а не сеткой из шести колонок
    assert "flex-wrap: wrap" in mobile
    # шапка колонок скрыта БОЛЕЕ специфичным селектором, иначе display:flex ниже
    # перебил бы её (ровно этот дефект поймал стенд)
    assert ".dl-row.dl-head { display: none; }" in mobile
    head_at = mobile.index(".dl-row.dl-head")
    row_at = mobile.index(".dl-row {")
    assert head_at < row_at


def test_customer_card_has_pencil_and_no_duplicate_message_button():
    html = _read("core/_deal_customer_card.html")

    assert "data-customer-edit-open" in html  # карандаш у имени
    assert "_deal_message_button.html" not in html  # дубль кнопки убран
    assert "_deal_customer_edit.html" in html  # попап правки на месте


def test_customer_edit_is_a_dialog_not_a_disclosure_row():
    html = _read("core/_deal_customer_edit.html")

    assert "<dialog" in html
    assert "showModal" in html
    # прежняя строка-раскрывашка «Kundendaten bearbeiten» больше не рисуется
    assert "<summary" not in html


def test_quote_card_uses_the_shared_customer_popup():
    """Заявка жаловалась именно этой формой — теперь у неё общий попап."""
    from apps.jobs import views

    source = Path(views.__file__).read_text(encoding="utf-8")

    assert '"deal_customer_edit": True' in source
    quote = _read("jobs/detail.html")
    assert "Kundendaten bearbeiten" not in quote  # своей раскрывашки нет
    assert 'name="site_address"' in quote  # адрес объекта остался


def test_cabinet_language_switcher_is_reachable_on_phones():
    html = _read("tenant/_base_dashboard.html")
    # Берём САМ тег формы, а не текст вокруг: в комментарии рядом процитирован
    # прежний класс, и поиск по подстроке ловил бы его (поймано этим же замком).
    opening = html.split('<form method="post" action="{% url \'set-cabinet-lang\' %}"', 1)[1]
    tag = opening.split(">", 1)[0]
    body = opening.split("</form>", 1)[0]

    assert "hidden" not in tag  # форма видна и на узком экране
    assert 'select name="lang"' in body
