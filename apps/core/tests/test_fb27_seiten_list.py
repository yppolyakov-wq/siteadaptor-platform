"""FB-27 «Seiten», срез S-a: один список по макетам S1/S3 — карточки на телефоне, таблица
от планшета, действия в меню «⋯», удаление отдельным шагом с вопросом."""

import pathlib
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core import content_page_views as views
from apps.core import content_pages
from apps.core.models import ContentPage
from apps.core.tests.test_m21_6_content_pages import _req, _user

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant")


def _list(user=None):
    return views.pages_list(_req(user=user or _user())).content.decode()


def _part(html, marker):
    """Разметка одного вида списка: карточки (`<ul …cards>`) или таблица."""
    start = html.index(marker)
    # карточки кончаются там, где начинается таблица (внутри карточек есть свои списки меню)
    end = html.index("<table" if "cards" in marker else "</table>", start + 1)
    return html[start:end]


def test_list_has_no_danger_buttons_and_one_menu_per_row_in_each_view():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    for name in ("content_pages.html", "_page_row_menu.html"):
        assert "ui-btn-danger" not in (TPL / name).read_text(), name
    html = _list()
    rows = content_pages.all_rows(_req().tenant)
    for marker in ("data-pages-cards", "<table"):
        part = _part(html, marker)
        assert part.count("data-page-menu=") == len(rows), marker
        assert "ui-btn-danger" not in part and "<form" not in part


def test_cards_and_table_show_the_same_rows_in_the_same_order():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    ContentPage.objects.create(slug="bald", title="Bald", is_published=False)
    html = _list()
    cards = re.findall(r'data-page-row="([^"]+)"', _part(html, "data-pages-cards"))
    table = re.findall(r'data-page-row="([^"]+)"', _part(html, "<table"))
    assert cards == table and "page:zahlung" in cards and "legal:impressum" in cards


def test_legal_rows_carry_the_caption_and_cannot_be_deleted():
    html = _list()
    menu = html[html.index('data-page-menu="legal:impressum"') :]
    menu = menu[: menu.index("</details>")]
    assert "Rechtstexte können nicht gelöscht werden." in menu and "loeschen=1" not in menu
    row = html[html.index('data-page-row="legal:impressum"') :]
    assert "Rechtstext" in row[: row.index("data-page-menu")]


def test_own_page_menu_leads_to_a_confirmation_step_not_to_a_delete_request():
    page = ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    html = _list()
    menu = html[html.index('data-page-menu="page:zahlung"') :]
    menu = menu[: menu.index("</details>")]
    assert f"/dashboard/site/seiten/{page.pk}/?loeschen=1" in menu
    assert "content-page-delete" not in menu and "/loeschen/" not in menu.replace("?loeschen=1", "")


def test_delete_needs_the_confirmation_step_and_a_get_writes_nothing():
    page = ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    owner = _user()
    plain = views.page_edit(_req(user=owner), page.pk).content.decode()
    assert "data-page-delete-confirm" not in plain and "data-page-delete-link" in plain
    asked = views.page_edit(_req("/x/?loeschen=1", user=owner), page.pk).content.decode()
    assert "data-page-delete-confirm" in asked and "Seite „Zahlung“ löschen?" in asked
    assert ContentPage.objects.filter(pk=page.pk).exists()  # GET ничего не удалил


def test_blocks_column_names_what_stands_on_the_page_without_a_query_per_row():
    tenant = _req().tenant
    tenant.site_config = {
        "page_blocks": {
            "seite:zahlung": [
                {"key": "text", "id": "a", "enabled": True, "data": {"title": "x"}},
                {"key": "button", "id": "b", "enabled": True, "data": {"label": "y"}},
            ]
        }
    }
    for i in range(6):
        ContentPage.objects.create(slug=f"s{i}", title=f"S{i}", is_published=True)
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    with CaptureQueriesContext(connection) as few:
        rows = content_pages.all_rows(tenant)
    row = next(r for r in rows if r.key == "page:zahlung")
    assert row.blocks == "Text + 1" and row.schema_url.endswith("?seite=text@seite:zahlung")
    assert next(r for r in rows if r.key == "legal:impressum").schema_url == ""
    for i in range(6, 12):
        ContentPage.objects.create(slug=f"s{i}", title=f"S{i}", is_published=True)
    with CaptureQueriesContext(connection) as many:
        content_pages.all_rows(tenant)
    assert len(many) <= len(few)  # число запросов не растёт с числом страниц


def test_published_own_page_reads_veroeffentlicht_and_a_draft_entwurf():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    ContentPage.objects.create(slug="bald", title="Bald", is_published=False)
    html = _list()
    row = html[html.index('data-page-row="page:zahlung"') :]
    assert "Veröffentlicht" in row[: row.index("data-page-menu")]
    row = html[html.index('data-page-row="page:bald"') :]
    assert "Entwurf" in row[: row.index("data-page-menu")]
