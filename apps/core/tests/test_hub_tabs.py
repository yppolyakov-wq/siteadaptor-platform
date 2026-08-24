"""Навигация кабинета: ОДНО меню — разделы сайдбара с подменю (R7-1).

История файла: S1/S2/S3 (хаб-табы) → W-CL → R2 (ящик «Erweitert» снят со
страниц) → **R7-1** (фидбэк владельца 2026-08-24 «по-прежнему на страницах
есть дубль меню; при нажатии на Продажи/Ассортимент должно открываться
подменю, и в нём уже всё»): таб-бары хабов на страницах СНЕСЕНЫ целиком
(тег `hub_tabs` и партиал `_hub_tabs.html` удалены, прецедент W-CL), состав
хабов живёт подменю раздела в сайдбаре и палитрой Ctrl+K.

Замки ниже сохраняют смысл прежних тестов тега, перенеся его на новую
поверхность: состав подменю, гейты модулей, owner-only, отсутствие дублей.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.core import modules, nav_registry


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(disabled=(), business_type="shop"):
    return SimpleNamespace(
        site_config={},
        disabled_modules=list(disabled),
        enabled_modules=[],
        business_type=business_type,
    )


def _menu(tenant=None):
    """{nav_key якоря: [подписи подпунктов]} — как видит владелец в сайдбаре."""
    items = modules.sidebar_nav(tenant or _tenant())
    return {it["nav_key"]: [str(c["label"]) for c in it["children"]] for it in items}


# --- R7-1: тег таб-бара мёртв -------------------------------------------------
def test_hub_tabs_tag_is_gone():
    """Дубль меню невозможен по построению: тега нет в библиотеке, партиала —
    в шаблонах (осознанный снос, прецедент classic_ui/W-CL)."""
    from pathlib import Path

    from apps.core.templatetags import cabinet

    assert not hasattr(cabinet, "hub_tabs")
    root = Path(__file__).resolve().parents[3]
    assert not (root / "templates" / "tenant" / "_hub_tabs.html").exists()
    hits = [p for p in (root / "templates").rglob("*.html") if "{% hub_tabs" in p.read_text()]
    assert hits == []


# --- S1: каталог свёрнут в один раздел ---------------------------------------
def test_catalog_nav_collapsed_to_one_hub():
    cat = modules.get_module("catalog")
    assert len(cat.nav_items) == 1  # 5 пунктов → 1 раздел
    assert cat.nav_items[0].nav_key == "catalog"


def test_sortiment_submenu_has_full_hub_content():
    """R7-1: в подменю раздела — ВЕСЬ состав его хабов (main + advanced),
    включая складскую группу: раньше main-часть жила таб-баром на странице."""
    kids = _menu()["sellables"]
    # SR-1: «Produkte» умер вместе со страницей (обзор Sortiment несёт товары).
    for lbl in ("Kategorien", "Lager", "Einkauf", "Kombi"):
        assert lbl in kids, lbl
    assert "Produkte" not in kids


def test_submenu_starts_with_section_overview():
    """Клик по разделу раскрывает меню, а не уводит на страницу — обзорная
    страница раздела обязана остаться достижимой ПЕРВЫМ подпунктом."""
    menu = modules.sidebar_nav(_tenant())
    for it in menu:
        if not it["children"]:
            continue
        first = it["children"][0]
        assert first["url_name"] == it["url_name"] and not first.get("query"), it["nav_key"]


def test_submenu_has_no_duplicate_entries():
    """«Nachrichten» вставлялась первой ради бейджа — после R7-1 она уже есть
    в составе хаба; дубля строки в меню быть не должно."""
    for nav_key, labels in _menu().items():
        assert len(labels) == len(set(labels)), (nav_key, labels)


def test_moved_pages_anchor_mapping():
    """SM-4: подсветка якоря следует за переездами — отчёты под Verkäufe,
    site-страницы под Website; Abläufe остаётся в настройках."""
    assert nav_registry.anchor_for("finance") == "board"
    assert nav_registry.anchor_for("analytics") == "board"
    assert nav_registry.anchor_for("seo") == "site"
    assert nav_registry.anchor_for("domains") == "site"
    assert nav_registry.anchor_for("media") == "site"
    assert nav_registry.anchor_for("ablaeufe") == "settings"


# --- S2: продажи одной поверхностью ------------------------------------------
def test_sales_nav_collapsed_into_verkauefe():
    for key in ("orders", "booking", "stays", "events", "jobs"):
        assert modules.get_module(key).nav_items == (), key
    assert str(modules.NAV_TASK_LABELS["board"]) == "Verkäufe"


def test_sales_submenu_gates_inactive_modules():
    """Тенант без booking/stays — рабочие входы дня скрыты, Aufträge видна."""
    kids = _menu(_tenant(disabled=["booking", "stays"]))["board"]
    assert "Tage blockieren" not in kids
    assert "Check-ins" not in kids
    assert "Aufträge" in kids


def test_kitchen_display_only_for_food_types():
    """X4: гастро-экраны — только гастро-типам (гейт business_types жив)."""
    shop = [c["url_name"] for c in modules.sidebar_nav(_tenant())[1]["children"]]
    assert "orders:kitchen" not in shop
    food = modules.sidebar_nav(_tenant(business_type="restaurant"))
    food_kids = [c["url_name"] for it in food for c in it["children"]]
    assert "orders:kitchen" in food_kids


# --- S3: настройки ------------------------------------------------------------
def test_settings_nav_collapsed_to_website_plus_hub():
    keys = [n.nav_key for n in modules.get_module("settings").nav_items]
    assert keys == ["site", "settings"]
    assert str(modules.NAV_TASK_LABELS["settings"]) == "Einstellungen"


def test_settings_submenu_lists_every_screen():
    """W9-1 «базовые + по типам» + R7-1: весь состав настроек — в одном
    подменю (прежде часть жила рядами табов, часть — ящиком)."""
    kids = _menu()["settings"]
    for lbl in (
        "Mein Geschäft",
        "Sprachen",
        "Recht & Steuern",
        "Zahlung & Lieferung",
        "Benachrichtigungen & Kanäle",
        "Abläufe",
        "Integrationen",
        "Abo & Rechnung",
        "Team & Zugriff",
        "Funktionen",
    ):
        assert lbl in kids, lbl
    # SM-4: отчёты/домены переехали в другие разделы — здесь их нет
    for gone in ("Finanzen", "Auswertungen", "Website & Domains", "Medien"):
        assert gone not in kids, gone


# --- S4a: маркетинг -----------------------------------------------------------
def test_marketing_nav_collapsed_to_hub():
    assert modules.get_module("promotions").nav_items != ()
    assert str(modules.NAV_TASK_LABELS["promotions"]) == "Marketing"
    for key in ("reviews", "loyalty", "publishing"):
        assert modules.get_module(key).nav_items == (), key
    crm_keys = [n.nav_key for n in modules.get_module("crm").nav_items]
    assert crm_keys == ["crm"]


def test_marketing_submenu_when_active_and_gated():
    kids = _menu()["promotions"]
    for lbl in ("Aktionen", "Bewertungen", "Kampagnen", "Gutscheine", "Kontakte", "Nachrichten"):
        assert lbl in kids, lbl
    # решение 4а (2026-08-06): Reservierungen — только вкладка Verkäufe
    assert "Reservierungen" not in kids
    off = _menu(_tenant(disabled=["publishing", "reviews"]))["promotions"]
    assert "Kanäle" not in off and "Beiträge" not in off and "Bewertungen" not in off
    assert "Aktionen" in off


# --- W11-1 (Р-2): хаб «Kunden» удалён ----------------------------------------
def test_kunden_hub_is_gone():
    assert "kunden" not in nav_registry.HUBS
    assert not any(e.hub == "kunden" for e in nav_registry.ENTRIES)
    for key in ("inbox", "telegram"):
        assert modules.get_module(key).nav_items == (), key


# --- X0: owner-only записи прячутся у сотрудников ----------------------------
@pytest.mark.django_db
def test_owner_only_entries_hidden_for_staff_in_menu_and_palette():
    """Смысл прежнего теста тега: сотрудник не видит owner-only экраны (Team/
    Abo/Recht — мидлварь W9-10 отдала бы 403). Проверяем на живых поверхностях:
    палитра Ctrl+K и подменю сайдбара."""
    from django.contrib.auth import get_user_model
    from django.template import Context, Template

    from apps.core.models import Membership
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(slug=f"r7-{uuid4().hex[:6]}", name="R7")
    user = get_user_model().objects.create_user(
        username=f"u-{uuid4().hex[:8]}", email=f"{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_STAFF)
    req = SimpleNamespace(tenant=t, user=user)
    html = Template("{% load cabinet %}{% nav_palette %}").render(Context({"request": req}))
    for lbl in ("Team &amp; Zugriff", "Abo &amp; Rechnung", "Recht &amp; Steuern"):
        assert lbl not in html, lbl
    assert "Sprachen" in html  # не-owner запись остаётся
