"""S1/S2 (упрощение кабинета): хаб-табы Sortiment/Verkäufe + свод nav 5→1 и продаж."""

from types import SimpleNamespace

import pytest
from django.template import Context, Template

from apps.core import modules


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- S1: хаб «Sortiment» (каталог) ------------------------------------------
def test_catalog_nav_collapsed_to_one_hub():
    cat = modules.get_module("catalog")
    assert len(cat.nav_items) == 1  # 5 пунктов → 1 хаб
    assert cat.nav_items[0].nav_key == "catalog"


def _render(nav):
    return Template('{% load cabinet %}{% hub_tabs "catalog" %}').render(Context({"nav": nav}))


def test_hub_tabs_renders_all_five_subpages():
    html = _render("catalog")
    for lbl in ("Produkte", "Kategorien", "Lager", "Kombi", "Import"):
        assert lbl in html


def test_hub_tabs_marks_exactly_one_active():
    html = _render("stock")  # Lager активен
    assert html.count('aria-selected="true"') == 1
    # активный таб — именно Lager (ссылка на stock, подсвечена)
    assert 'aria-selected="true"' in html and "Lager" in html


def test_hub_tabs_empty_for_unknown_hub():
    assert (
        Template('{% load cabinet %}{% hub_tabs "nope" %}').render(Context({"nav": "x"})).strip()
        == ""
    )


# --- S2: хаб «Verkäufe» (доска + продажные списки/календари) -----------------
def _fake_tenant(disabled=()):
    return SimpleNamespace(disabled_modules=list(disabled), enabled_modules=[])


def _render_board(nav, tenant=None):
    ctx = {"nav": nav}
    if tenant is not None:
        ctx["request"] = SimpleNamespace(tenant=tenant)
    return Template('{% load cabinet %}{% hub_tabs "board" %}').render(Context(ctx))


def test_sales_nav_collapsed_into_verkauefe():
    # 5 продажных пунктов сайдбара убраны (доступны через единую страницу продаж).
    for key in ("orders", "booking", "stays", "events", "jobs"):
        assert modules.get_module(key).nav_items == (), key
    assert str(modules.NAV_TASK_LABELS["board"]) == "Verkäufe"


def test_board_hub_only_uncovered_tabs():
    """W-CL: board/календари/список покрыты сегментом ST-5b и единой страницей —
    в реестре board-хаба остались только Tickets/Aufträge."""
    html = _render_board("board", _fake_tenant())  # ничего не выключено
    for lbl in ("Board", "Bestellungen", "Termine", "Übernachtungen"):
        assert lbl not in html, lbl
    for lbl in ("Tickets", "Aufträge"):
        assert lbl in html, lbl


def test_board_hub_gates_inactive_modules():
    # Тенант без Tickets — вкладка скрыта, Aufträge видна.
    tenant = _fake_tenant(disabled=["events"])
    html = _render_board("jobs", tenant)
    assert "Tickets" not in html
    assert "Aufträge" in html
    assert html.count('aria-selected="true"') == 1  # активна вкладка Aufträge


def test_board_hub_fail_open_without_request():
    # Без request/tenant в контексте (простой рендер) — гейт fail-open.
    html = _render_board("board")
    for lbl in ("Tickets", "Aufträge"):
        assert lbl in html, lbl


# --- S3: хаб «Einstellungen» (свод настроек + ящик «Erweitert») ---------------
def _render_settings(nav):
    return Template('{% load cabinet %}{% hub_tabs "settings" %}').render(Context({"nav": nav}))


def test_settings_nav_collapsed_to_website_plus_hub():
    # 10 пунктов настроек → 2: «Website» (билдер) + хаб «Einstellungen».
    keys = [n.nav_key for n in modules.get_module("settings").nav_items]
    assert keys == ["site", "settings"]
    assert str(modules.NAV_TASK_LABELS["settings"]) == "Einstellungen"


def test_settings_hub_primary_and_advanced_tabs():
    # W9-1: «базовые + по типам» — целевой порядок табов Settings-хаба.
    html = _render_settings("settings")
    for lbl in (
        "Mein Geschäft",
        "Sprachen",
        "Recht &amp; Steuern",
        "Zahlung &amp; Lieferung",
        "Benachrichtigungen &amp; Kanäle",
        "Abläufe",  # W9-8
    ):
        assert lbl in html, lbl
    # ящик «Erweitert» + его (редкие) вкладки (Zusatzleistungen/Finder переехали сюда)
    assert "Erweitert" in html
    for lbl in ("Zusatzleistungen", "Medien", "Domains", "Funktionen", "Finder", "Hilfe"):
        assert lbl in html, lbl


def test_settings_hub_erweitert_closed_on_primary_active():
    # Активна прямая вкладка → ящик «Erweitert» свёрнут (без open).
    html = _render_settings("settings")
    assert " open>" not in html
    assert html.count('aria-selected="true"') == 1  # активна одна прямая вкладка


def test_settings_hub_erweitert_open_on_advanced_active():
    # Активна вкладка из «Erweitert» (Medien) → ящик раскрыт (open), подсвечен.
    html = _render_settings("media")
    assert " open>" in html
    assert html.count('aria-selected="true"') == 1  # активна одна вкладка (в ящике)


# --- S4a: хаб «Marketing» (акции/отзывы/лояльность/публикация) ---------------
def _render_marketing(nav, tenant=None):
    ctx = {"nav": nav}
    if tenant is not None:
        ctx["request"] = SimpleNamespace(tenant=tenant)
    return Template('{% load cabinet %}{% hub_tabs "marketing" %}').render(Context(ctx))


def test_marketing_nav_collapsed_to_hub():
    # промо/отзывы/лояльность/публикация убраны из сайдбара → якорь «Marketing».
    assert modules.get_module("promotions").nav_items != ()  # якорь остаётся
    assert str(modules.NAV_TASK_LABELS["promotions"]) == "Marketing"
    for key in ("reviews", "loyalty", "publishing"):
        assert modules.get_module(key).nav_items == (), key
    # «Kampagnen» переехали из CRM в хаб → у CRM остался один пункт-якорь.
    crm_keys = [n.nav_key for n in modules.get_module("crm").nav_items]
    assert crm_keys == ["crm"]


def test_marketing_hub_all_tabs_when_active():
    html = _render_marketing("promotions", _fake_tenant())
    for lbl in ("Aktionen", "Bewertungen", "Kampagnen", "Gutscheine"):  # прямые
        assert lbl in html, lbl
    assert "Erweitert" in html
    for lbl in ("Reservierungen", "Einlösen", "Treuepunkte", "Kanäle", "Beiträge"):  # ящик
        assert lbl in html, lbl
    assert html.count('aria-selected="true"') == 1  # активна Aktionen


def test_marketing_hub_gates_by_module():
    # Без publishing — Kanäle/Beiträge скрыты; без reviews — Bewertungen скрыт.
    html = _render_marketing("promotions", _fake_tenant(disabled=["publishing", "reviews"]))
    assert "Kanäle" not in html
    assert "Beiträge" not in html
    assert "Bewertungen" not in html
    assert "Aktionen" in html  # promotions активен


# --- W11-1 (Р-2): хаб «Kunden» влит в Marketing --------------------------------
def test_kunden_hub_is_gone_pages_render_marketing():
    """Kunden-хаб удалён из реестра; crm/inbox/telegram — вкладки Marketing
    («молчаливая подмена таб-бара» умерла)."""
    from apps.core import nav_registry
    from apps.core.templatetags.cabinet import HUB_TABS

    assert "kunden" not in nav_registry.HUBS
    assert "kunden" not in HUB_TABS
    assert not any(e.hub == "kunden" for e in nav_registry.ENTRIES)
    # Пустой рендер бывшего хаба — не 500 (unknown hub → "")
    out = Template('{% load cabinet %}{% hub_tabs "kunden" %}').render(Context({"nav": "crm"}))
    assert out.strip() == ""
    for key in ("inbox", "telegram"):
        assert modules.get_module(key).nav_items == (), key


def test_kontakte_nachrichten_are_direct_marketing_tabs():
    # Прямые табы (не Erweitert): группа «Ruf & Dialog»; Telegram — в ящике.
    html = _render_marketing("crm", _fake_tenant())
    assert html.count('aria-selected="true"') == 1  # активна Kontakte
    from apps.core.templatetags.cabinet import HUB_TABS

    direct = {str(t[1]) for t in HUB_TABS["marketing"] if not t[4]}
    assert {"Kontakte", "Nachrichten"} <= direct
    advanced = {str(t[1]) for t in HUB_TABS["marketing"] if t[4]}
    assert "Telegram" in advanced


def test_kunden_pages_gate_by_module_on_marketing_hub():
    # Без inbox — вкладка Nachrichten скрыта; Kontakte видна.
    html = _render_marketing("crm", _fake_tenant(disabled=["inbox"]))
    assert "Nachrichten" not in html
    assert "Kontakte" in html
