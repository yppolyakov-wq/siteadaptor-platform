"""FB-33 M5b-2 W2: имя главного списка, обычная строка, плашка «Hauptliste», мёртвое снято.

План — `docs/fb33-stack10-plan-2026-11-22.md` §2.A W2, §4 таблица A (№2, №4, №13, №16), §8.1
(architect A-M3) и §8.2 (a11y Y-M4, Y-L1, Y-L5). Решение владельца 2026-11-22
(`project-memory.md` §1 «Решения владельца стопки 10»):

- имя главного списка — как у блока «Liste» той же сущности: `list_blocks.source_label`
  источника хоста («Leistungen», «Blog», «Produkte»…); своего реестра имён нет, свои имена —
  только у Team, Galerie, Merkzettel, Lookbook; «Menü-Pakete» у гастро — через тенант;
- строка главного списка — обычная (без ★ и покраски индиго); сводка «Hauptliste · <вид>»
  (разделитель — в сводке, не в имени); признак `main` и запреты (скрыть, удалить) остаются;
- в окне главного списка — плашка «Hauptliste» текстом и фраза «Die Hauptliste lässt sich
  nicht ausblenden oder entfernen.»;
- мёртвое: `title_row`, подпись «Darstellung, Kartenform, Textbreite»; `TITLE_REF` — только в
  псевдониме (`site_schema.page_ref`, переименование старой сессии) и `whole_page_refs`.
"""

import copy
import pathlib
import re

import polib
import pytest
from django.db import connection
from django.utils import translation

from apps.core import list_blocks, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]
LANGS = ("de", "en", "ru", "tr", "uk")
MAIN = siteconfig.MAIN_LIST_KEY
#: оракул: источник блока «Liste» той же сущности, что главный список хоста
SOURCE_OF = {
    "catalog": "products",
    "category": "products",
    "promos": "promotions",
    "promo_group": "promotions",
    "services": "services",
    "stay_rooms": "stays",
    "events": "events",
    "tours": "tours",
    "combos": "combos",
    "blog": "blog",
    "reviews": "reviews",
}
#: у этих списков источника «Liste» нет — своё имя (решение владельца)
OWN_NAMES = {"team": "Team", "gallery": "Fotos", "wishlist": "Merkzettel", "lookbook": "Looks"}
NEW_MSGIDS = (
    "Die Hauptliste lässt sich nicht ausblenden oder entfernen.",
    "Blöcke davor stehen über der Liste, danach unter ihr.",  # W3: строка Студии
)
DEAD_MSGIDS = (
    "Darstellung, Kartenform, Textbreite",
    # W3: «как выглядит список» строки Студии — теперь ссылка на окно ★-строки
    "Blöcke davor stehen über der Liste, danach unter ihr. Wie die Liste aussieht, stellen "
    "Sie oben bei dieser Seite ein.",
)


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
    start = html.index("data-schema-blocks")
    return html[start : html.index("data-schema-add", start)]


def _row(html: str, ref: str) -> tuple[str, str]:
    """(открывающий тег, содержимое) ссылки строки `ref` в колонке схемы."""
    m = re.search(rf'(<a [^>]*data-schema-block="{ref}"[^>]*>)(.*?)</a>', _map(html), re.S)
    assert m, ref
    return m.group(1), m.group(2)


# ───────────── имя главного списка ─────────────


def test_main_list_name_is_source_label():
    """A-M3: имя = `source_label` источника хоста; свои — только Team/Galerie/Merkzettel/
    Lookbook; оракул покрывает ровно `MAIN_LIST_HOSTS`; хосты категории и группы акций — по
    префиксу."""
    assert set(SOURCE_OF) | set(OWN_NAMES) == set(siteconfig.MAIN_LIST_HOSTS)
    with translation.override("de"):
        for host, source in SOURCE_OF.items():
            assert site_schema.main_list_name(host) == list_blocks.source_label(source), host
        for host, name in OWN_NAMES.items():
            assert site_schema.main_list_name(host) == name, host
        assert site_schema.main_list_name(siteconfig.CATEGORY_HOST_PREFIX + "brot") == "Produkte"
        group = siteconfig.PROMO_GROUP_HOST_PREFIX + "0" * 32
        assert site_schema.main_list_name(group) == "Aktionen"
        assert site_schema.main_list_name("services") == "Leistungen"
        assert site_schema.main_list_name("blog") == "Blog"
        assert site_schema.main_list_name("combos") == "Sets & Pakete"
        gastro = _tenant("restaurant")
        assert site_schema.main_list_name("combos", gastro) == "Menü-Pakete"
        assert site_schema.main_list_name("combos", _tenant("online_shop")) == "Sets & Pakete"


def test_main_row_label_in_screen_gastro():
    """«Menü-Pakete» у гастро — подпись ставит вьюха (у `blocks_for` тенанта нет)."""
    html = Browser(_tenant("restaurant")).get("?seite=combos")
    _tag, inner = _row(html, MAIN)
    assert ">Menü-Pakete</span>" in inner


@pytest.mark.parametrize(("bt", "code", "name"), [
    ("friseur", "services", "Leistungen"),
    ("online_shop", "catalog", "Produkte"),
    ("online_shop", "promos", "Aktionen"),
    ("hotel", "stays", "Zimmer"),
    ("friseur", "gallery", "Fotos"),
    ("online_shop", "wishlist", "Merkzettel"),
    ("friseur", "reviews", "Bewertungen"),
])  # fmt: skip
def test_main_row_is_plain_row(bt, code, name):
    """Y-L5: имя без ★ и без «Hauptliste»; сводка «Hauptliste[ · <вид>]»; покраски индиго нет
    (обычная строка); признак `main` остаётся (не скрывается, «⋯» без «Ausblenden»)."""
    html = Browser(_tenant(bt)).get(f"?seite={code}")
    tag, inner = _row(html, MAIN)
    assert f'<span class="block font-semibold">{name}</span>' in inner
    assert "★" not in inner
    summary = re.search(
        r'<span class="block text-xs text-gray-600 break-words">(.*?)</span>', inner
    )
    assert summary and summary.group(1).startswith("Hauptliste"), inner
    assert "bg-indigo-50" not in tag and "border-indigo-400" not in tag
    assert "border-gray-500 bg-white" in tag


def test_main_row_summary_names_current_view():
    """Вид — из уже заполненных `mainview` (второго списка видов нет)."""
    tenant = _tenant("online_shop")
    saved = siteconfig.normalize(tenant.site_config)
    blocks = site_schema.blocks_for(saved, "catalog")
    main = next(b for b in blocks if b.get("main"))
    current = next(
        str(lab) for v, lab, _h, _t in main["mainview"]["choices"]
        if v == main["mainview"]["value"]
    )  # fmt: skip
    assert main["summary"] == f"Hauptliste · {current}"
    services = site_schema.blocks_for(siteconfig.normalize(_tenant().site_config), "services")
    assert next(b for b in services if b.get("main"))["summary"] == "Hauptliste"


def test_no_star_literal_in_row_labels():
    """Ни одна подпись строки схемы не несёт ★ (★ есть только у строки страницы `__page`,
    в шаблоне, скрытой от чтения); в коде подписей нет литерала «★ »."""
    for bt in ("online_shop", "restaurant", "friseur", "hotel", "events"):
        tenant = _tenant(bt)
        saved = siteconfig.normalize(tenant.site_config)
        for _label, items in site_schema.type_groups(tenant, saved):
            for row in items:
                for b in site_schema.blocks_for(saved, row.code, host=row.host or None):
                    assert "★" not in str(b.get("label") or ""), (bt, row.code, b["ref"])
    src = (ROOT / "apps" / "core" / "site_schema.py").read_text(encoding="utf-8")
    assert not re.search(r"""f["']★""", src), "подпись строки с ★"
    assert 'removeprefix("★ ")' not in (ROOT / "apps/core/page_window.py").read_text()


# ───────────── окно главного списка: плашка «Hauptliste» ─────────────


@pytest.mark.parametrize(("bt", "code"), [("friseur", "services"), ("online_shop", "catalog")])
def test_main_row_badge_text(bt, code):
    """Y-M4: видимая плашка «Hauptliste» текстом и причина «нельзя скрыть»; у других строк и у
    ★-строки страницы плашки нет."""
    b = Browser(_tenant(bt))
    panel = _panel(b.get(f"?seite={code}&block={MAIN}"))
    m = re.search(r'<span class="ui-badge ui-tone-run"[^>]*>(.*?)</span>', panel)
    assert m and m.group(1) == "Hauptliste", panel[:600]
    assert "Die Hauptliste lässt sich nicht ausblenden oder entfernen." in panel
    head = panel[: panel.index("</h2>")]
    assert "★" not in head or '<span aria-hidden="true">★</span>' in head
    page = _panel(b.get(f"?seite={code}&block={site_schema.PAGE_REF}"))
    assert "Die Hauptliste lässt sich" not in page


def test_star_row_labels_ru():
    """Имена и плашка — переводы по ключу (свежие `.mo`), тенант de+ru."""
    tenant = _tenant(locales=["de", "ru"])
    with translation.override("ru"):
        assert site_schema.main_list_name("services") == "Услуги"
        assert site_schema.main_list_name("team") == "Команда"
        services = site_schema.blocks_for(siteconfig.normalize(tenant.site_config), "services")
        main = next(b for b in services if b.get("main"))
        assert main["label"] == "Услуги" and main["summary"] == "Основной список"
        panel = _panel(Browser(tenant).get(f"?seite=services&block={MAIN}"))
    assert "Основной список нельзя скрыть или удалить." in panel


# ───────────── переводы и мёртвый код ─────────────


def _po(lang):
    return polib.pofile(str(ROOT / "locale" / lang / "LC_MESSAGES" / "django.po"))


@pytest.mark.parametrize("lang", LANGS)
def test_new_msgids_in_all_po(lang):
    po = _po(lang)
    for msgid in NEW_MSGIDS:
        entry = po.find(msgid)
        assert entry is not None and entry.msgstr and not entry.obsolete, (lang, msgid)
        if lang == "de":
            assert entry.msgstr == msgid
        else:
            assert entry.msgstr != msgid, (lang, msgid)


def test_m5b2_dead_code():
    """№4: `title_row` снят; `TITLE_REF` читают только псевдоним (`site_schema.page_ref`,
    переименование ключей старой сессии `aufbau_draft._rename_legacy_title`), его определение
    и `window_links.whole_page_refs`; подпись «Darstellung, Kartenform, Textbreite» и её msgid
    сняты во всех `.po`."""
    allowed = {
        "apps/core/page_title.py",
        "apps/core/site_schema.py",
        "apps/core/window_links.py",
        "apps/core/aufbau_draft.py",
    }
    seen = set()
    for path in (ROOT / "apps").rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\btitle_row\(", text), path
        assert not re.search(r"\bdef title_row\b", text), path
        if "TITLE_REF" in text:
            seen.add(path.relative_to(ROOT).as_posix())
    assert seen <= allowed, seen - allowed
    schema = (ROOT / "apps/core/site_schema.py").read_text(encoding="utf-8")
    # в site_schema — только импорт и псевдоним `page_ref`
    lines = [ln.strip() for ln in schema.splitlines() if "TITLE_REF" in ln]
    assert lines == [
        "from apps.core.page_title import TITLE_REF",
        "return PAGE_REF if ref == TITLE_REF else ref",
    ], lines
    draft = (ROOT / "apps/core/aufbau_draft.py").read_text(encoding="utf-8")
    assert [ln.strip() for ln in draft.splitlines() if "TITLE_REF" in ln] == [
        "old, new = page_title.TITLE_REF, site_schema.PAGE_REF"
    ]
    links = (ROOT / "apps/core/window_links.py").read_text(encoding="utf-8")
    assert [ln.strip() for ln in links.splitlines() if "TITLE_REF" in ln] == [
        "page_title.TITLE_REF,"
    ]
    for tpl in (ROOT / "templates").rglob("*.html"):
        for msgid in DEAD_MSGIDS:
            assert msgid not in tpl.read_text(encoding="utf-8"), tpl
    for lang in LANGS:
        po = _po(lang)
        for msgid in DEAD_MSGIDS:
            entry = po.find(msgid)
            assert entry is None or entry.obsolete, (lang, msgid)
