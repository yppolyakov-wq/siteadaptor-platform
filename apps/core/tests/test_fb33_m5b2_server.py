"""FB-33 M5b-2 W0: сервер понимает ★-строку страницы (`__page`) как место «Seitentitel».

План — `docs/fb33-stack10-plan-2026-11-22.md` §2.A W0, §4 таблица A, §8.1 (architect). W0 вид
не меняет: строка «Seitentitel» (`__title`) живёт на экране до W1, её окно открывается как
прежде. Сервер уже принимает поля заголовка на `__page` (тем же писателем `title_op`), держит
один предикат строки заголовка (`site_schema.is_title_row`) и псевдоним `__title` → `__page`
(`site_schema.page_ref`).

Слияние ключей окна и переводов (`__title` → `__page`: снимок окна, `btr`, `btr_base`, вкладка
переводов заголовка на `__page`) в W0 держал переключатель `page_title.ON_PAGE_ROW`; W1 его
снял — слияние действует всегда. Сессия до деплоя (ключи `__title`) в замках строится явно:
правка окна, затем ключи переименовываются так, как их писал прежний код.
"""

import copy
import logging
import re
from pathlib import Path

import pytest

from apps.core import aufbau_draft, block_i18n, block_window, page_title, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

WOPEN = "openW0a"
OTHER = "openW0b"
#: хост с «Seitentitel» и страницей промо у фабричного бизнеса (`_shop`)
CODE = "promos"


def _post(b, **data):
    data.setdefault("wopen", WOPEN)
    return b.post(**data)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _shop_with_ru_title():
    """Сохранённый перевод заголовка: без него отпечаток переводов пуст при любом ref."""
    tenant = _shop()
    cfg = copy.deepcopy(tenant.site_config)
    cfg["page_titles"] = {CODE: {"title": "Aktionen"}}
    cfg["i18n"] = {"ru": {"page_titles": {CODE: {"title": "Акции"}}}}
    tenant.site_config = cfg
    tenant.enabled_locales = ["de", "ru", "en"]
    tenant.save()
    return tenant


def _title_row_page(fields=True):
    """Строка `__page` окна, которая несёт поля заголовка (как её построит W1)."""
    row = {"ref": site_schema.PAGE_REF, "key": site_schema.PAGE_REF, "cblock": False}
    if fields:
        row["fields"] = [
            {"name": "title", "label": "Seitentitel", "kind": "line", "value": ""},
            {"name": "intro", "label": "Einleitung", "kind": "area", "value": ""},
            {"name": "align", "label": "Ausrichtung", "kind": "select", "value": ""},
        ]
    return row


# ───────────── псевдоним и маршрут правки ─────────────


def test_page_ref_alias_exact():
    assert site_schema.page_ref(page_title.TITLE_REF) == site_schema.PAGE_REF
    for ref in (site_schema.PAGE_REF, "__title_x", "x__title", "", "main", "page_title"):
        assert site_schema.page_ref(ref) == ref
    assert not site_schema.is_page_title_edit("__title_x", {"title": "x"})
    assert not site_schema.is_page_title_edit(site_schema.PAGE_REF, {"seo_title": "x"})
    assert not site_schema.is_page_title_edit(site_schema.PAGE_REF, None)
    assert site_schema.is_page_title_edit(site_schema.PAGE_REF, {"align": ""})


def test_title_on_page_ref_goes_through_title_op(monkeypatch):
    calls = []
    real = site_schema.title_op

    def spy(host, draft, op, fields):
        calls.append((host, op))
        return real(host, draft, op, fields)

    monkeypatch.setattr(site_schema, "title_op", spy)
    old, new = Browser(_shop()), Browser(_shop())
    fields = {"f_title": "Mein Titel", "f_intro": "Text", "f_align": "center"}
    _post(old, seite=CODE, ref=page_title.TITLE_REF, op="update", panel_present="1", **fields)
    _post(new, seite=CODE, ref=site_schema.PAGE_REF, op="update", panel_present="1", **fields)
    assert calls == [(CODE, "update"), (CODE, "update")]
    assert _drafts(old)[CODE]["title"] == _drafts(new)[CODE]["title"]
    assert _drafts(new)[CODE]["title"] == {
        "title": "Mein Titel",
        "intro": "Text",
        "align": "center",
    }
    assert "page_titles" not in _saved(new)  # только черновик
    _post(new, seite=CODE, op="save")
    assert _saved(new)["page_titles"] == {
        CODE: {"title": "Mein Titel", "intro": "Text", "align": "center"}
    }
    # прямая запись (`apply`) — тот же писатель
    tenant = _shop()
    site_schema.apply(tenant, CODE, "update", ref=site_schema.PAGE_REF, fields={"title": "Direkt"})
    assert Tenant.objects.get(pk=tenant.pk).site_config["page_titles"] == {
        CODE: {"title": "Direkt"}
    }
    assert calls[-1] == (CODE, "update")


def test_title_on_page_ref_keeps_other_ops_of_the_page_row():
    """SEO окна «Einstellungen der Seite» и прочие операции `__page` идут прежним путём."""
    b = Browser(_shop())
    _resp, msgs = _post(b, seite="text", ref=site_schema.PAGE_REF, op="update", panel_present="1",
                        f_seo_title="Über uns")  # fmt: skip
    draft = _drafts(b)["text"]
    assert draft["seo"] == {"title": "Über uns"} and "title" not in draft
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(_shop(), CODE, "update", ref=site_schema.PAGE_REF, fields={"x": "1"})


#: стопка 15 M5e-2b: у каталога шапка своя (`page_title.has_head`) — он больше не «чужой»
@pytest.mark.parametrize("code", ("cart", "product", "text"))
def test_foreign_host_title_on_page_ref_rejected(code):
    b = Browser(_shop())
    req = b._request("post", {"wopen": WOPEN})
    with pytest.raises(site_schema.SchemaError) as err:
        aufbau_draft.op(req, b.tenant, code, "update", ref=site_schema.PAGE_REF,
                        fields={"title": "x"}, token=WOPEN)  # fmt: skip
    assert err.value.args == ("block",)
    with pytest.raises(site_schema.SchemaError) as err:
        site_schema.apply(b.tenant, code, "update", ref=site_schema.PAGE_REF, fields={"title": "x"})
    assert err.value.args == ("block",)
    assert "page_titles" not in _saved(b)


#: запись `page_titles` в коде приложений: `[...]["page_titles"] = …`, путь `("page_titles", …)`,
#: `config["page_titles"] = …` — набор писателей M2d (черновик, переводы, инлайн, нормализация)
_WRITE_RE = re.compile(r"""\[\s*["']page_titles["']\s*\]\s*=(?!=)|\(\s*["']page_titles["']\s*,""")
WRITERS = {
    # стопка 15 M5e-2b: один писатель шапки `put_head` (черновик зовёт его, переводы —
    # путём `tr_path`)
    "apps/core/page_title.py",
    "apps/core/views.py",  # инлайн-правка H1 в Студии
    "apps/tenants/siteconfig.py",  # `normalize`
}


def test_page_titles_writers_unchanged():
    root = Path(__file__).resolve().parents[3]
    found = set()
    for path in (root / "apps").rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if _WRITE_RE.search(path.read_text(encoding="utf-8")):
            found.add(path.relative_to(root).as_posix())
    assert found == WRITERS


# ───────────── один предикат строки заголовка: потолки и «Ausrichtung» ─────────────


def test_page_ref_title_caps():
    caps = {"title": page_title.TITLE_MAX, "intro": page_title.INTRO_MAX}
    assert block_window.field_caps(_title_row_page()) == caps
    # W2: строки «Seitentitel» (`title_row`) больше нет — потолки только у ★-строки
    # W0: строка `__page` окна полей заголовка не несёт — потолков нет, окно прежнее
    assert block_window.field_caps(_title_row_page(fields=False)) == {}
    assert site_schema.is_title_row(_title_row_page(), "anfrage")
    assert not site_schema.is_title_row(_title_row_page(), "cart")
    assert not site_schema.is_title_row(_title_row_page(fields=False), "anfrage")
    assert not site_schema.is_title_row({**_title_row_page(), "cblock": True}, "anfrage")
    assert not site_schema.is_title_row(None, "anfrage")
    # сервер обрезает 121 символ до потолка
    b = Browser(_shop())
    _post(b, seite=CODE, ref=site_schema.PAGE_REF, op="update", panel_present="1",
          f_title="x" * (page_title.TITLE_MAX + 1), f_intro="y" * (page_title.INTRO_MAX + 5))  # fmt: skip
    title = _drafts(b)[CODE]["title"]
    assert (
        len(title["title"]) == page_title.TITLE_MAX and len(title["intro"]) == page_title.INTRO_MAX
    )


def test_page_ref_title_align_options():
    row = _title_row_page()  # W2: строки «Seitentitel» (`title_row`) больше нет
    site_schema.fill_options(row, "anfrage")
    align = next(f for f in row["fields"] if f["name"] == "align")
    assert [value for value, _label in align["options"]] == ["", "center"]
    foreign = _title_row_page()
    site_schema.fill_options(foreign, "cart")
    assert "options" not in next(f for f in foreign["fields"] if f["name"] == "align")


# ───────────── Студия ─────────────


def test_studio_open_title_alias(monkeypatch):
    from apps.core import window_links

    refs = {"main", site_schema.PAGE_REF}
    monkeypatch.setattr(window_links, "_refs", lambda request, code, host: set(refs))
    assert window_links._block_of(None, CODE, CODE, page_title.TITLE_REF) == site_schema.PAGE_REF
    assert window_links._block_of(None, CODE, CODE, "__title_x") == ""
    refs.add(page_title.TITLE_REF)  # W0: строка «Seitentitel» ещё на экране — точное совпадение
    assert window_links._block_of(None, CODE, CODE, page_title.TITLE_REF) == page_title.TITLE_REF
    refs.discard(site_schema.PAGE_REF)
    refs.discard(page_title.TITLE_REF)
    assert window_links._block_of(None, CODE, CODE, page_title.TITLE_REF) == ""


# ───────────── после W1: ключи окна и переводов — под ★-строкой ─────────────


def test_title_window_keys_are_page_keys():
    """W1 (переписано осознанно: W0 держал прежние ключи до слияния): правка заголовка — и по
    старому ref `__title` — пишет снимок и переводы под `__page`; окно `__page` форм несёт
    переводы заголовка; у страницы без заголовка снимок `__page` — без заголовка."""
    assert not hasattr(page_title, "ON_PAGE_ROW")
    b = Browser(_shop())
    _post(b, seite=CODE, ref=page_title.TITLE_REF, op="update", panel_present="1",
          f_title="Mein Titel", f_tr_title_en="Deals")  # fmt: skip
    draft = _drafts(b)[CODE]
    assert set(draft[aufbau_draft.WINDOW_KEY]) == {site_schema.PAGE_REF}
    assert set(draft["btr"]) == set(draft["btr_base"]) == {site_schema.PAGE_REF}
    assert site_schema.title_op(CODE, {}, "update", {"title": "x"}) == site_schema.PAGE_REF
    assert block_i18n.kinds({"host": "anfrage", "items": []}, site_schema.PAGE_REF) == ("title",)
    _post(b, seite="text", ref=site_schema.PAGE_REF, op="update", panel_present="1",
          f_seo_title="Über uns")  # fmt: skip
    assert "title" not in _drafts(b)["text"][aufbau_draft.WINDOW_KEY][site_schema.PAGE_REF]


# ───────────── после W1: сессия до деплоя ─────────────


def _as_before_deploy(b, code=CODE):
    """Ключи окна и переводов заголовка — так, как их писал код до слияния (`__title`)."""
    draft = b.session[aufbau_draft.SESSION_KEY][code]
    for key in (aufbau_draft.WINDOW_KEY, *block_i18n.DRAFT_KEYS):
        part = draft.get(key)
        if isinstance(part, dict) and site_schema.PAGE_REF in part:
            part[page_title.TITLE_REF] = part.pop(site_schema.PAGE_REF)
    b.session.modified = True


def _old_title_draft(tenant, title="Neu"):
    """Черновик сессии до слияния: правка окна «Seitentitel» с переводом (ключи `__title`)."""
    b = Browser(tenant)
    _post(b, seite=CODE, ref=page_title.TITLE_REF, op="update", panel_present="1",
          f_title=title, f_tr_title_en="Deals")  # fmt: skip
    _as_before_deploy(b)
    draft = _drafts(b)[CODE]
    assert page_title.TITLE_REF in draft[aufbau_draft.WINDOW_KEY]
    assert page_title.TITLE_REF in draft["btr"]
    return b


@pytest.mark.parametrize("ref", (page_title.TITLE_REF, site_schema.PAGE_REF))
def test_legacy_window_title_snapshot_reverts(ref):
    b = _old_title_draft(_shop())
    _resp, msgs = _post(b, seite=CODE, ref=ref, op="revert")
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b) == {}


def test_legacy_btr_title_saves():
    b = _old_title_draft(_shop())
    _resp, msgs = _post(b, seite=CODE, op="save")
    assert "Gespeichert." in msgs
    saved = _saved(b)
    assert saved["page_titles"][CODE] == {"title": "Neu"}
    assert saved["i18n"]["en"]["page_titles"][CODE] == {"title": "Deals"}


def test_legacy_keys_logged(caplog):
    b = _old_title_draft(_shop())
    with caplog.at_level(logging.INFO, logger="apps.core.aufbau_draft"):
        b.get(f"?seite={CODE}")
        b.get(f"?seite={CODE}")
    said = [r for r in caplog.records if "__title" in r.getMessage()]
    assert len(said) == 1 and said[0].levelno == logging.INFO
    draft = _drafts(b)[CODE]
    for key in (aufbau_draft.WINDOW_KEY, "btr", "btr_base"):
        assert set(draft[key]) == {site_schema.PAGE_REF}, key


def test_open_draft_before_deploy_not_conflict():
    """Перевод заголовка уже сохранён: отпечаток `btr_base["__title"]` равен отпечатку
    `__page` после слияния — «Speichern» не видит чужой правки."""
    b = _old_title_draft(_shop_with_ru_title(), title="Aktionen")  # немецкий прежний — ru остаётся
    assert _drafts(b)[CODE]["btr_base"][page_title.TITLE_REF]
    _resp, msgs = _post(b, seite=CODE, op="save")
    assert "Gespeichert." in msgs, msgs
    saved = _saved(b)
    assert saved["i18n"]["en"]["page_titles"][CODE] == {"title": "Deals"}
    assert saved["i18n"]["ru"]["page_titles"][CODE] == {"title": "Акции"}


def test_bases_title_equals_page():
    tenant = _shop_with_ru_title()
    cfg = siteconfig.normalize(tenant.site_config)
    for host in (CODE, "anfrage", "services"):
        page = {"host": host, "home": False, "items": [], "title": {}}
        assert block_i18n.kinds(page, site_schema.PAGE_REF) == ("title",)
        assert (
            block_i18n.bases(cfg, page, page_title.TITLE_REF)["all"]
            == block_i18n.bases(cfg, page, site_schema.PAGE_REF)["all"]
        )
    assert block_i18n.kinds({"host": "cart", "items": []}, site_schema.PAGE_REF) == ()


def test_two_snapshots_pick_by_token():
    """У формы до слияния — два окна: «Einstellungen der Seite» (`__page`) и «Seitentitel»
    (`__title`). После слияния — один снимок: основа — окно с присланным токеном, второй
    вливается в неё (ревью M5b-2 №1)."""

    def two_windows():
        b = _old_title_draft(_shop())  # сессия до деплоя
        drafts = b.session[aufbau_draft.SESSION_KEY]
        window = drafts[CODE][aufbau_draft.WINDOW_KEY]
        window[site_schema.PAGE_REF] = {
            "item": None, "at": None, "after": None, "base": window[page_title.TITLE_REF]["base"],
            "wopen": OTHER, "codes": [],
        }  # fmt: skip
        return b

    b = two_windows()
    _resp, msgs = _post(b, seite=CODE, ref=site_schema.PAGE_REF, op="revert", wopen=WOPEN)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b) == {}  # заголовок вернулся — черновика нет

    # ревью M5b-2 №1 (осознанно): снимок — одного окна; второй не отбрасывается, а вливается —
    # «Abbrechen» окна «Einstellungen der Seite» откатывает и заголовок из окна «Seitentitel»
    b = two_windows()
    _resp, msgs = _post(b, seite=CODE, ref=site_schema.PAGE_REF, op="revert", wopen=OTHER)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b) == {}

    # без токена окна выбрать нечем: оба снимка ждут своего окна
    b = two_windows()
    b.get(f"?seite={CODE}")
    window = _drafts(b)[CODE][aufbau_draft.WINDOW_KEY]
    assert set(window) == {site_schema.PAGE_REF, page_title.TITLE_REF}
    assert set(_drafts(b)[CODE]["btr"]) == {site_schema.PAGE_REF}


def test_merged_title_window_writes_new_keys_only():
    b = Browser(_shop())
    _resp, _msgs = _post(b, seite=CODE, ref=site_schema.PAGE_REF, op="update", panel_present="1",
                         f_title="Neu", f_tr_title_en="Deals")  # fmt: skip
    draft = _drafts(b)[CODE]
    assert draft["title"] == {"title": "Neu"}
    for key in (aufbau_draft.WINDOW_KEY, "btr", "btr_base"):
        assert set(draft[key]) == {site_schema.PAGE_REF}, key
    assert "title" in draft[aufbau_draft.WINDOW_KEY][site_schema.PAGE_REF]  # «Abbrechen» вернёт
    assert site_schema.title_op(CODE, {}, "update", {"title": "x"}) == site_schema.PAGE_REF
    _post(b, seite=CODE, ref=page_title.TITLE_REF, op="window_done")  # старая ссылка «Fertig»
    assert aufbau_draft.WINDOW_KEY not in (_drafts(b).get(CODE) or {})
