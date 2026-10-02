"""Поле в строке C-блока ⇒ его читает Save ⇒ его несёт live-черновик (замок КЛАССА).

Дефект повторялся дважды одним и тем же способом:

* STU-12e — у «Abstand» был контрол высоты, а `_read_cblock_data` не знал spacer, и
  Save молча терял высоту;
* PT-6 (найдено разведкой 2026-10-02) — у блока «Aktionen eines Typs» в строке есть
  выбор типа, заголовок и «Höchstens», но `_read_cblock_data` не знал `promo_list`:
  первый же Save билдера стирал тип, и блок начинал показывать ВСЕ акции; черновик
  (`CB_DATA_FIELDS`) не слал `type`/`limit` — превью тоже показывало всё подряд.

Поэтому замок не про один тип блока, а про все: рендерим строку редактора для КАЖДОГО
повторяемого блока, собираем поля `cb_<id>_<поле>` и требуем, чтобы каждое из них
читалось приёмником Save и входило в набор полей черновика.
"""

import re

import pytest
from django.http import QueryDict

from apps.core import views
from apps.core.tests.test_stu12_groups import TPL, _builder, _post_builder, _segment
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Поля, которые collect() черновика читает ОТДЕЛЬНОЙ веткой (чекбокс шлётся по
# checked, а не по value — общий перебор CB_DATA_FIELDS его бы не увидел).
DRAFT_SPECIAL = {"show_button"}


def _editor_fields(tenant) -> dict[str, set[str]]:
    """Тип блока → поля `cb_<id>_<поле>`, которые строка редактора реально выводит."""
    body = _builder(tenant)
    types = dict(re.findall(r'name="cb_type_([\w-]+)" value="([\w]+)"', body))
    out: dict[str, set[str]] = {}
    for bid, field in re.findall(r'name="cb_([\w-]+?)_([a-z_]+)"', body):
        if bid in types:
            out.setdefault(types[bid], set()).add(field)
    return out


@pytest.fixture
def tenant_with_every_block():
    sections = [
        {"key": key, "id": f"rt{i}", "enabled": True, "order": i + 1, "data": {}}
        for i, key in enumerate(sorted(siteconfig.REPEATABLE_BLOCKS))
    ]
    return TenantFactory(slug="cbrt", name="CbRt", site_config={"sections": sections})


def test_every_editor_field_is_read_by_save(tenant_with_every_block):
    fields = _editor_fields(tenant_with_every_block)
    # Санити: строка редактора выведена для каждого повторяемого блока с полями.
    # LB-1: «Aktionen eines Typs» (PT-6) стал блоком «Liste» — санити на новом ключе.
    assert "list" in fields and "spacer" in fields, sorted(fields)
    lost = []
    for btype, names in fields.items():
        post = QueryDict(mutable=True)
        for name in names:
            post[f"cb_x_{name}"] = "on" if name == "show_button" else "3"
        data = views._read_cblock_data(post, "x", btype)
        lost += [f"{btype}.{name}" for name in sorted(names) if name not in data]
    assert not lost, f"Save молча теряет поля строки редактора: {lost}"


def test_every_editor_field_reaches_the_live_draft(tenant_with_every_block):
    draft = set(re.findall(r'"(\w+)"', _segment(TPL.read_text("utf-8"), "var CB_DATA_FIELDS", "]")))
    missing = sorted(
        f"{btype}.{name}"
        for btype, names in _editor_fields(tenant_with_every_block).items()
        for name in names
        if name not in draft and name not in DRAFT_SPECIAL
    )
    assert not missing, f"черновик не несёт поля строки редактора: {missing}"


def test_promo_list_type_survives_builder_save():
    """Сквозной сценарий владельца: выбрал тип, задал заголовок и лимит, нажал Save.

    LB-1 (осознанная переписка): вкладка Студии, открытая ДО деплоя, шлёт легаси-тип
    `promo_list` — Save его принимает и сохраняет блоком «Liste» с источником «акции»
    (данные PT-6 подходят без преобразования), ничего не теряя.
    """
    tenant = TenantFactory(
        slug="cbrt2",
        name="CbRt2",
        site_config={
            "sections": [
                {"key": "promo_list", "id": "pl1", "enabled": True, "order": 1, "data": {}}
            ]
        },
    )
    cfg = _post_builder(
        tenant,
        {
            "cb_id": "pl1",
            "cb_type_pl1": "promo_list",
            "enabled_cb_pl1": "on",
            "order_cb_pl1": "1",
            "cb_pl1_type": "sys:mystery",
            "cb_pl1_title": "Nur heute",
            "cb_pl1_limit": "6",
        },
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "pl1")
    assert block["key"] == "list"
    assert block["data"] == {
        "source": "promotions",
        "type": "sys:mystery",
        "title": "Nur heute",
        "limit": 6,
    }


def test_list_block_survives_builder_save():
    """LB-1: блок «Liste» товаров — фильтр, сортировка и вид переживают Save."""
    tenant = TenantFactory(
        slug="cbrt3",
        name="CbRt3",
        site_config={
            "sections": [{"key": "list", "id": "lb1", "enabled": True, "order": 1, "data": {}}]
        },
    )
    post = {
        "cb_id": "lb1",
        "cb_type_lb1": "list",
        "enabled_cb_lb1": "on",
        "order_cb_lb1": "1",
        "cb_lb1_source": "products",
        "cb_lb1_category": "kaese",
        "cb_lb1_only": "sale",
        "cb_lb1_sort": "price_asc",
        "cb_lb1_limit": "8",
        "cb_lb1_title": "Käse im Angebot",
        "cb_lb1_intro": "Diese Woche günstiger.",
        "cb_lb1_out": "slider",
        "cb_lb1_cols": "4",
        "cb_lb1_rows": "2",
        "cb_lb1_speed": "5",
        "cb_lb1_card": "regal",
        # поля скрытого источника тоже приходят (W0) — normalize их не хранит
        "cb_lb1_type": "Räumung",
        "cb_lb1_endet": "heute",
    }
    cfg = _post_builder(tenant, post)
    block = next(s for s in cfg["sections"] if s.get("id") == "lb1")
    assert block["data"] == {
        "source": "products",
        "category": "kaese",
        "only": "sale",
        "sort": "price_asc",
        "limit": 8,
        "title": "Käse im Angebot",
        "intro": "Diese Woche günstiger.",
        "out": "slider",
        "cols": 4,
        "rows": 2,
        "speed": 5,
        "card": "regal",
    }
