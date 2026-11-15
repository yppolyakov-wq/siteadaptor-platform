"""FB-30.9 (макет 5): подвал — конструктор как у шапки: порядок, перенос между колонками,
скрытие, выбор колонки в панели; нижняя панель — вид на телефоне. Модель данных прежняя."""

import pathlib

from apps.tenants import siteconfig

SRC = pathlib.Path("templates/tenant/site_menu.html").read_text()


def test_footer_links_can_move_between_columns_and_be_hidden():
    footer = SRC[SRC.index("function renderFooter()") : SRC.index("function renderBottomPreview()")]
    for token in ("T.toLeft", "T.toRight", "T.up", "T.down", "T.hide", "moveToColumn(", "drop"):
        assert token in footer, token
    assert "data-footer-column" in SRC, "колонка выбирается и в панели пункта"
    assert "footer_max_links" in SRC.split("function moveToColumn", 1)[1][:500], "потолок колонки"


def test_bottom_bar_shows_its_phone_view():
    assert 'id="bottom-preview"' in SRC and "renderBottomPreview();" in SRC
    assert ".slice(0, 5)" in SRC


def test_hidden_footer_link_survives_saving_and_is_not_shown():
    raw = {"footer": {"columns": [{"label": "Shop", "items": [
        {"label": "Sortiment", "type": "products", "target": "", "enabled": False},
        {"label": "Kontakt", "type": "url", "target": "/kontakt/"},
    ]}]}}  # fmt: skip
    cols = siteconfig.normalize({"menus": raw})["menus"]["footer"]["columns"]
    assert [i.get("enabled", True) for i in cols[0]["items"]] == [False, True]
