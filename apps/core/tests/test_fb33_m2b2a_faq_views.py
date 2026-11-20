"""FB-33 M2b-2a C1: реестр видов FAQ (`apps/core/faq_views.py`) — один список на все страницы."""

import ast
from pathlib import Path

import pytest

from apps.core import detail_parts, faq_views
from apps.tenants import siteconfig

DETAIL = {"product_detail", "service_detail", "stay_detail", "event_detail"}


def test_section_styles_of_faq_stay_byte_for_byte():
    """Сохранённые виды FAQ в конфигах валидны как раньше — тот же кортеж в том же порядке."""
    assert siteconfig.SECTION_STYLES["faq"] == ("list", "twocol", "cards", "numbered")
    assert type(siteconfig.SECTION_STYLES["faq"]) is tuple
    assert siteconfig.SECTION_STYLES["faq"] is faq_views.STYLE_KEYS


def test_faq_views_does_not_import_siteconfig():
    """Цикл импортов: siteconfig читает реестр при загрузке — реестр siteconfig не трогает."""
    tree = ast.parse(Path(faq_views.__file__).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {node.module or ""} | {f"{node.module}.{a.name}" for a in node.names}
    assert not [n for n in names if "siteconfig" in n], names
    allowed = {"__future__", "typing", "django.utils.translation", "apps.core.detail_parts"}
    assert {n for n in names if not any(n == a or n.startswith(a + ".") for a in allowed)} == set()


@pytest.mark.parametrize("host", sorted(detail_parts.SECTION_HOSTS))
def test_every_section_host_is_detail_only_if_it_is_a_detail_page(host):
    """Замок: новый хост с разделами не станет «детальным» молча (и наоборот)."""
    assert faq_views.is_detail_host(host) is (host in DETAIL)


@pytest.mark.parametrize("kind", sorted(detail_parts.OBJECT_SHARED))
def test_own_object_hosts_are_details(kind):
    """R8: свой хост объекта (товар, услуга, номер, событие, тур) — детальная страница."""
    host = f"{kind}:{'a' * 32}"
    assert faq_views.is_detail_host(host)
    assert detail_parts.shared_host(host) in DETAIL


@pytest.mark.parametrize(
    "host", ["", None, "home", "catalog", "services", "promo_detail", "combo_detail", "blog_post",
             "seite:ueber-uns", "tours", "x:abc"],
)  # fmt: skip
def test_other_pages_are_not_details(host):
    assert not faq_views.is_detail_host(host)
    assert faq_views.emits_ld(host)
    assert [v.key for v in faq_views.views(host)] == ["", "list", "twocol", "cards", "numbered"]


@pytest.mark.parametrize("host", ["service_detail", "event_detail", f"tour:{'b' * 32}"])
def test_detail_pages_offer_three_views_and_no_faqpage(host):
    assert [v.key for v in faq_views.views(host)] == ["", "list", "twocol"]
    assert not faq_views.emits_ld(host)


def test_one_name_per_view_on_every_page():
    """Решение владельца: «Akkordeon», «Liste» — у FAQ (у отзывов/команды «Offene Liste»)."""
    names = dict(faq_views.choices("home"))
    assert names == {
        "": "Akkordeon",
        "list": "Liste",
        "twocol": "Zwei Spalten",
        "cards": "Karten",
        "numbered": "Nummeriert",
    }
    assert faq_views.choices("service_detail") == [(k, names[k]) for k in ("", "list", "twocol")]
    assert all(v.hint for v in faq_views.VIEWS)
    assert faq_views.label("") == "Akkordeon" and faq_views.label("evil") == "evil"
    assert str(siteconfig.SECTION_STYLE_LABELS["list"]) == "Offene Liste"  # у прочих секций


# ── C2: панель блока FAQ — виды страницы ──


def _faq_panel(host, value="", key="faq_ref"):
    from apps.core import site_schema

    if key == "faq_ref":
        fields = site_schema.panel_fields({"key": key, "data": {"style": value} if value else {}})
        block = {"key": key, "fields": fields}
    else:
        block = {"key": key, "cblock": False, "fields": site_schema.section_style_fields({"key": key, "style": value})}  # fmt: skip
    site_schema.fill_options(block, host)
    return block["fields"][0]["options"]


@pytest.mark.parametrize("host", ["service_detail", "event_detail", f"service:{'c' * 32}"])
def test_detail_panel_offers_three_views(host):
    assert _faq_panel(host) == [("", "Akkordeon"), ("list", "Liste"), ("twocol", "Zwei Spalten")]


@pytest.mark.parametrize(("host", "key"), [("catalog", "faq_ref"), ("promo_detail", "faq_ref"), ("", "faq")])  # fmt: skip
def test_other_pages_and_the_home_section_offer_five_views(host, key):
    assert [lab for _k, lab in _faq_panel(host, key=key)] == [
        "Akkordeon",
        "Liste",
        "Zwei Spalten",
        "Karten",
        "Nummeriert",
    ]


def test_saved_view_outside_the_detail_views_stays_selected_with_a_note():
    """W0: «Karten» на детальной сохранён раньше — пункт остаётся и назван, а не «Standard»."""
    options = _faq_panel("service_detail", "cards")
    assert options[-1] == ("cards", "Karten (nicht unter den Ansichten dieser Seite)")
    assert len(options) == 4
    assert _faq_panel("service_detail", "evil")[-1] == ("evil", "evil (nicht verfügbar)")


@pytest.mark.django_db
def test_seitenaufbau_of_the_service_page_shows_three_faq_views(settings):
    from apps.core import site_schema
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    bt = "friseur"
    tenant = TenantFactory(business_type=bt, disabled_modules=list(default_disabled_for(bt)))
    ref = site_schema.apply(tenant, "service", "add", block_type="faq_ref")
    html = Browser(tenant).get(f"?seite=service&block={ref}")
    assert 'name="f_style"' in html and 'value="twocol"' in html
    assert 'value="cards"' not in html and 'value="numbered"' not in html
    assert ">Akkordeon<" in html
    site_schema.apply(tenant, "service", "update", ref=ref, fields={"style": "cards"})
    html = Browser(tenant).get(f"?seite=service&block={ref}")
    assert "Karten (nicht unter den Ansichten dieser Seite)" in html
