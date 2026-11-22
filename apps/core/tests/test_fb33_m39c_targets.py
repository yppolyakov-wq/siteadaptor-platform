"""FB-33 M3-9c: цели касания — окно блока без скриптов (44 px) и мелкие цели витрины (24 px).

№4: кнопки панели блока брали 40 px из `.ui-btn`; 44 px давало правило `.ui-bwin …`, а класс
`ui-bwin` вешает только `static/js/aufbau.js`. Теперь то же правило стоит и на самой панели
(`[data-schema-panel]`) — без правки шаблонов окна и их эталонов.

№6: ссылки подвала, «Alle anzeigen →», стрелки дня и месяца, «+ Mehr hinzufügen», «Herunterladen»,
«📅 Kalender», «💬 Eine Frage stellen» — не ниже 24 px (WCAG 2.2 2.5.8 AA); точка слайдера —
кнопка 24×24 с видимой точкой 8 px.

Высоту pytest не видит: здесь замок правил CSS и классов разметки, приёмка в браузере —
`scripts/fb33_m39c_targets_stand.py` (1440/390, de/ru, без JS и с JS).
"""

import datetime as dt
import re
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

ROOT = Path(__file__).resolve().parents[3]
CSS = (ROOT / "static" / "src" / "app.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "templates" / "storefront"

#: класс минимальной цели витрины (WCAG 2.2 2.5.8 AA)
TARGET = "min-h-[24px]"
#: цели окна блока — одни и те же элементы в окне со скриптами и в панели без них
WINDOW_TARGETS = (
    r':is\(button, summary, select, \[role="tab"\], a\.ui-btn\) \{ min-height: 2\.75rem; \}'
)


# --- №4: окно блока без скриптов ----------------------------------------------------------


def _components_layer() -> str:
    return CSS[CSS.index("@layer components {") :]


def test_panel_without_scripts_has_the_44px_rule():
    """Панель блока без скриптов — те же 44 px, что окно со скриптами."""
    assert re.search(r"^\s*\[data-schema-panel\] " + WINDOW_TARGETS, _components_layer(), re.M)


def test_window_with_scripts_keeps_its_44px_rule():
    assert re.search(r"^\s*\.ui-bwin " + WINDOW_TARGETS, _components_layer(), re.M)


def test_panel_rule_touches_only_the_block_panel():
    """Обёртка одна: `aside#schema-panel` в «Seitenaufbau» — правило не уходит на другие экраны."""
    hits = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "templates").rglob("*.html")
        if re.search(r"<[a-z]+\b[^>]*\sdata-schema-panel[\s>]", p.read_text(encoding="utf-8"))
    ]
    assert hits == ["templates/tenant/site_schema.html"]


def test_c5_stand_checks_the_apply_button_too():
    """Стенд «Felder» корзины больше не исключает «Übernehmen» из проверки ≥ 44 px."""
    src = (ROOT / "scripts" / "fb33_m2i34_c5_window_stand.py").read_text(encoding="utf-8")
    small = src[src.index("const small") : src.index("const checked")]
    assert "data-schema-apply" not in small


# --- №6: точки слайдера -------------------------------------------------------------------


def _rule(selector: str) -> str:
    m = re.search(r"^" + re.escape(selector) + r" \{([^}]*)\}", CSS, re.M)
    assert m, f"нет правила {selector}"
    return m.group(1)


def test_slider_dot_is_a_24px_target_with_an_8px_dot():
    button = _rule(".sf-slider-dot")
    assert "width: 1.5rem" in button and "height: 1.5rem" in button
    assert "background: transparent" in button
    dot = _rule(".sf-slider-dot::before")
    assert "width: .5rem" in dot and "height: .5rem" in dot
    assert "var(--accent" in _rule(".sf-slider-dot.is-on::before")


def test_slider_dots_are_updated_in_place_and_marked_current():
    """Ревью a11y стопки 8: точки пересоздавались на каждый `scroll` — точка в фокусе исчезала,
    фокус падал в body (2.4.3). Теперь кнопки пересоздаются только при смене числа страниц,
    активная отмечена `aria-current`. Поведение (фокус после Enter) мерит стенд."""
    js = (ROOT / "templates/storefront/_slider_script.html").read_text(encoding="utf-8")
    body = js[js.index("function renderDots()") : js.index("function go(")]
    assert "dots.children.length !== n" in body
    # полная пересборка — только под проверкой числа страниц (первое обнуление — ветка «одна»)
    assert body.index("dots.children.length !== n") < body.rindex('dots.innerHTML = ""')
    assert body.count('dots.innerHTML = ""') == 2
    assert "aria-current" in body


def test_dark_theme_keeps_the_active_dot_accented():
    assert ".dark .sf-slider-dot:not(.is-on)::before" in CSS
    assert ".dark .sf-slider-dot::before" not in CSS


def test_panel_rule_covers_link_buttons_and_says_it_wins_over_utilities():
    """Ревью a11y: правило панели (0,2,0) сильнее утилиты `min-h-[…]` (0,1,0) — комментарий
    говорил обратное; ссылка-кнопка «Abbrechen» (`a.ui-btn`) оставалась 40 px."""
    for scope in (".ui-bwin", "[data-schema-panel]"):
        assert f'{scope} :is(button, summary, select, [role="tab"], a.ui-btn)' in CSS
    assert "по-прежнему сильнее" not in CSS


# --- №6: ссылки витрины -------------------------------------------------------------------


class _Links(HTMLParser):
    """Ссылки и кнопки разметки: `(атрибуты, текст)`; `scope` — только внутри этого тега."""

    def __init__(self, scope: str | None = None):
        super().__init__()
        self.scope, self.depth, self.open, self.found = scope, 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag == self.scope:
            self.depth += 1
        if tag in ("a", "button") and (self.depth or not self.scope):
            self.open = [dict(attrs), ""]

    def handle_data(self, data):
        if self.open:
            self.open[1] += data

    def handle_endtag(self, tag):
        if tag in ("a", "button") and self.open:
            self.found.append((self.open[0], " ".join(self.open[1].split())))
            self.open = None
        if tag == self.scope:
            self.depth -= 1


def _links(html: str, scope: str | None = None):
    parser = _Links(scope)
    parser.feed(html)
    return parser.found


def _small(links):
    return [text for attrs, text in links if TARGET not in (attrs.get("class") or "").split()]


@pytest.fixture
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _home(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _shop(slug: str, **site_config):
    cat = Category.objects.create(name={"de": "Brot"}, slug="brot", sort_order=1, is_active=True)
    for name in ("Roggenbrot", "Bauernbrot"):
        Product.objects.create(
            name={"de": name}, base_price=Decimal("3.20"), category=cat, is_active=True
        )
    tenant = TenantFactory(
        slug=slug,
        name="M39C",
        disabled_modules=[],
        address="Markt 1, 42781 Haan",
        contact_phone="+49 2129 1234",
        contact_email="hallo@m39c.test",
        map_url="https://maps.example/m39c",
    )
    tenant.site_config = site_config
    tenant.save(update_fields=["site_config"])
    return tenant


@pytest.mark.django_db
def test_footer_links_are_24px_targets_with_columns(_urlconf):
    page = {"label": "Über uns", "type": "page", "target": "about"}
    tenant = _shop("m39cfoot", menus={"footer": {"columns": [{"label": "Shop", "items": [page]}]}})
    links = _links(_home(tenant), scope="footer")
    texts = [t for _a, t in links]
    assert "Über uns" in texts and "+49 2129 1234" in texts and "hallo@m39c.test" in texts
    assert any("Impressum" in t or "Imprint" in t for t in texts)
    assert _small(links) == []


@pytest.mark.django_db
def test_footer_links_are_24px_targets_without_columns(_urlconf):
    links = _links(_home(_shop("m39cplain")), scope="footer")
    assert any("+49 2129 1234" in t for _a, t in links) and len(links) >= 5
    assert _small(links) == []


@pytest.mark.django_db
def test_home_section_show_all_link_is_a_24px_target(_urlconf):
    sections = [{"key": "products", "enabled": True}, {"key": "categories", "enabled": True}]
    sections += [
        {"key": k, "enabled": False}
        for k, _l, _on in siteconfig.SECTIONS
        if k not in ("products", "categories")
    ]
    html = _home(_shop("m39chome", sections=sections))
    # кнопка-пилюля под сеткой (`_grid_more.html`, класс sf-more) высокая сама — не текстовая
    more = [
        (a, t)
        for a, t in _links(html, scope="main")
        if t.endswith("→") and "sf-more" not in a.get("class", "")
    ]
    assert len(more) == 2, "на главной нет ссылок «Alle anzeigen →» у товаров и категорий"
    assert _small(more) == []


def test_month_arrows_are_24px_targets():
    html = render_to_string(
        "storefront/_booking_calendar.html",
        {
            "cal_show_prev": True,
            "cal_show_next": True,
            "cal_prev": dt.date(2026, 10, 1),
            "cal_next": dt.date(2026, 12, 1),
            "cal_first": dt.date(2026, 11, 1),
            "day": dt.date(2026, 11, 22),
            "cal_weeks": [],
        },
    )
    arrows = [(a, t) for a, t in _links(html) if t in ("‹", "›")]
    assert len(arrows) == 2 and _small(arrows) == []
    assert all("min-w-[24px]" in a["class"].split() for a, _t in arrows)


#: шаблон → признак ссылки в исходнике (текст между `<a …>` и `</a>`); страницы, которым для
#: рендера нужен целый бизнес (запись, номер, событие, акция), — приёмка стендом
SOURCE_LINKS = [
    ("_service_slots_box.html", "prev_day|date"),
    ("_service_slots_box.html", "next_day|date"),
    ("_booking_slots_box.html", "prev_day|date"),
    ("_booking_slots_box.html", "next_day|date"),
    ("sections/_promotions.html", '{% trans "Alle Aktionen" %} →'),
    ("sections/_team.html", '{% trans "Ganzes Team" %} →'),
    ("sections/_gallery.html", '{% trans "Alle Fotos" %} →'),
    ("sections/_reviews.html", '{% trans "Alle Bewertungen" %} →'),
    ("sections/_block_list.html", "{% endblocktrans %} →"),
    ("booking_index.html", '{% trans "Buy a multi-visit card" %} →'),
    ("service_index.html", '{% trans "Buy a multi-visit card" %} →'),
    ("_booking_info.html", '{% trans "Open in maps" %} →'),
    ("_booking_info.html", '{% trans "Contact" %} →'),
    ("_booking_info.html", "tenant.public_phone }}"),
    ("_booking_info.html", "WhatsApp"),
    ("cart.html", '{% trans "Add more" %}'),
    ("event_index.html", '{% trans "Calendar" %}'),
    ("event_calendar.html", '{% trans "Subscribe (iCal)" %}'),
    ("event_detail.html", '{% trans "Ask a question" %}'),
    ("stay_detail.html", '{% trans "Ask a question" %}'),
    ("product_detail.html", '{% trans "Ask a question about this product" %}'),
    ("promotion_detail.html", '{% trans "Download" %}'),
    ("promotion_detail.html", '{% trans "Alle anzeigen" %} →'),
    ("promotions_list.html", '{% trans "Alle anzeigen" %} →'),
    ("composition/_shelves.html", '{% trans "Alle anzeigen" %} →'),
    ("products.html", '{% trans "View all" %} →'),
    *[
        (f"sections/_{key}.html", '{% trans "View all" %} →')
        for key in ("products", "categories", "tours", "blog", "services", "stay_rooms", "events")
    ],
]
_ANCHOR = re.compile(r"<a\b([^>]*)>((?:(?!</a>).)*)</a>", re.S)


@pytest.mark.parametrize(("template", "marker"), SOURCE_LINKS)
def test_storefront_link_is_a_24px_target(template, marker):
    src = (TEMPLATES / template).read_text(encoding="utf-8")
    found = [attrs for attrs, body in _ANCHOR.findall(src) if marker in body]
    assert found, f"{template}: ссылка «{marker}» не найдена"
    small = [attrs.strip()[:80] for attrs in found if TARGET not in attrs]
    assert small == []
