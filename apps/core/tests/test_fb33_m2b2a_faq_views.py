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
