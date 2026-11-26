"""FB-33 стопка 16 T4: ИИ-перевод частями (клиент `tenant/_i18n_translate_js.html`).

Решение владельца (план `docs/fb33-stack16-plan-2026-11-26.md` §0.1 №2): одно нажатие
«🌐 Übersetzen» — клиент делит пустые поля на части по серверным потолкам и шлёт их по
очереди; статус «Teil N von M»; ошибка части не теряет уже переведённое. Сервер
(`i18n_translate.parse_items`, `translate_views`) не ослабляется — делит клиент.

Замки (§4 T4; поведение в браузере — стенд `scripts/fb33_m2i5c_translate_stand.py`):
1. потолки клиента — из констант сервера (подмена констант меняет вывод), чисел в шаблоне нет;
2. сервер по-прежнему отказывает `too_large` (защита не ослаблена);
3. следующая часть после `done` не получает `busy`;
4. строки частей — ровно msgid §5.2 через `{% blocktrans … asvar %}`, других форм нет;
5. у клиента есть сообщение на каждый код ошибки сервера (без тихой ветки);
6. правка части уходит в черновик «тихо»: `aufbau.js` не озвучивает «Übernommen» второй раз.
"""

import ast
import re
import uuid
from pathlib import Path
from unittest import mock

import polib
import pytest
from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from django.template.loader import render_to_string
from django.utils import translation

from apps.core import i18n_translate as it
from apps.core import tasks
from apps.core.tests import test_ais5_translate as ais5

ROOT = Path(settings.BASE_DIR)
CLIENT = ROOT / "templates/tenant/_i18n_translate_js.html"
AUFBAU = ROOT / "static/js/aufbau.js"
PART_WORK = "Teil %(n)s von %(m)s wird übersetzt …"
PART_FAIL = (
    "Teil %(n)s von %(m)s nicht übersetzt. Bereits übersetzte Felder bleiben erhalten "
    "— bitte erneut versuchen."
)
LONG_FIELD = "übersprungen: zu lang für die automatische Übersetzung"
LONG_SUM = "Übersprungen, zu lang für die automatische Übersetzung: %(n)s"


def _client(lang="de"):
    with translation.override(lang):
        return render_to_string("tenant/_i18n_translate_js.html", {})


# --- 1. потолки клиента — из сервера -----------------------------------------------------


@pytest.mark.xfail(strict=True, reason="T4: клиент частями ещё не написан")
def test_client_limits_come_from_server_constants(monkeypatch):
    monkeypatch.setattr(it, "MAX_ITEMS", 37)
    monkeypatch.setattr(it, "ITEM_MAX", 1234)
    monkeypatch.setattr(it, "TOTAL_MAX", 4321)
    html = _client()
    got = re.search(r"var TR_LIM = \{([^}]*)\}", html)
    assert got, "клиент несёт потолки одним объектом TR_LIM"
    nums = dict(re.findall(r"(\w+): (\d+)", got.group(1)))
    assert nums == {"items": "37", "item": "1234", "total": "4321"}
    source = CLIENT.read_text()
    for literal in ("60", "2000", "6000"):
        assert not re.search(rf"(?<![\d.]){literal}(?!\d)", source), f"число {literal} в шаблоне"


def test_server_limits_unchanged():
    def items(texts):
        return ais5.json.dumps([{"id": f"t{i}", "text": t} for i, t in enumerate(texts)])

    assert len(it.parse_items(items(["Wort"] * it.MAX_ITEMS))) == it.MAX_ITEMS
    with pytest.raises(it.BadRequest) as exc:
        it.parse_items(items(["Wort"] * (it.MAX_ITEMS + 1)))
    assert exc.value.code == "too_large"
    full = ["a" * it.ITEM_MAX] * (it.TOTAL_MAX // it.ITEM_MAX)
    assert sum(len(t) for t in full) == it.TOTAL_MAX
    assert len(it.parse_items(items(full))) == len(full)
    with pytest.raises(it.BadRequest) as exc:
        it.parse_items(items([*full, "b"]))
    assert exc.value.code == "too_large"
    with pytest.raises(it.BadRequest) as exc:
        it.parse_items(items(["a" * (it.ITEM_MAX + 1)]))
    assert exc.value.code == "too_large"
    assert (it.MAX_ITEMS, it.ITEM_MAX, it.TOTAL_MAX) == (60, 2000, 6000)


# --- 3. очередь частей на сервере --------------------------------------------------------


@pytest.mark.django_db
def test_next_part_not_busy_after_done(monkeypatch):
    from apps.core import ratelimit

    monkeypatch.setattr(it, "cache", LocMemCache(f"s16-t4-{uuid.uuid4().hex}", {}))
    monkeypatch.setattr(ratelimit, "hit", lambda *a, **k: False)
    monkeypatch.setattr(ratelimit, "refund", lambda *a, **k: None)
    from apps.ai import api

    monkeypatch.setattr(api, "is_enabled", lambda task=None: True)
    monkeypatch.setattr(
        it, "translate", lambda items, **kw: ({i["id"]: f"EN {i['text']}" for i in items}, "")
    )
    owner = ais5._member()
    with mock.patch.object(tasks.i18n_translate_job, "delay"):
        first = ais5._json(ais5._post(owner, [{"id": "t1", "text": "Teil eins"}]))
    # пока первая часть идёт — вторая «busy» (сервер держит одну задачу)
    with mock.patch.object(tasks.i18n_translate_job, "delay"):
        assert ais5._json(ais5._post(owner, [{"id": "t2", "text": "Teil zwei"}])) == {
            "code": "busy"
        }
    from django.db import connection

    it.run_job(schema=connection.schema_name, user_pk=owner.pk, job=first["job"])
    assert ais5._json(ais5._get(owner, first["job"]))["state"] == "done"
    with mock.patch.object(tasks.i18n_translate_job, "delay"):
        second = ais5._json(ais5._post(owner, [{"id": "t2", "text": "Teil zwei"}]))
    assert set(second) == {"job"}, "после done следующая часть не busy"


# --- 4. строки частей = msgid §5.2 ---------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="T4: клиент частями ещё не написан")
def test_part_status_strings_are_plan_msgids():
    source = CLIENT.read_text()
    blocks = re.findall(r"\{% blocktrans ([^%]*)%\}(.*?)\{% endblocktrans %\}", source, re.S)
    found = {}
    for args, body in blocks:
        assert "asvar" in args, "строка со счётчиком — через blocktrans … asvar"
        msgid = re.sub(r"\{\{ (\w+) \}\}", r"%(\1)s", body)
        found[msgid] = args
    assert PART_WORK in found and PART_FAIL in found, sorted(found)
    assert LONG_SUM in found
    parts = [m for m in found if m.startswith("Teil ")]
    assert sorted(parts) == sorted([PART_WORK, PART_FAIL]), "ровно две строки частей"
    for msgid in (PART_WORK, PART_FAIL, LONG_SUM):
        assert 'n="{n}"' in found[msgid]
    assert 'm="{m}"' in found[PART_WORK] and 'm="{m}"' in found[PART_FAIL]
    assert f"_('{LONG_FIELD}')" in source
    for po_path in sorted(ROOT.glob("locale/*/LC_MESSAGES/django.po")):
        entries = {e.msgid: e for e in polib.pofile(str(po_path))}
        for msgid in (PART_WORK, PART_FAIL, LONG_SUM, LONG_FIELD):
            assert msgid in entries, (po_path, msgid)
            if "%(" in msgid:
                assert "python-format" in entries[msgid].flags, (po_path, msgid)
    for text in (source, AUFBAU.read_text()):
        assert "Wird übersetzt … Teil" not in text
        assert "· Teil" not in text
    de, ru = _client("de"), _client("ru")
    assert "Teil {n} von {m} wird übersetzt …" in de
    assert "%(" not in de.split("<script>", 1)[1] and "%%" not in de
    assert "Переводится часть {n} из {m} …" in ru


# --- 5. каждый код ошибки сервера ----------------------------------------------------------


def _server_codes() -> set[str]:
    codes: set[str] = set()
    for rel in ("apps/core/translate_views.py", "apps/core/i18n_translate.py"):
        tree = ast.parse((ROOT / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "code"
                        and isinstance(value, ast.Constant)
                    ):
                        codes.add(value.value)
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "BadRequest"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                codes.add(node.args[0].value)
            if isinstance(node, ast.BoolOp):  # `getattr(exc, "code", "") or "unavailable"`
                codes |= {v.value for v in node.values if isinstance(v, ast.Constant) and v.value}
    from apps.ai import errors

    for obj in vars(errors).values():
        if isinstance(obj, type) and issubclass(obj, errors.AIError):
            codes.add(obj.code)
    return {c for c in codes if isinstance(c, str)}


@pytest.mark.xfail(strict=True, reason="T4: клиент частями ещё не написан")
def test_client_handles_every_server_error_code():
    codes = _server_codes()
    assert {"quota", "error", "busy", "forbidden", "unavailable", "bad", "disabled"} <= codes
    assert "too_large" in codes
    html = _client()
    table = re.search(r"var TR_CODE = \{(.*?)\};", html, re.S)
    assert table, "у клиента таблица кодов TR_CODE"
    keys = set(re.findall(r"(\w+): TR_MSG\.\w+", table.group(1)))
    missing = (codes | {"slow"}) - keys
    assert not missing, f"коды без сообщения: {sorted(missing)}"
    # неизвестный код — не тихо: сообщение об ошибке и console.error
    assert "unknown translate code" in html


# --- 6. одна озвучка: правка частей в черновик — «тихая» --------------------------------------


@pytest.mark.xfail(strict=True, reason="T4: клиент частями ещё не написан")
def test_part_change_is_quiet_in_aufbau():
    html = _client()
    assert 'new CustomEvent("change", { bubbles: true, detail: { quiet: true } })' in html
    js = AUFBAU.read_text()
    assert "e.detail && e.detail.quiet" in js
    assert re.search(r"function apply\(form, target, quiet\)", js)
