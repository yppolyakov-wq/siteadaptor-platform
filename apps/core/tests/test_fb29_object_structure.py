"""FB-29.4b S1: своя структура страницы у товара и услуги — показ разделов и шаблон
страницы поверх общих настроек («Website › Seitenaufbau»). Объект без правок выглядит
как раньше."""

from types import SimpleNamespace

import pytest

from apps.core import object_structure as ost
from apps.tenants import siteconfig

CFG = {"product_detail": {"hidden": ["related"], "layout": "tabs"}}


def _obj(**override):
    return SimpleNamespace(page_override=override)


def test_object_without_overrides_reads_the_shared_settings():
    for obj in (_obj(), SimpleNamespace(), SimpleNamespace(page_override=None)):
        assert ost.effective_hidden(CFG, "catalog", obj) == siteconfig.detail_section_hidden(
            CFG, "catalog"
        )
        assert ost.effective_layout(CFG, "product", obj) == "tabs"


def test_shown_beats_the_shared_hiding_and_hidden_beats_the_shared_showing():
    obj = _obj(shown=["related"], hidden=["reviews"])
    assert ost.effective_hidden(CFG, "catalog", obj) == {"reviews"}


def test_own_layout_and_explicit_default():
    assert ost.effective_layout(CFG, "product", _obj(layout="breit")) == "breit"
    # «standard» — свой выбор «обычный вид», хотя у сайта стоят вкладки
    assert ost.effective_layout(CFG, "product", _obj(layout="standard")) == ""
    assert ost.effective_layout(CFG, "product", _obj(layout="<script>")) == "tabs"


def test_clean_keeps_only_known_sections_and_is_presence_minimal():
    raw = {
        "hidden": ["reviews", "nope", "reviews"],
        "shown": ["related", "reviews", 7],
        "layout": "breit",
        "junk": 1,
    }
    assert ost.clean(raw, "catalog") == {
        "hidden": ["reviews"],
        "shown": ["related"],  # раздел не может быть и «показать», и «скрыть» — скрытие главнее
        "layout": "breit",
    }
    assert ost.clean({"hidden": [], "layout": "x"}, "catalog") == {}
    assert ost.clean("garbage", "booking") == {}
    assert ost.clean({"hidden": ["team"]}, "booking") == {"hidden": ["team"]}


def test_garbage_in_the_field_never_breaks_the_page():
    obj = SimpleNamespace(page_override={"hidden": "reviews", "shown": {"a": 1}, "layout": 5})
    assert ost.effective_hidden(CFG, "catalog", obj) == {"related"}
    assert ost.effective_layout(CFG, "product", obj) == "tabs"


def test_deviations_are_counted_for_the_badge():
    assert ost.deviations(_obj(), "catalog") == 0
    assert (
        ost.deviations(_obj(shown=["related"], hidden=["reviews"], layout="breit"), "catalog") == 3
    )


@pytest.mark.django_db
def test_models_carry_the_override_fields():
    from apps.booking.models import Service
    from apps.catalog.models import Product

    assert Product._meta.get_field("page_override").default is dict
    assert Service._meta.get_field("page_override").default is dict
    assert Service._meta.get_field("card_style").blank is True
