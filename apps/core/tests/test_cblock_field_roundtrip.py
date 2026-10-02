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
    assert "promo_list" in fields and "spacer" in fields, sorted(fields)
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
    """Сквозной сценарий владельца: выбрал тип, задал заголовок и лимит, нажал Save."""
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
    assert block["data"] == {"type": "sys:mystery", "title": "Nur heute", "limit": 6}
