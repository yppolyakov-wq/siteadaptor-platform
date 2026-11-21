"""FB-33 M2i-5c: кнопка ИИ «🌐 Übersetzen» во вкладке «Felder» окна блока формы заявки.

Переиспользует AIS-5 без изменений на сервере (эндпоинты `translate_views`, тег
`i18n_translate_ctx`, клиент — вынесенный дословно `tenant/_i18n_translate_js.html`).
Решения владельца 2026-11-21: переводятся ТОЛЬКО ПУСТЫЕ поля выбранного языка; больше лимитов
AIS-5 — штатный отказ «Zu viel Text auf einmal». Запись — только «Übernehmen» → черновик →
`form_spec.put` (второго писателя нет).

Замки:
1. кнопка — в блоке языков вкладки (`after_tpl` партиала `_bw_langs.html`): type=button, без
   скриптов не видна (box `hidden`), язык — `data-loc` выбранного, экран подписан `site-schema`,
   живая область, пометка ИИ и плашка;
2. ИИ выключен / нет права записи / один язык — вкладка байт-в-байт прежняя;
3. источник перевода: своя подпись поля и вопрос — `data-i18n-of` на ЕСТЬ в форме поле,
   варианты и «Art der Veranstaltung» — `data-i18n-base` (автоэкранирование);
4. страница «Seitenaufbau» несёт клиент перевода один раз (только при ИИ), он знает `data-loc`
   и событие `aufbau:panel`;
5. 20 форм кабинета: `_i18n_switch.html` включает тот же клиент (регресс AIS-5 — стенд
   `scripts/ais5_translate_stand.py`);
6. эндпоинт AIS-5 принимает экран окна, чужой язык и лишний объём — штатные коды.
"""

import json
import re
from unittest import mock

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.urls import resolve
from django.utils import translation

from apps.core import i18n_translate as it
from apps.core import tasks, view_perms
from apps.core.tests import test_ais5_translate as ais5
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i5b_window import _browser
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
XSS = '<script>alert("x")</script>'
FLAG = "window.__i18nTranslateBound = true"
BOX = re.compile(r"<div[^>]*data-i18n-translate-box.*?</div>", re.S)
MARKS = re.compile(r' data-i18n-(?:of|base)="[^"]*"')


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _ScreenBrowser(Browser):
    """Как в кабинете: у запроса есть `resolver_match` (тег кнопки читает имя экрана)."""

    def _request(self, method, data=None, query=""):
        req = super()._request(method, data, query)
        req.resolver_match = resolve("/dashboard/site/aufbau/")
        return req


def _b(cfg=None, locales=("de", "ru", "en")):
    return _ScreenBrowser(_browser(cfg, locales).tenant)


def _ai(monkeypatch, on=True, allowed=True):
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: on)
    monkeypatch.setattr(view_perms, "allowed", lambda user, name, method: allowed)


def _part(b, query=""):
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder" + query)
    start = html.index("data-form-felder")
    return html, html[start : html.index("</form>", start)]


def _cfg_xss():
    from apps.core.tests.test_fb33_m2i5_before import CUSTOM

    cfg = json.loads(json.dumps(CUSTOM))
    cfg["form_fields"]["anfrage"]["custom"][1]["options"] = ["Saal", XSS]
    return cfg


# --- 1. кнопка ----------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="M2i-5c: кнопки ещё нет")
def test_button_sits_in_language_block_hidden_without_js(monkeypatch):
    _ai(monkeypatch)
    _html, part = _part(_b())
    langs = part[part.index("data-form-langs") :]
    langs = langs[: langs.index("</div>\n", langs.index("ff-lang-hint"))]
    box = BOX.search(langs)
    assert box, "кнопка — внутри блока языков (after_tpl)"
    box = box.group(0)
    assert re.search(r"<div[^>]* hidden[ >]", box), "без скриптов не видна"
    btn = re.search(r"<button[^>]*data-i18n-translate[ >][^>]*>", box).group(0)
    assert 'type="button"' in btn and 'data-loc="ru"' in btn and 'data-base="de"' in btn
    assert "name=" not in btn, "кнопка не отправляет форму"
    screen = re.search(r'data-screen="([^"]+)"', btn).group(1)
    assert it.screen_from(screen, connection.schema_name) == "site-schema"
    assert 'role="status"' in box and 'aria-live="polite"' in box
    assert 'id="i18n-ai-note"' in box
    assert part.count("data-i18n-translate ") == 1
    # язык — выбранный кнопкой языка (data-loc меняется вместе с панелью)
    _html, part_en = _part(_b(), "&sprache=en")
    assert 'data-loc="en"' in BOX.search(part_en).group(0)


# --- 2. без ИИ / без права / один язык — прежняя вкладка ---------------------------------


@pytest.mark.xfail(strict=True, reason="M2i-5c: кнопки ещё нет")
def test_tab_unchanged_without_ai_perm_or_languages(monkeypatch):
    b = _b(_cfg_xss())
    _ai(monkeypatch, on=False)
    _html, off = _part(b)
    assert "data-i18n-translate" not in off and "data-i18n-of" not in off
    assert "data-i18n-base" not in off
    _ai(monkeypatch, on=True, allowed=False)
    assert _part(b)[1] == off, "без права записи — байт-в-байт"
    _ai(monkeypatch, on=True)
    _html, on = _part(b)
    assert on != off
    assert MARKS.sub("", BOX.sub("", on)) == off, "кроме кнопки и пометок источника — то же"
    single = _b(locales=("de",))
    _ai(monkeypatch, on=False)
    single_off = _part(single)[1]
    _ai(monkeypatch, on=True)
    assert _part(single)[1] == single_off, "один язык — без кнопки, байт-в-байт"


# --- 3. источник перевода ------------------------------------------------------------------


def _input(part, name):
    return re.search(rf'<input type="text" id="[^"]+" name="{re.escape(name)}"[^>]*>', part).group(
        0
    )


@pytest.mark.xfail(strict=True, reason="M2i-5c: пометок источника ещё нет")
def test_source_of_each_translation(monkeypatch):
    from apps.core import form_spec

    _ai(monkeypatch)
    _html, part = _part(_b(_cfg_xss()))
    # своя подпись поля — живое значение поля подписи той же формы
    assert 'data-i18n-of="f_label_phone"' in _input(part, "f_label_phone_ru")
    # без своей подписи — то же поле (пусто → не отправляется; сайт покажет подпись языка)
    assert 'data-i18n-of="f_label_guest_count"' in _input(part, "f_label_guest_count_ru")
    assert 'data-i18n-of="f_q_q2_label"' in _input(part, "f_q_q2_label_ru")
    h_hochzeit = form_spec.text_hash("Hochzeit")
    assert 'data-i18n-base="Hochzeit"' in _input(part, f"f_et_{h_hochzeit}_ru")
    assert 'data-i18n-base="Saal"' in _input(part, f"f_q_q2_o{form_spec.text_hash('Saal')}_ru")
    xss = _input(part, f"f_q_q2_o{form_spec.text_hash(XSS)}_ru")
    assert 'data-i18n-base="&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"' in xss
    assert XSS not in part
    # каждая ссылка data-i18n-of — на поле, которое есть в этой форме
    for name in re.findall(r'data-i18n-of="([^"]+)"', part):
        assert f'name="{name}"' in part, name
    # у полей невыбранного языка (без name) — тоже пометка, но перевод идёт в выбранный
    assert 'data-i18n-of="f_label_phone"' in re.search(r'id="ff-label-phone-en"[^>]*>', part).group(
        0
    )


# --- 4. клиент на странице «Seitenaufbau» -------------------------------------------------


@pytest.mark.xfail(strict=True, reason="M2i-5c: клиента на странице ещё нет")
def test_page_carries_translate_client_once(monkeypatch):
    b = _b()
    _ai(monkeypatch, on=False)
    html_off, _ = _part(b)
    assert "__i18nTranslateBound" not in html_off
    _ai(monkeypatch)
    html, _ = _part(b)
    assert html.count(FLAG) == 1
    script = html[html.index(FLAG) - 400 : html.index("</script>", html.index(FLAG))]
    assert '"aufbau:panel"' in script and 'getAttribute("data-loc")' in script
    assert "__i18nSwitchBound" not in html, "переключатель языка форм на страницу не тащим"


# --- 5. формы кабинета (AIS-5) --------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="M2i-5c: клиент ещё внутри _i18n_switch.html")
def test_switch_includes_the_same_client(monkeypatch):
    from apps.ai import api
    from apps.core.models import Membership

    user = ais5._member(Membership.ROLE_OWNER)
    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    html = ais5._render_switch(user)
    assert html.count("window.__i18nSwitchBound = true") == 1
    assert html.count(FLAG) == 1
    assert "data-i18n-translate " in html and "TR_MSG" in html
    own = render_to_string("tenant/_i18n_translate_js.html", {})
    assert own.strip() in html, "клиент — один и тот же партиал"


# --- 6. эндпоинт AIS-5 с экрана окна ---------------------------------------------------------


@pytest.mark.urls("config.urls_tenant")
def test_endpoint_accepts_window_screen(monkeypatch):
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "hit", lambda *a, **k: False)
    monkeypatch.setattr(ratelimit, "refund", lambda *a, **k: None)
    _ai(monkeypatch)
    owner = ais5._member()
    screen = it.sign_screen(connection.schema_name, "site-schema")
    tenant = TenantFactory.build(
        schema_name="public", business_type="catering", enabled_locales=["de", "ru"]
    )
    items = [{"id": "t1", "text": "Handy", "max": 120}]
    with mock.patch.object(tasks.i18n_translate_job, "delay"):
        got = ais5._json(ais5._post(owner, items, target="ru", screen=screen, tenant=tenant))
    assert set(got) == {"job"}
    # язык не бизнеса — отказ
    got = ais5._json(ais5._post(owner, items, target="tr", screen=screen, tenant=tenant))
    assert got == {"code": "bad"}
    # форма больше лимита AIS-5 — штатный отказ, не обрезка (решение владельца)
    many = [{"id": f"t{i}", "text": f"Option {i}"} for i in range(it.MAX_ITEMS + 1)]
    got = ais5._json(ais5._post(owner, many, target="ru", screen=screen, tenant=tenant))
    assert got == {"code": "too_large"}
    # нет права записи окна — отказ
    monkeypatch.setattr(view_perms, "allowed", lambda user, name, method: False)
    got = ais5._json(ais5._post(owner, items, target="ru", screen=screen, tenant=tenant))
    assert got == {"code": "forbidden"}
