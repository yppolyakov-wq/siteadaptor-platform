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


def test_hub_tabs_renders_main_tabs_only():
    # R2 (редизайн B): на странице — только контентные вкладки; advanced-состав
    # живёт подпунктами сайдбара (SM-4) и в палитре, ящика «Erweitert» нет.
    html = _render("catalog")
    for lbl in ("Produkte", "Kategorien"):
        assert lbl in html
    for lbl in ("Lager", "Kombi", "Import", "Einkauf"):
        assert lbl not in html, lbl


def test_catalog_hub_has_no_erweitert_drawer():
    """R2: ящик «Erweitert» снят со страниц (утверждённая структура —
    каждая страница живёт ровно в одном месте; SM-4-переписка)."""
    html = _render("catalog")
    assert "Erweitert" not in html


def test_moved_pages_anchor_mapping():
    """SM-4: подсветка якоря следует за переездами — отчёты под Verkäufe,
    site-страницы под Website; Abläufe остаётся вкладкой настроек."""
    from apps.core import nav_registry

    assert nav_registry.anchor_for("finance") == "board"
    assert nav_registry.anchor_for("analytics") == "board"
    assert nav_registry.anchor_for("seo") == "site"
    assert nav_registry.anchor_for("domains") == "site"
    assert nav_registry.anchor_for("media") == "site"
    assert nav_registry.anchor_for("ablaeufe") == "settings"


def test_hub_tabs_marks_exactly_one_active():
    html = _render("categories")  # Kategorien — контентная вкладка
    assert html.count('aria-selected="true"') == 1
    # R2: advanced-страница (Lager) вкладки на странице не имеет — «где я»
    # держит подпункт сайдбара (замок подсветки — test_w8_nav_registry).
    html2 = _render("stock")
    assert html2.count('aria-selected="true"') == 0


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
    """W-CL: board/календари/список покрыты сегментом ST-5b и единой страницей.
    X4 (осознанная переписка): события/туры переехали в хаб «Sortiment» —
    сущность продаётся, а сделки по ней живут вкладкой «Tickets» страницы
    Verkäufe; в board-хабе из главных записей остались только Aufträge."""
    html = _render_board("board", _fake_tenant())  # ничего не выключено
    for lbl in ("Board", "Bestellungen", "Termine", "Übernachtungen", "Veranstaltungen"):
        assert lbl not in html, lbl
    assert "Aufträge" in html


def test_board_hub_gates_inactive_modules():
    # Тенант без booking/stays — рабочие входы дня скрыты, Aufträge видна.
    tenant = _fake_tenant(disabled=["booking", "stays"])
    html = _render_board("jobs", tenant)
    assert "Tage blockieren" not in html
    assert "Check-ins" not in html
    assert "Aufträge" in html
    assert html.count('aria-selected="true"') == 1  # активна вкладка Aufträge


def test_board_hub_fail_open_without_request():
    # Без request/tenant в контексте (простой рендер) — гейт fail-open,
    # включая X4-гейт business_types (гастро-KDS показывается).
    html = _render_board("board")
    assert "Aufträge" in html
    # R2: KDS — advanced-запись, на странице больше не рендерится (вход —
    # подпункт сайдбара «Verkäufe»; X4-гейт business_types жив в реестре).
    assert "/kitchen/" not in html


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
    # SM-4 (решение владельца 2026-08-11, осознанная переписка): Finanzen/
    # Auswertungen — подпункты «Verkäufe», Domains/Medien — подпункты «Website»
    # в сайдбаре; из settings-хаба ушли.
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
    for gone in ("Finanzen", "Auswertungen", "Domains", "Medien"):
        assert gone not in html, gone
    # R2: ящика «Erweitert» нет — advanced-состав в сайдбаре и палитре.
    assert "Erweitert" not in html
    for lbl in ("Zusatzleistungen", "Funktionen", "Finder", "Hilfe"):
        assert lbl not in html, lbl


def test_settings_hub_primary_active_single():
    html = _render_settings("settings")
    assert html.count('aria-selected="true"') == 1  # активна одна прямая вкладка


def test_settings_hub_advanced_page_has_no_tab_highlight():
    # R2: advanced-страница (Funktionen) вкладки на странице не имеет —
    # подсветку держит подпункт сайдбара «Einstellungen».
    html = _render_settings("modules")
    assert "Erweitert" not in html
    assert html.count('aria-selected="true"') == 0


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
    # R2: ящика нет — Einlösen/Treuepunkte/Kanäle/Beiträge в сайдбаре Marketing.
    assert "Erweitert" not in html
    for lbl in ("Einlösen", "Treuepunkte", "Kanäle", "Beiträge"):
        assert lbl not in html, lbl
    # решение 4а (2026-08-06): Reservierungen — только вкладка Verkäufe, дубль убран
    assert "Reservierungen" not in html
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
