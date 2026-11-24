"""FB-33 стопка 14 E9: «Abbrechen» окна блока возвращает к якорю строки схемы, сообщение — у строки.

План — `docs/fb33-stack14-plan-2026-11-24.md` §0.1 «E9», §2 «E9», §4 «E9», §10 (architect H4, L1;
a11y H1, L4). Решение владельца 2026-11-24 отменяет решение M5d-2b «сообщение вверху, якоря нет».

- POST `op=revert` → `?…&zuletzt=<ref>&abbruch=<done|conflict|same>#schema-row-<quote(ref)>`;
- GET: `abbruch` из белого списка и `zuletzt` ∈ строк схемы → статичный видимый
  `<p id="schema-cancel-msg">` прямо перед строкой, у ссылки строки — `aria-describedby`; у конфликта —
  видимый префикс «Nicht übernommen:» и оформление ошибки; вверху сообщения нет, `[data-schema-live]`
  пуст (текст туда кладёт `aufbau.js`, ветка `back`);
- без `abbruch` разметка прежняя (31 эталон не сдвигается, L1).
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
AUFBAU_JS = ROOT / "static" / "js" / "aufbau.js"

DONE = "Änderungen an diesem Block zurückgenommen."
SAME = "Nichts zurückzunehmen – der Block ist so wie beim Öffnen."
CONFLICT = (
    "Die Seite wurde inzwischen an anderer Stelle gespeichert – "
    "Abbrechen ist nicht mehr möglich. Bitte den Block prüfen."
)
PREFIX = "Nicht übernommen:"
TEXTS = {"done": DONE, "same": SAME, "conflict": CONFLICT}
RESULTS = {
    "done": aufbau_draft.CANCEL_DONE,
    "same": aufbau_draft.CANCEL_NOTHING,
    "conflict": aufbau_draft.CANCEL_CONFLICT,
}
TOKEN = "openE9a"


def said(resp, msgs):
    """E9: прежние тесты «Abbrechen» читали итог из `messages`; у строки блока он теперь в адресе
    (`abbruch`) — тот же текст дописывается к сообщениям POST (тесты M3-1b и соседей)."""
    from apps.core.site_schema_views import CANCEL_KINDS, _cancel_text

    kind = parse_qs(urlsplit(resp.get("Location", "")).query).get("abbruch", [""])[0]
    return resp, list(msgs) + ([str(_cancel_text(kind)[1])] if kind in CANCEL_KINDS else [])


def _browser(hidden=False):
    b = Browser(_shop())
    if hidden:
        b.post(seite="home", ref="t1", op="toggle", zeile="1")  # строка — в «Ausgeblendet»
    return b


def _cancel(b, ref="t1", edit=True):
    b.get(f"?seite=home&block={ref}&wopen={TOKEN}")
    if edit:
        b.post(seite="home", ref=ref, op="update", panel_present="1", f_title="Neu", f_body="X",
               wopen=TOKEN)  # fmt: skip
    resp, msgs = b.post(seite="home", ref=ref, op="revert", wopen=TOKEN)
    assert resp.status_code == 302
    return urlsplit(resp["Location"]), msgs


def _row_link(html, ref):
    """Открывающий тег ссылки строки (`id="schema-row-<ref>"`) и его позиция."""
    m = re.search(rf'<a\b[^>]*\bid="schema-row-{re.escape(ref)}"[^>]*>', html)
    assert m, ref
    return m


def _cancel_html(monkeypatch, kind, hidden=False):
    b = _browser(hidden)
    monkeypatch.setattr(aufbau_draft, "cancel", lambda *a, **kw: RESULTS[kind])
    target, _msgs = _cancel(b, edit=False)
    return target, b.get(f"?{target.query}")


# --- поведение E9 (были strict xfail в коммите замков) ------------------------------------------------------------------------------------


@pytest.mark.parametrize("hidden", [False, True], ids=["visible", "hidden"])
def test_cancel_to_row_anchor(hidden):
    """№21: после «Abbrechen» — к строке блока: якорь `#schema-row-<ref>`, `zuletzt` (раскрытый
    «Ausgeblendet» у скрытой) и итог `abbruch`; окно закрыто."""
    b = _browser(hidden)
    target, _msgs = _cancel(b)
    query = parse_qs(target.query)
    assert target.fragment == "schema-row-t1"
    assert query.get("zuletzt") == ["t1"] and query.get("abbruch") == ["done"]
    assert "block" not in query and "wopen" not in query
    html = b.get(f"?{target.query}")
    assert 'data-window-part="' not in html  # окно закрыто
    details = re.search(r"<details\b([^>]*data-schema-hidden[^>]*)>", html)
    assert (details is not None and " open" in details.group(1)) is hidden


def test_anchor_exact_ref():
    """№5: якорь — точный ref (`quote(ref, safe="")`); GET сверяет `zuletzt` со строками схемы
    точным совпадением: чужой или обрезанный ref сообщения не даёт."""
    b = _browser()
    target, _msgs = _cancel(b)
    assert target.fragment == "schema-row-" + quote("t1", safe="")
    for wrong in ("t", "t1 ", "T1", "t1x"):
        html = b.get(f"?seite=home&zuletzt={quote(wrong)}&abbruch=done")
        assert 'id="schema-cancel-msg"' not in html, wrong
    assert 'id="schema-cancel-msg"' in b.get("?seite=home&zuletzt=t1&abbruch=done")


@pytest.mark.parametrize("hidden", [False, True], ids=["visible", "hidden"])
@pytest.mark.parametrize("kind", ["done", "conflict", "same"])
def test_cancel_message_in_html_before_row(monkeypatch, kind, hidden):
    """a11y H1: сообщение — статичный видимый абзац прямо ПЕРЕД ссылкой строки (между ними нет
    другой строки), ссылка ссылается на него `aria-describedby`; у конфликта — видимый префикс
    «Nicht übernommen:» и оформление ошибки; вверху (`data-schema-messages`) сообщения нет,
    живая область при загрузке пуста."""
    _target, html = _cancel_html(monkeypatch, kind, hidden)
    msg = re.search(r'<p\b[^>]*\bid="schema-cancel-msg"[^>]*>(.*?)</p>', html, re.S)
    assert msg, kind
    text = re.sub(r"<[^>]+>", "", msg.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    assert text.endswith(TEXTS[kind])
    assert text.startswith(PREFIX) is (kind == "conflict")
    assert f'data-schema-cancel="{kind}"' in msg.group(0)
    if kind == "conflict":
        assert "red" in msg.group(0)  # оформление ошибки, не только слово
    link = _row_link(html, "t1")
    between = html[msg.end() : link.start()]
    assert "data-schema-block=" not in between and "<li" not in between
    assert re.search(r'aria-describedby="[^"]*\bschema-cancel-msg\b', link.group(0))
    top = re.search(r"<div data-schema-messages[^>]*>(.*?)</div>", html, re.S).group(1)
    assert TEXTS[kind] not in top
    assert re.search(r"<p\b[^>]*data-schema-live[^>]*></p>", html)


@pytest.mark.parametrize("kind", ["done", "conflict", "same"])
def test_cancel_msg_once(monkeypatch, kind):
    """H4: сообщение в ответе ровно одно (ни вверху, ни в живой области второго нет)."""
    _target, html = _cancel_html(monkeypatch, kind)
    assert html.count(TEXTS[kind]) == 1
    assert html.count('id="schema-cancel-msg"') == 1


def test_js_back_branch_takes_abbruch():
    """architect H4: со скриптами — НЕ второй обработчик: ветка `back` (`aufbauWindowBack`, одно
    чтение) берёт и `abbruch`, снимает его из адреса вместе с якорем, текст сообщения — через
    общую задержанную озвучку (`aufbauMoved` и «Abbrechen» — одна функция)."""
    js = AUFBAU_JS.read_text(encoding="utf-8")
    assert js.count('getItem("aufbauWindowBack"') == 1
    assert js.count("abbruch") >= 2  # чтение и снятие из адреса
    assert "schema-cancel-msg" in js
    assert js.count("function aufbauSay(") == 1
    moved = js[js.index("window.aufbauMoved = function") :]
    assert "aufbauSay(" in moved[: moved.index("};")]


# --- охранные -----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "ok", "<b>x</b>", "DONE", "nothing", "done "])
def test_abbruch_whitelisted(value):
    """№6: `abbruch` — только из белого списка: иначе сообщения нет и разметка не ломается."""
    b = _browser()
    html = b.get(f"?seite=home&zuletzt=t1&abbruch={quote(value)}")
    assert 'id="schema-cancel-msg"' not in html
    assert "<b>x</b>" not in html


def test_cancel_slot_no_golden_drift():
    """L1: без `abbruch` (и с чужим значением) разметка схемы байт-в-байт та же — условие
    стоит внутри существующих строк шаблона, 31 эталон не сдвигается."""
    b = _browser(hidden=True)
    plain = b.get("?seite=home&zuletzt=t1")
    other = b.get("?seite=home&zuletzt=t1&abbruch=bogus")
    strip = re.compile(r'name="(?:csrfmiddlewaretoken|wopen)" value="[^"]*"|wopen=[A-Za-z0-9_-]+')
    assert strip.sub("", plain) == strip.sub("", other)
    assert "schema-cancel-msg" not in plain


def test_page_row_cancel_keeps_the_top_message():
    """★-строка страницы (`__page`) — вне строк блоков: её «Abbrechen» говорит, как прежде,
    сообщением вверху (якорь строки и сообщение у строки — только у строк блоков)."""
    b = Browser(_shop())
    b.post(seite="text", op="add", type="text")
    resp, msgs = b.post(seite="text", ref="__page", op="revert", wopen=TOKEN)
    assert resp.status_code == 302
    assert msgs and "abbruch=" not in resp["Location"]
