"""FB-33 M5b-2 W1: список «Seitenaufbau» по V4 — ★-строка страницы и серая метка заголовка.

План — `docs/fb33-stack10-plan-2026-11-22.md` §0 (V4), §2.A W1, §4 таблица A, §8.1 (architect:
A-M4, A-M5, A-M6) и §8.2 (a11y: Y-H1, Y-H2, Y-H3). Правило владельца 2026-11-22:

- `site_schema.page_row_ref`: главная — «Banner», как было; любая другая страница с настройками
  типа, «Design» или своим заголовком (`page_title.HEAD_HOSTS`) — ★-строка `__page`; ★ основной
  список больше не носитель;
- ★-строка стоит первой после «Kopfzeile & Menü»: ссылка ≥ 44 px, `★` скрыт от чтения, после
  названия sr «, feste Position»; без ручки, «⋯» и `data-schema-pinned`;
- строки «Seitentitel» (`__title`) больше нет: на её месте — серая метка «Überschrift der Seite ·
  in ★ bearbeiten» (только когда над заголовком стоит включённый блок), без атрибутов строки —
  не выбирается, не двигается, не цель броска;
- старые ссылки `?block=__title` — 302 на окно ★-строки, вкладка «Seite».
"""

import copy
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection

from apps.core import aufbau_draft, page_title, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PAGE = site_schema.PAGE_REF
TITLE = page_title.TITLE_REF
#: пять типов бизнеса стенда владельца (как замки M5b-1)
TYPES = ("online_shop", "restaurant", "friseur", "hotel", "events")


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="friseur", config=None, locales=None):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config=copy.deepcopy(config) if config is not None else {},
    )
    if locales is not None:
        tenant.enabled_locales = locales
        tenant.save()
    connection.tenant = tenant
    return tenant


def _map(html: str) -> str:
    """Колонка схемы (без панели окна)."""
    start = html.index("data-schema-blocks")
    return html[start : html.index("data-schema-add", start)]


def _blocks_attr(html: str) -> list[str]:
    return re.findall(r'data-schema-block="([^"]*)"', _map(html))


def _oracle_v4(tenant, code: str, blocks: list[dict]) -> str:
    """Правило владельца V4 (2026-11-22), дословно по плану §2.A W1 п.1."""
    try:
        has = bool(site_schema.setting_codes(tenant, code)) or bool(
            site_schema.design_codes(tenant, code)
        )
    except site_schema.SchemaError:
        return ""
    host = site_schema.host_for(code)
    if not (has or host in page_title.HEAD_HOSTS):
        return ""
    if code == "home":
        return "hero" if any(b["ref"] == "hero" for b in blocks) else PAGE
    return PAGE


# ───────────── правило V4 ─────────────


@pytest.mark.parametrize("bt", TYPES)
def test_page_row_ref_follows_v4(bt):
    tenant = _tenant(bt)
    saved = siteconfig.normalize(tenant.site_config)
    rows = [r for _l, items in site_schema.type_groups(tenant, saved) for r in items]
    browser = Browser(tenant)
    for row in rows:
        blocks = site_schema.blocks_for(saved, row.code, host=row.host or None)
        want = _oracle_v4(tenant, row.code, blocks)
        assert site_schema.page_row_ref(tenant, row.code, blocks) == want, (bt, row.code)
        assert want != siteconfig.MAIN_LIST_KEY, "★ основной список больше не носитель"
        html = browser.get(f"?seite={row.code}")
        assert (PAGE in _blocks_attr(html)) == (want == PAGE), (bt, row.code)


def test_static_rule_has_page_row_on_list_pages():
    """Адрес настроек типа (без тенанта): у списков и форм — ★-строка, у главной — «Banner»."""
    for code in ("catalog", "services", "promos", "text", "product", "contact"):
        assert site_schema.page_row_ref(None, code) == PAGE, code
    assert site_schema.page_row_ref(None, "home") == "hero"


@pytest.mark.parametrize(("bt", "code"), [
    ("online_shop", "catalog"),
    ("friseur", "services"),
    ("friseur", "contact"),
    ("online_shop", "product"),  # было и до W1
])  # fmt: skip
def test_star_row_first_on_list_pages(bt, code):
    html = Browser(_tenant(bt)).get(f"?seite={code}")
    refs = _blocks_attr(html)
    assert refs[0] == PAGE, refs
    assert refs.count(PAGE) == 1
    assert TITLE not in refs, "строки «Seitentitel» больше нет"
    first = _map(html).index("<li")
    assert "Kopfzeile & Menü" in _map(html)[first : _map(html).index(f'"{PAGE}"')]


def test_star_row_markup():
    """Y-H3: ★-строка — ссылка в `li`, ≥ 44 px; ★ скрыт от чтения, после названия sr «, feste
    Position»; сводка внутри ссылки; без ручки, «⋯» и `data-schema-pinned`."""
    html = Browser(_tenant()).get("?seite=services")
    m = re.search(r'<li><a [^>]*data-schema-block="__page"[^>]*>(.*?)</a></li>', _map(html), re.S)
    assert m, "ссылка ★-строки — прямо в li"
    link, inner = m.group(0), m.group(1)
    assert "min-h-[44px]" in link
    assert '<span aria-hidden="true">★</span>' in inner
    assert re.search(
        r"Seitentitel und Seite</span>\s*<span class=\"sr-only\">, feste Position</span>", inner
    )
    assert re.search(r'<span class="[^"]*break-words[^"]*">Standard</span>', inner)
    assert "data-schema-pinned" not in link and "data-schema-drag" not in link
    assert "⋮⋮" not in inner and "🔒" not in inner


@pytest.mark.parametrize(("bt", "code", "label", "summary"), [
    ("friseur", "services", "Seitentitel und Seite", "Standard"),
    ("friseur", "contact", "Seitentitel und Seite", "Standard"),
    ("online_shop", "catalog", "Einstellungen der Seite", None),
    ("online_shop", "lookbook", "Einstellungen der Seite", None),
    ("online_shop", "promo_group", "Einstellungen der Seite", None),
    ("online_shop", "product", "Einstellungen der Seite", "Titel = Name des Eintrags"),
    ("online_shop", "text", "Einstellungen der Seite", None),  # было и до W1
])  # fmt: skip
def test_star_row_labels(bt, code, label, summary):
    html = Browser(_tenant(bt)).get(f"?seite={code}")
    m = re.search(r'data-schema-block="__page"[^>]*>(.*?)</a>', _map(html), re.S)
    assert m and f"{label}</span>" in m.group(1), code
    if summary:
        assert f">{summary}</span>" in m.group(1), code


def test_star_row_summary_is_own_title_in_quotes():
    tenant = _tenant(config={"page_titles": {"services": {"title": "Unsere Leistungen"}}})
    html = Browser(tenant).get("?seite=services")
    m = re.search(r'data-schema-block="__page"[^>]*>(.*?)</a>', _map(html), re.S)
    assert ">„Unsere Leistungen“</span>" in m.group(1)


# ───────────── серая метка «Überschrift der Seite» ─────────────


def _hint(html: str) -> str:
    m = re.search(r"<li[^>]*data-schema-title-hint[^>]*>.*?</li>", _map(html), re.S)
    return m.group(0) if m else ""


def test_hint_after_page_head_on_lists():
    html = Browser(_tenant()).get("?seite=services")
    hint = _hint(html)
    assert hint and "Überschrift der Seite" in hint
    cols = _map(html)
    assert cols.index('data-schema-block="page_head"') < cols.index("data-schema-title-hint")
    assert cols.index("data-schema-title-hint") < cols.index('data-schema-block="groups"')


def test_no_hint_without_block_above():
    """Макет: «Ohne „Fotos der Seite“ steht die Überschrift ganz oben — dann gibt es keinen
    Hinweis.» Скрытая фото-шапка — тоже без метки; форма без блока сверху — без метки."""
    saved = siteconfig.normalize(_tenant().site_config)
    blocks = copy.deepcopy(site_schema.blocks_for(saved, "services"))
    assert site_schema.title_hint_at("services", blocks) is not None
    for b in blocks:
        if b["key"] == "page_head":
            b["enabled"] = False  # скрытая фото-шапка (там, где её можно скрыть)
    assert site_schema.title_hint_at("services", blocks) is None
    no_head = [b for b in blocks if b["key"] != "page_head"]
    assert site_schema.title_hint_at("services", no_head) is None
    assert not _hint(Browser(_tenant()).get("?seite=contact"))
    assert not _hint(Browser(_tenant("online_shop")).get("?seite=catalog")), "нет заголовка"


def test_hint_on_form_with_block_above():
    cfg = {"page_blocks": {"message": [
        {"key": "text", "id": "t1", "enabled": True, "data": {"title": "So läuft es ab"}},
        {"key": "form"},
    ]}}  # fmt: skip
    html = Browser(_tenant(config=cfg)).get("?seite=contact")
    cols = _map(html)
    assert _hint(html)
    assert cols.index('data-schema-block="t1"') < cols.index("data-schema-title-hint")
    assert cols.index("data-schema-title-hint") < cols.index('data-schema-block="form"')


def test_hint_markup_is_not_a_row():
    """Y-H2: метка — не строка: нет `data-schema-block/-drag/-pinned/aria-current`; одна ссылка
    ≥ 44 px на окно ★-строки, вкладка «Seite»."""
    hint = _hint(Browser(_tenant()).get("?seite=services"))
    for attr in ("data-schema-block", "data-schema-drag", "data-schema-pinned", "aria-current"):
        assert attr not in hint, attr
    links = re.findall(r'<a [^>]*href="([^"]+)"[^>]*>', hint)
    assert len(links) == 1
    query = parse_qs(urlsplit(links[0].replace("&amp;", "&")).query)
    assert query["block"] == [PAGE] and query["tab"] == ["seite"] and query["seite"] == ["services"]
    assert "min-h-[44px]" in re.search(r"<a [^>]*>", hint).group(0)


def test_hint_link_underlined():
    """Y-H1 (WCAG 1.4.1): ссылка метки и «Menü bearbeiten» подчёркнуты."""
    html = Browser(_tenant()).get("?seite=services")
    assert re.search(r'<a [^>]*class="[^"]*\bunderline\b', _hint(html))
    menu = re.search(r"<a [^>]*>Menü bearbeiten</a>", html)
    assert menu and re.search(r'class="[^"]*\bunderline\b', menu.group(0))


def _accessible(html: str) -> str:
    html = re.sub(r'<span aria-hidden="true">.*?</span>', " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _seen(html: str) -> str:
    html = re.sub(r'<span class="sr-only">.*?</span>', " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def test_hint_link_name_contains_visible_text():
    """Y-H1 (WCAG 2.5.3): видимое «in ★ bearbeiten» — слова видимого текста входят в доступное
    имя по порядку; ★ скрыт; имя называет окно «Seitentitel und Seite»."""
    hint = _hint(Browser(_tenant()).get("?seite=services"))
    link = re.search(r"<a [^>]*>(.*?)</a>", hint, re.S).group(1)
    seen = [w for w in _seen(link).split() if w != "★"]
    name = _accessible(link)
    assert seen == ["in", "bearbeiten"], seen
    assert re.search(r"\bin\b.*\bbearbeiten\b", name)
    assert "„Seitentitel und Seite“" in name and "★" not in name
    assert '<span aria-hidden="true">★</span>' in link


def test_hint_not_in_blocks():
    """Y-H2 / A-M4: метки нет в строках `blocks_for` (7 вызывающих, стенд владельца) — она
    считается функцией `title_hint_at` и вставляется только в разметку экрана."""
    saved = siteconfig.normalize(_tenant().site_config)
    for code in ("services", "contact", "promos", "gallery"):
        blocks = site_schema.blocks_for(saved, code)
        assert TITLE not in [b["ref"] for b in blocks], code
        assert all(b["key"] != "page_title" for b in blocks), code
    blocks = site_schema.blocks_for(saved, "services")
    at = site_schema.title_hint_at("services", blocks)
    assert at == [b["key"] for b in blocks].index("page_head") + 1
    assert site_schema.title_hint_at("contact", site_schema.blocks_for(saved, "contact")) is None
    assert site_schema.title_hint_at("catalog", site_schema.blocks_for(saved, "catalog")) is None


def test_hint_not_movable():
    """Y-H2: метка и ★-строка — не цели перестановки."""
    saved = siteconfig.normalize(_tenant().site_config)
    items = copy.deepcopy(siteconfig.page_rows(saved, "services"))
    for value in (f"before:{TITLE}", f"after:{TITLE}", f"before:{PAGE}", f"after:{PAGE}"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.mutate(items, "services", "move", "groups", value=value)
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "services", "move", PAGE, value="after:groups")


def test_move_neighbors_skip_star():
    """Y-H2: первый блок под ★-строкой не «двигается выше» неё; бросок до ★ — отказ, черновика
    нет."""
    tenant = _tenant()
    saved = siteconfig.normalize(tenant.site_config)
    blocks = site_schema.blocks_for(saved, "services")
    first = next(b for b in blocks if b["enabled"] and not b["fixed"])
    assert first["can_up"] is False
    b = Browser(tenant)
    _resp, msgs = b.post(seite="services", op="move", ref="groups", value=f"before:{PAGE}")
    assert "Diese Änderung ist hier nicht möglich." in msgs
    assert "services" not in (b.session.get(aufbau_draft.SESSION_KEY) or {}), "отказ не пишет"


# ───────────── старые ссылки `?block=__title` ─────────────


@pytest.mark.parametrize(("bt", "code", "page"), [
    ("friseur", "services", True),
    ("friseur", "contact", True),
    ("online_shop", "catalog", True),
    ("online_shop", "product", True),
    ("online_shop", "confirmation", False),
    ("online_shop", "gibtsnicht", False),
], ids=["services", "anfrage", "catalog", "product", "no-page-row", "junk"])  # fmt: skip
def test_old_title_link_redirects(bt, code, page):
    """A-M5: 302 на окно ★-строки, вкладка «Seite»; `ansicht`, `wopen`, `sprache` остаются,
    `entfernen`, `offen`, чужая вкладка — снимаются; нет ★-строки — страница без блока."""
    b = Browser(_tenant(bt))
    req = b._request("get", query=f"?seite={code}&block={TITLE}&tab=texte&ansicht=telefon"
                     "&wopen=openA1&sprache=en&entfernen=1&offen=service_list_layout")  # fmt: skip
    from apps.core.site_schema_views import site_schema_view

    resp = site_schema_view(req)
    assert resp.status_code == 302
    url = urlsplit(resp["Location"])
    query = parse_qs(url.query)
    seite = code if code != "gibtsnicht" else "home"
    assert query.pop("seite") == [seite]
    assert "entfernen" not in query and "offen" not in query
    if page:
        assert query == {"block": [PAGE], "tab": ["seite"], "ansicht": ["telefon"],
                         "wopen": ["openA1"], "sprache": ["en"]}  # fmt: skip
        assert url.fragment == "schema-panel"
    else:
        assert query == {"ansicht": ["telefon"]}


def test_old_title_post_lands_on_page_row():
    """Открытое до деплоя окно «Seitentitel» шлёт `ref=__title` — правка идёт тем же писателем,
    возврат — на окно ★-строки."""
    b = Browser(_tenant())
    resp, _msgs = b.post(seite="services", ref=TITLE, op="update", panel_present="1",
                         f_title="Termine", wopen="openA1")  # fmt: skip
    query = parse_qs(urlsplit(resp["Location"]).query)
    assert query["block"] == [PAGE]
    draft = b.session[aufbau_draft.SESSION_KEY]["services"]
    assert draft["title"] == {"title": "Termine"}
    assert set(draft[aufbau_draft.WINDOW_KEY]) == {PAGE}
