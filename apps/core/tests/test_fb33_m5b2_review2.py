"""FB-33 M5b-2: замки по ревью среза A, раунд 2 (django-reviewer W2+W3, a11y-architect).

План — `docs/fb33-stack10-plan-2026-11-22.md` §8. Пункты ревью:

1. «хост → код страницы» — один разбор (`site_schema.page_code_of_host`): его зовёт и
   `code_for_path`; круг `host_for(page_code_of_host(h)) == h` у каждого хоста со своим
   списком, у категории, группы акций и текстовых страниц;
2. строка главного списка Студии: ссылка «Wie die Liste aussieht» — по правилу с тенантом
   (`page_row_ref(tenant, …)`): у бизнеса, у которого ★-строки этой страницы нет, ссылки нет,
   имя списка остаётся;
3. `_MAIN_LIST_SOURCES` — только хосты, чей источник «Liste» назван иначе; у каждого хоста со
   списком имя не пустое и не «Aktionen» по умолчанию (кроме акций);
4. «Hauptliste» сводки — `_()` не внутри f-строки (xgettext);
5. `is_title_alias` — точное сравнение с `TITLE_REF`;
6. комментарий `page_templates` без «★ Hauptliste»; стенд обхода владельца ищет «Hauptliste»
   как немецкое слово (не подпись строки) — правило верно;
7. ссылка «Wie die Liste aussieht» уводит из Студии через `leaveOk()` (`data-stu-window`);
8. скрытая «Übernehmen» формы полей — НЕ `aria-hidden` (решение a11y M3-5c; находка не принята);
9. ★-строка: «, feste Position» отделена от сводки для чтения;
10. глиф «›» строки «Darstellung der Liste» — в `aria-hidden`;
11. окно ★-строки без повторных `id` и у страницы с SEO на «Texte»; SEO-хосты и хосты своего
    заголовка не пересекаются.
"""

import copy
import inspect
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.utils import translation

from apps.core import list_blocks, page_title, site_schema, views
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.core.tests.test_fb33_m4b_studio_dupes import _req
from apps.core.tests.test_fb33_m5b2_studio import CFG, _main_rows
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
TPL = ROOT / "templates" / "tenant"
PAGE = site_schema.PAGE_REF
#: хосты, где главный список — акции (имя «Aktionen» — по делу, не умолчание)
PROMO_HOSTS = ("promos", "promo_group")
NO_SOURCE = "__kein_quelle__"


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


def _studio(tenant) -> str:
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


# ───────────── 1. один разбор «хост → код страницы» ─────────────


def test_page_code_of_host_round_trip(monkeypatch):
    """`host_for(page_code_of_host(h)) == h`: хосты со своим списком, категория, группа акций,
    текстовые страницы."""
    group = siteconfig.promo_group_host("Sale")
    monkeypatch.setattr(site_schema, "live_promo_groups", lambda: [("Sale", "Sale")])
    category = siteconfig.category_host("brot")
    for host in (*siteconfig.MAIN_LIST_HOSTS, category, group):
        code = site_schema.page_code_of_host(host)
        assert code, host
        assert site_schema.host_for(code, known_slugs={"brot"}) == host, (host, code)
    assert site_schema.page_code_of_host(category) == f"{site_schema.CATEGORY}@{category}"
    assert site_schema.page_code_of_host(group) == f"{site_schema.PROMO_GROUP}@{group}"
    for junk in ("", None, "home", "nope", "promo_group:xyz"):
        assert site_schema.page_code_of_host(junk) == "", junk


def test_page_code_of_host_text_pages():
    """Те же ветки, что у `code_for_path`: «Versand», «Info», своя страница `seite:<slug>`."""
    assert site_schema.page_code_of_host("versand") == f"{site_schema.TEXT}@versand"
    assert site_schema.page_code_of_host("info") == site_schema.TEXT
    assert site_schema.page_code_of_host("seite:ueber-uns") == f"{site_schema.TEXT}@seite:ueber-uns"
    for host in ("versand", "info"):
        assert site_schema.host_for(site_schema.page_code_of_host(host)) == host, host


def test_code_for_path_uses_page_code_of_host():
    """Ветки префиксов хоста живут в одном месте: `code_for_path` зовёт `page_code_of_host`."""
    src = inspect.getsource(site_schema.code_for_path)
    assert "page_code_of_host(" in src
    assert "CATEGORY_HOST_PREFIX" not in src and 'startswith("seite:")' not in src


# ───────────── 2. ссылка Студии — по правилу с тенантом ─────────────


def test_studio_main_row_no_link_without_page_row():
    """У магазина модуля записи нет — ★-строки «Leistungen» нет (`page_row_ref(tenant, …)`
    пусто): ссылки «Wie die Liste aussieht» нет, имя списка и плашка остаются."""
    tenant = _tenant("online_shop", CFG)
    assert site_schema.page_row_ref(tenant, "services") == ""
    assert site_schema.page_row_ref(None, "services") == PAGE  # без тенанта — была бы
    row = _main_rows(_studio(tenant))["services"]
    assert "data-pb-main-page-link" not in row
    assert '<span class="font-medium">Leistungen</span>' in row
    assert ">Hauptliste</span>" in row


def test_studio_main_row_link_with_page_row():
    """У бизнеса со ★-строкой (каталог магазина) ссылка остаётся."""
    tenant = _tenant("online_shop", CFG)
    assert site_schema.page_row_ref(tenant, "catalog") == PAGE
    assert "data-pb-main-page-link" in _main_rows(_studio(tenant))["catalog"]


# ───────────── 3. имя главного списка без копии карты ─────────────


def test_main_list_name_every_host_named():
    """У каждого хоста со списком имя не пустое и не умолчание `source_label` (акции), кроме
    самих акций; у категории — как у каталога."""
    fallback = list_blocks.source_label(NO_SOURCE)
    with translation.override("de"):
        for host in siteconfig.MAIN_LIST_HOSTS:
            name = site_schema.main_list_name(host)
            assert name, host
            if host not in PROMO_HOSTS:
                assert name != fallback, host
        assert site_schema.main_list_name("combos") == list_blocks.source_label("combos")
        assert site_schema.main_list_name("reviews") == list_blocks.source_label("reviews")
        assert site_schema.main_list_name("stay_rooms") == list_blocks.source_label("stays")


def test_main_list_sources_only_renamed():
    """В карте — только хосты, чей источник назван иначе (тождественные — из `LIST_SOURCES`)."""
    assert set(site_schema._MAIN_LIST_SOURCES) == {"catalog", "category", "promos", "promo_group"}


# ───────────── 4–6. мелочи кода ─────────────


def test_summary_msgid_outside_fstring():
    src = inspect.getsource(site_schema.main_list_summary)
    assert '{_("' not in src and "{_('" not in src


def test_is_title_alias_exact():
    assert site_schema.is_title_alias(page_title.TITLE_REF)
    for ref in (PAGE, "x__title", "__title_x", "", None, 1):
        assert not site_schema.is_title_alias(ref), ref


def test_page_templates_doc_current():
    src = (ROOT / "apps" / "core" / "page_templates.py").read_text(encoding="utf-8")
    assert "★ Hauptliste" not in src


def test_owner_stand_hauptliste_is_a_german_word_not_a_label():
    """Стенд обхода владельца знает «Hauptliste» только словом немецкого словаря (признак
    непереведённой строки в ru), подписей строк по нему не ищет — правило верно после W2."""
    src = (ROOT / "scripts" / "fb33_m3_9_owner_stand.py").read_text(encoding="utf-8")
    hits = [line for line in src.splitlines() if "Hauptliste" in line]
    assert len(hits) == 1, hits
    words = src[src.index("GERMAN_WORDS = frozenset(") :]
    assert "Hauptliste" in words[: words.index(".split()")]


# ───────────── 7–10. разметка ─────────────


@pytest.mark.xfail(strict=True, reason="№7: ссылка уходит без leaveOk() (до правки)")
def test_studio_main_row_link_guarded():
    """Ссылка «Wie die Liste aussieht» — `data-stu-window`: её ловит `leaveOk()` Студии; в
    окно ★-строки, не в окно блока стенда M4b (`block=products`)."""
    row = _main_rows(_studio(_tenant("online_shop", CFG)))["catalog"]
    link = re.search(r"<a [^>]*data-pb-main-page-link[^>]*>", row).group(0)
    assert re.search(r"\sdata-stu-window[\s>]", link), link
    href = re.search(r'href="([^"]+)"', link).group(1).replace("&amp;", "&")
    assert parse_qs(urlsplit(href).query)["block"] == [PAGE]
    src = (TPL / "site_home.html").read_text(encoding="utf-8")
    assert re.search(r'querySelectorAll\("[^"]*\[data-stu-window\][^"]*"\)\.forEach', src)


def test_hidden_apply_button_stays_readable():
    """№8 не принят: невидимая «Übernehmen» формы полей — БЕЗ `aria-hidden` (решение a11y-ревью
    M3-5c, замок `test_fb33_m35c_review::test_invisible_apply_button_is_not_aria_hidden`,
    грабля `pitfalls.md` 2026-11-21 и скилла sa-block-editor). На «Seite» видимая кнопка формы
    заголовка различима суффиксом «: Seitentitel» (`test_title_form_apply_button_named`)."""
    src = (TPL / "_bw_fields.html").read_text(encoding="utf-8")
    buttons = re.findall(r'<button [^>]*class="sr-only"[^>]*>', src)
    assert buttons
    for b in buttons:
        assert 'tabindex="-1"' in b and "aria-hidden" not in b, b


@pytest.mark.xfail(strict=True, reason="№9: «feste Position» слита со сводкой (до правки)")
def test_page_row_position_separated_from_summary():
    html = Browser(_tenant()).get("?seite=services")
    m = re.search(rf'<a [^>]*data-schema-block="{PAGE}"[^>]*>(.*?)</a>', html, re.S)
    assert m
    inner = m.group(1)
    assert '<span class="block text-xs' in inner, "у ★-строки есть сводка"
    sr = re.search(r'<span class="sr-only">([^<]*)</span>\s*<span class="block', inner)
    assert sr and re.search(r"feste Position[.;,]\s*$", sr.group(1)), inner


@pytest.mark.xfail(strict=True, reason="№10: глиф › читается (до правки)")
def test_list_link_glyph_hidden():
    html = _panel(Browser(_tenant("online_shop")).get(f"?seite=catalog&block={PAGE}"))
    link = re.search(r"<a [^>]*data-schema-list-link[^>]*>(.*?)</a>", html, re.S).group(1)
    assert '<span aria-hidden="true">›</span>' in link
    assert "›" not in link.replace('<span aria-hidden="true">›</span>', "")
    text = re.sub(r"<[^>]+>", "", link)
    assert "Darstellung der Liste" in text and "Wie anordnen" in text


# ───────────── 11. SEO и заголовок ─────────────


def test_seo_hosts_and_head_hosts_disjoint():
    """SEO на «Texte» (`is_seo_page_host`) и поля заголовка на «Seite» (`HEAD_HOSTS`) — у
    разных страниц: одновременного сочетания нет, повторные `id` проверяются по отдельности
    (`test_no_duplicate_ids_on_page_tab`)."""
    assert not [h for h in page_title.HEAD_HOSTS if siteconfig.is_seo_page_host(h)]
    for host in (*siteconfig.SEO_PAGE_HOSTS, "seite:ueber-uns"):
        assert siteconfig.is_seo_page_host(host)
        assert host not in page_title.HEAD_HOSTS
