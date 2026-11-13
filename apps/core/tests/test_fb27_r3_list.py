"""FB-27 R3b-2: блок «Liste» в панели «Seitenaufbau» — «Was zeigen · Welche · Wie»."""

import pytest

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _data(tenant, host="info"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return next(b for b in cfg["page_blocks"][host] if b.get("id"))["data"]


def _list(browser):
    return site_schema.apply(browser.tenant, "text", "add", block_type="list")


def test_panel_has_three_groups_for_a_list_block():
    b = Browser(_tenant())
    ref = _list(b)
    html = b.get(f"?seite=text&block={ref}")
    assert "data-schema-list" in html
    for key in ("was", "welche", "wie"):
        assert f'data-schema-group="{key}"' in html
    assert 'name="f_source"' in html and 'name="f_cols"' in html


def test_only_filters_of_the_chosen_source_are_shown():
    b = Browser(_tenant())
    ref = _list(b)
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_source="products")
    # FB-27 V2 (макет, осознанная переписка): способ «Welche» — три кнопки; поля
    # категории стоят под «Kategorie», остальные фильтры — под «Regel».
    html = b.get(f"?seite=text&block={ref}")
    assert 'name="f_only"' in html and 'name="f_category"' not in html
    assert 'data-schema-which-mode="kategorie"' in html
    html = b.get(f"?seite=text&block={ref}&welche=kategorie")
    assert 'name="f_category"' in html and 'name="f_only"' not in html
    assert 'name="f_type"' not in html and 'name="f_rabatt"' not in html
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_source="promotions")
    html = b.get(f"?seite=text&block={ref}")
    assert 'name="f_type"' in html and 'name="f_category"' not in html


def test_rule_goes_through_the_draft_and_is_saved():
    b = Browser(_tenant())
    ref = _list(b)
    b.post(
        seite="text", op="update", ref=ref, panel_present="1",
        f_source="products", f_only="sale", f_limit="6", f_cols="3", f_out="slider",
        f_title="Reduziert",
    )  # fmt: skip
    assert _data(b.tenant).get("only") is None  # пока черновик
    b.post(seite="text", op="save")
    data = _data(b.tenant)
    assert data["source"] == "products" and data["only"] == "sale"
    assert data["limit"] == 6 and data["cols"] == 3 and data["out"] == "slider"
    assert data["title"] == "Reduziert"


def test_changing_the_source_drops_foreign_filters():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    site_schema.apply(
        tenant, "text", "update", ref=ref, fields={"source": "products", "only": "sale"}
    )
    site_schema.apply(tenant, "text", "update", ref=ref, fields={"source": "promotions"})
    assert "only" not in _data(tenant)


def test_upcoming_is_stored_as_phase_and_can_be_cleared():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    site_schema.apply(
        tenant, "text", "update", ref=ref, fields={"source": "promotions", "endet": "upcoming"}
    )
    assert _data(tenant).get("phase") == "upcoming"
    site_schema.apply(tenant, "text", "update", ref=ref, fields={"endet": ""})
    assert "phase" not in _data(tenant) and "endet" not in _data(tenant)


def test_rubbish_values_are_not_stored():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    site_schema.apply(
        tenant, "text", "update", ref=ref,
        fields={"source": "products", "card": "<script>", "cols": "99", "only": "evil", "out": "x"},
    )  # fmt: skip
    data = _data(tenant)
    assert not {"card", "cols", "only", "out"} & set(data)


def test_unchanged_submit_creates_no_draft():
    b = Browser(_tenant())
    ref = _list(b)
    site_schema.apply(
        b.tenant, "text", "update", ref=ref, fields={"source": "products", "limit": "6"}
    )
    b.post(
        seite="text", op="update", ref=ref, panel_present="1",
        f_source="products", f_limit="6", f_cols="", f_only="",
    )  # fmt: skip
    assert "data-schema-draft" not in b.get("?seite=text")


def test_value_that_is_gone_stays_selected():
    """Удалённая категория остаётся выбранным пунктом — «Übernehmen» её не сменит молча."""
    b = Browser(_tenant())
    ref = _list(b)
    site_schema.apply(
        b.tenant, "text", "update", ref=ref, fields={"source": "products", "category": "weg"}
    )
    html = b.get(f"?seite=text&block={ref}")
    assert '<option value="weg" selected>' in html


def test_speed_and_other_fields_outside_the_panel_survive():
    tenant = _tenant()
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "info": [
                    {"id": "a1", "key": "list", "enabled": True,
                     "data": {"source": "products", "out": "slider", "speed": 5}}
                ]
            }
        }
    )  # fmt: skip
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    site_schema.apply(tenant, "text", "update", ref="a1", fields={"limit": "4"})
    data = _data(tenant)
    assert data["speed"] == 5 and data["limit"] == 4


def test_empty_selection_is_named_in_the_panel():
    """Пустой блок на сайте не выводится — панель говорит об этом до «Speichern»."""
    b = Browser(_tenant())
    ref = _list(b)
    site_schema.apply(b.tenant, "text", "update", ref=ref, fields={"source": "products"})
    html = b.get(f"?seite=text&block={ref}")
    assert "erscheint nicht auf der Website" in html


def test_panel_says_how_many_entries_the_block_shows():
    from apps.catalog.tests.factories import ProductFactory

    ProductFactory.create_batch(2)
    b = Browser(_tenant())
    ref = _list(b)
    site_schema.apply(b.tenant, "text", "update", ref=ref, fields={"source": "products"})
    html = b.get(f"?seite=text&block={ref}")
    assert "Zeigt derzeit 2 Einträge (von 2)." in html


def _panel_values(html):
    """Что браузер отправит из формы панели, если ничего не трогать."""
    import re
    from html import unescape

    form = html[html.index("data-schema-list") :]
    form = form[: form.index("</form>")]
    out = {}
    for name, body in re.findall(r'<select[^>]*name="(f_\w+)"[^>]*>(.*?)</select>', form, re.S):
        picked = re.search(r'<option value="([^"]*)" selected', body)
        first = re.search(r'<option value="([^"]*)"', body)
        out[name] = unescape((picked or first).group(1))
    for tag in re.findall(r"<input[^>]*>", form):
        name = re.search(r'name="(f_\w+)"', tag)
        if name and ('type="radio"' not in tag or " checked" in tag):
            out[name.group(1)] = unescape(re.search(r'value="([^"]*)"', tag).group(1))
    for name, body in re.findall(r'<textarea[^>]*name="(f_\w+)"[^>]*>(.*?)</textarea>', form, re.S):
        out[name] = unescape(body)
    return out


@pytest.mark.parametrize(
    "data",
    [
        {"source": "promotions", "type": "Räumung", "phase": "upcoming", "ziel": "product"},
        {"source": "promotions", "endet": "woche", "rabatt": 30, "sort": "rabatt"},
        {"source": "products", "category": "weg", "only": "sale", "sort": "newest", "limit": 7,
         "cols": 4, "rows": 2, "out": "slider", "speed": 5, "card": "deal",
         "style": "preisliste", "title": "T", "intro": "eins\nzwei"},
        {"source": "products", "collection": "fort", "sort": "featured"},
        {"source": "services", "only": "video"},
        {"source": "events", "event_category": "Yoga & mehr", "only": "soon"},
        {"source": "tours", "country": "Nepal"},
        {"source": "categories", "category": "weg", "style": "tall"},
        {"source": "reviews", "entity": "event", "stars": 4, "only": "text", "sort": "best"},
        {"source": "stays"},
        # FB-27 R5: ручной состав — правило не показано, но обязано уцелеть
        {"source": "products", "pick": ["11111111-1111-4111-8111-111111111111"],
         "only": "sale", "sort": "price_asc", "limit": 5, "category": "weg"},
        {"source": "combos"},
        {"source": "blog"},
    ],
)  # fmt: skip
def test_untouched_panel_never_changes_the_block(data):
    """Класс W0: «Übernehmen» без единой правки не меняет блок — для каждого источника
    и для значений, которых уже нет среди пунктов."""
    tenant = _tenant()
    cfg = siteconfig.normalize(
        {"page_blocks": {"info": [{"id": "a1", "key": "list", "enabled": True, "data": data}]}}
    )
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    tenant.refresh_from_db()
    before = _data(tenant)
    b = Browser(tenant)
    values = _panel_values(b.get("?seite=text&block=a1"))
    assert "f_source" in values
    b.post(seite="text", op="update", ref="a1", panel_present="1", **values)
    assert "data-schema-draft" not in b.get("?seite=text"), values
    assert _data(tenant) == before
