"""FB-33 стопка 15 M1d: «Kartenform» — варианты по виду основного списка (план
`docs/fb33-stack15-plan-2026-11-25.md` §1 «M1d», §4 «M1d», §14.1 A7, §14.2 Y7).

Решение владельца A7: схема настроек (`page_settings.schema`) и ассистент предлагают только
формы вида (`card_forms.forms_for_view`); `page_settings.choices` — без фильтра (сводка
Студии и `_clean`). Сохранённая форма вне вида видна с пометкой текстом, но не предлагается
(грабля «select по реестру»). Вид без карточек — «Diese Ansicht hat keine Karten» и ссылка
в окно блока ★ (`window_links.block_window_url`).
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation

from apps.core import (
    assistant_actions,
    assistant_pages,
    card_forms,
    page_settings,
    studio_pages,
    window_links,
)
from apps.core.modules import default_disabled_for
from apps.core.tests.test_assistant_a2 import _user
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CODE = "product_card_form"
OUTSIDE = "(passt nicht zur Ansicht)"
NO_CARDS = "Diese Ansicht hat keine Karten"
#: потолок запросов сводки (замер на ветке; рост — повод разобраться, а не поднять число)
SUMMARY_QUERIES = 15


def _tenant(business_type="online_shop"):
    return TenantFactory(
        business_type=business_type, disabled_modules=list(default_disabled_for(business_type))
    )


def _preisliste(tenant, form=""):
    page_settings.write(tenant, "catalog_layout", "preisliste")
    if form:
        page_settings.write(tenant, CODE, form)
    tenant.refresh_from_db()
    return tenant


def _state(tenant, type_code="catalog"):
    (ts,) = page_settings.schema(tenant, (type_code,))
    return next(s for s in ts.settings if s.code == CODE)


def _all_keys():
    return [k for k, _l, _h in card_forms.forms_for()]


# ───────────────────────── A7: схема и ассистент ─────────────────────────


def test_view_none_keeps_previous_variants():
    """Охранное: у сетки (вид с плитками и строками) — все прежние варианты."""
    st = _state(_tenant())
    assert [c.value for c in st.choices] == _all_keys()
    assert not st.no_cards


def test_choices_from_forms_for_view():
    st = _state(_tenant())
    assert [c.value for c in st.choices] == [k for k, _l, _h in card_forms.forms_for_view("")]


def test_schema_variants_by_view():
    st = _state(_preisliste(_tenant()))
    # у прайс-листа карточки нет — предлагать нечего, кроме сохранённого (с пометкой)
    assert [c.value for c in st.choices] == [""]
    assert st.no_cards


def test_saved_form_outside_view_marked():
    st = _state(_preisliste(_tenant(), "deal"))
    assert [c.value for c in st.choices] == ["deal"]
    assert OUTSIDE in str(st.choices[0].label)


def test_outside_form_option_text_suffix():
    """Y7: пометка — суффикс текста подписи (не цвет): подпись формы словом + суффикс."""
    st = _state(_preisliste(_tenant(), "deal"))
    label = str(st.choices[0].label)
    assert label.startswith(str(card_forms.label_for("deal"))) and label.endswith(OUTSIDE)


def test_choices_unfiltered_for_clean():
    tenant = _preisliste(_tenant())
    setting = studio_pages.SETTINGS[CODE]
    assert [c.value for c in page_settings.choices(setting)] == _all_keys()
    # запись (`_clean`) принимает любую форму реестра: форма сайта действует и на других страницах
    page_settings.validate(tenant, CODE, "deal")


def test_design_screen_keeps_all_forms():
    """Форма «Für alle Seiten» на «Design» — для всех страниц: вид каталога её не сужает."""
    tenant = _preisliste(_tenant())
    st = next(s for s in page_settings.design_schema(tenant) if s.code == CODE)
    assert [c.value for c in st.choices] == _all_keys()


def _page_item(type_code, value="deal"):
    return {
        "action": assistant_actions.PAGE_SETTING,
        "target": {"kind": "page", "pk": CODE},
        "values": {"name": "x", "value": value, "type": type_code},
        "before": "",
        "before_set": False,
    }


def _clean_errors(tenant, item):
    _rows, errors = assistant_actions._clean([item], {}, [], tenant)
    return errors


def test_assistant_variants_by_view():
    """Ревью 1 №1: путь продакшена — пункт ассистента несёт тип, варианты берутся по нему."""
    tenant = _tenant()
    user = _user()
    phrase = "Zeige die Produkte als Deal-Zeile"
    assert assistant_pages.build(tenant, user, phrase)  # у сетки — предлагается
    _preisliste(tenant)
    assert not assistant_pages.build(tenant, user, phrase)  # у прайс-листа — нет
    # проверка формы пакета: «deal» у каталога с прайс-листом — не из списка
    assert _clean_errors(tenant, _page_item("catalog"))
    # подпись «vorher/nachher» — словом и для формы вне вида
    assert assistant_pages.value_label(tenant, CODE, "deal") == str(card_forms.label_for("deal"))


def test_assistant_two_types_different_views():
    """Форма, допустимая только у другого типа, у этого отклоняется (а не по объединению)."""
    tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    _preisliste(tenant)
    assert _clean_errors(tenant, _page_item("catalog"))
    assert not _clean_errors(tenant, _page_item("services"))


def test_apply_rejects_form_outside_view():
    tenant = _preisliste(_tenant())
    item = _page_item("catalog")
    row = {
        "index": 0,
        "spec": assistant_actions.ACTIONS[assistant_actions.PAGE_SETTING],
        "item": item,
        "values": item["values"],
        "after": "deal",
    }
    with pytest.raises(assistant_actions.ApplyError):
        assistant_actions._change_page(row, tenant)
    tenant.refresh_from_db()
    assert page_settings.current_value(tenant.site_config, studio_pages.SETTINGS[CODE])[0] == ""


# ───────────────────────── вид основного списка (ревью 1 №2) ─────────────────────────


def test_main_view_only_main_list():
    """Вид — только у основного списка хоста: у детали товара (без ★) — "" и без ссылки."""
    from apps.tenants import siteconfig

    tenant = _tenant()
    raw = {**(tenant.site_config or {}), "detail_related_layout": {"preset": "preisliste"}}
    norm = siteconfig.normalize(raw)
    assert page_settings.main_view("product", raw, norm) == ""
    tenant.site_config = raw
    tenant.save(update_fields=["site_config"])
    found = page_settings.summaries(tenant, [CODE])[CODE]
    assert all("block=main" not in e["url"] or e["page"] != "product" for e in found["no_cards"])
    assert not _state(tenant, "product").no_cards


def test_main_view_ignores_other_layouts():
    """Две сетки в конфиге: каталог смотрит только на свою, чужой прайс-лист не в счёт."""
    from apps.tenants import siteconfig

    raw = {"service_index_layout": {"preset": "preisliste"}}
    norm = siteconfig.normalize(raw)
    assert page_settings.main_view("catalog", raw, norm) == ""
    assert page_settings.main_view("services", raw, norm) == "preisliste"


def test_main_view_failure_logged(monkeypatch, caplog):
    from apps.core import site_schema

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(site_schema, "host_for", boom)
    with caplog.at_level("WARNING", logger="apps.core.page_settings"):
        assert page_settings.main_view("catalog", {}, {}) == ""
    assert "main view of catalog failed" in caplog.text


def test_summaries_query_ceiling(django_assert_max_num_queries):
    tenant = _preisliste(_tenant())
    with django_assert_max_num_queries(SUMMARY_QUERIES):
        page_settings.summaries(tenant, [CODE])


# ───────────────────────── сводка Студии ─────────────────────────


def test_summary_label_for_form_outside_view():
    tenant = _preisliste(_tenant(), "deal")
    found = page_settings.summaries(tenant, [CODE])[CODE]
    assert str(found["value"]) == str(card_forms.label_for("deal"))


def test_rows_view_no_cards_hint():
    tenant = _preisliste(_tenant())
    found = page_settings.summaries(tenant, [CODE])[CODE]
    pages = {e["page"]: e for e in found["no_cards"]}
    assert "catalog" in pages
    assert pages["catalog"]["url"] == window_links.block_window_url("catalog", "main", "wie")
    assert pages["catalog"]["name"]
    # у сетки подсказки нет
    assert not page_settings.summaries(_tenant(), [CODE])[CODE]["no_cards"]


def _html(tenant, lang="de"):
    with translation.override(lang):
        s = page_settings.summaries(tenant, [CODE])[CODE]
        return render_to_string("tenant/_stu19_summary.html", {"s": s}), s


def test_hint_link_names_block_and_underlined():
    html, s = _html(_preisliste(_tenant()))
    entry = next(e for e in s["no_cards"] if e["page"] == "catalog")
    assert NO_CARDS in html
    link = re.search(r"<a [^>]*data-stu19-view-link[^>]*>([^<]*)</a>", html)
    assert link, html
    assert f"Ansicht im Block „{entry['name']}“ ändern" in link.group(1)
    assert re.search(r'class="[^"]*\bunderline\b', link.group(0))
    # aria-describedby ведёт к существующей подсказке
    ref = re.search(r'aria-describedby="([^"]+)"', link.group(0)).group(1)
    assert f'id="{ref}"' in html
    # подсказка видна только на странице своего типа
    assert 'data-stu-page="catalog"' in html


def test_hint_in_russian():
    html, _s = _html(_preisliste(_tenant()), "ru")
    assert "У этого вида нет карточек" in html and "Изменить вид в блоке" in html


def test_hint_link_plain():
    """Обычная ссылка без JS: настоящий адрес окна блока, без hx-/onclick."""
    html, _s = _html(_preisliste(_tenant()))
    link = re.search(r"<a [^>]*data-stu19-view-link[^>]*>", html).group(0)
    href = re.search(r'href="([^"]+)"', link).group(1)
    assert "block=main" in href and "tab=wie" in href
    assert "hx-" not in link and "onclick" not in link


def test_two_hints_name_their_page():
    """Ревью 1 №3: без JS видны обе подсказки (каталог и «Alle Kategorien») — текст разный."""
    html, s = _html(_preisliste(_tenant()))
    assert {e["page"] for e in s["no_cards"]} >= {"catalog", "category"}
    texts = re.findall(r'<span id="(stu19-nc-[^"]+)">(.*?)</span>\s*<a', html, re.S)
    assert len(texts) >= 2
    seen = [re.sub(r"<[^>]+>|\s+", " ", t).strip() for _id, t in texts]
    assert len(set(seen)) == len(seen), seen
    assert len({i for i, _t in texts}) == len(texts)
    assert all(NO_CARDS in t for t in seen)


def test_arrow_is_decorative():
    html, _s = _html(_tenant())
    assert '<span aria-hidden="true">→</span>' in html


def test_no_aria_hidden_on_focusable():
    html, _s = _html(_preisliste(_tenant()))
    for tag in re.findall(r"<(?:a|button|input|select)\b[^>]*>", html):
        assert "aria-hidden" not in tag


def test_summary_without_hint_unchanged():
    html, _s = _html(_tenant())
    assert NO_CARDS not in html and "data-stu19-view-link" not in html


def test_m1d_msgids_in_all_po():
    msgids = (NO_CARDS, OUTSIDE, "Ansicht im Block „%(name)s“ ändern")
    for lang in ("de", "en", "ru", "tr", "uk"):
        po = (Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.po").read_text()
        for msgid in msgids:
            m = re.search(r'msgid "' + re.escape(msgid) + r'"\nmsgstr "([^"]*)"', po)
            assert m and m.group(1), (lang, msgid)


def test_studio_scope_keeps_hint():
    """Ревью 1 №4: правило Студии «рамка без поля — спрятать» подсказку не прячет (у неё нет
    поля, только текст и ссылка) — её охват решает `data-stu-page` (стенд: видна одна)."""
    src = (Path(settings.BASE_DIR) / "templates" / "tenant" / "site_home.html").read_text()
    rule = src.index('document.querySelectorAll("[data-stu-page]:not([data-stu-setting])")')
    assert 'el.hasAttribute("data-stu19-no-cards")' in src[rule : rule + 600]


def test_main_list_layouts_registry():
    """Сетка основного списка — только у хостов с ★ и только из сеток кабинета."""
    from apps.tenants import siteconfig

    for host, key in page_settings.MAIN_LIST_LAYOUTS.items():
        assert siteconfig.has_main_list(host), host
        assert key in page_settings._LAYOUT_KEYS, key
