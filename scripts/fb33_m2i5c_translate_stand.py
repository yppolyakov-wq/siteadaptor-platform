"""FB-33 M2i-5c: стенд кнопки ИИ «🌐 Übersetzen» во вкладке «Felder» окна блока формы заявки
(Python-Playwright, не входит в CI). 1440 и 390, языки перевода ru и en, без JS; регресс AIS-5 —
форма товара (тот же клиент `_i18n_translate_js.html`).

Ответ ИИ подменён в браузере (маршрут `dashboard/uebersetzen/`): «перевод» = «<ЯЗЫК> <текст>»,
вариант «Firmenfeier» — отказ пост-проверки (пропуск). Сервер — с включённой задачей:

    uv run python scripts/text_pages_stand.py --setup           # один раз (тенант ptx, owner@ptx.test)
    uv run python scripts/text_pages_stand.py --jobs            # модуль заявок
    uv run python scripts/fb33_m2i5c_translate_stand.py --setup # языки de/ru/en и форма заявки ptx
    AI_ENABLED=True AI_TASKS_ENABLED=i18n_translate \\
      python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m2i5c_translate_stand.py <папка>

`--only-product` — только регресс формы товара (прогон до и после выноса клиента). Сервер на
другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import json
import os
import re
import subprocess
import sys

SETUP = """
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="ptx")
t.enabled_locales = ["de", "ru", "en"]
cfg = dict(t.site_config or {})
cfg["anfrage"] = {"fields": ["event_type"], "event_types": ["Hochzeit", "Firmenfeier"]}
cfg["form_fields"] = {"anfrage": {"labels": {"phone": "Handy"}, "custom": [
    {"id": "q1", "type": "choice", "label": "Raum", "options": ["Saal", "Garten"],
     "label_i18n": {"ru": "Комната"}}], "next_id": 1}}
cfg["i18n"] = {k: v for k, v in (cfg.get("i18n") or {}).items() if k not in ("ru", "en")}
t.site_config = cfg
t.save(update_fields=["enabled_locales", "site_config"])
print("READY", t.active_locales)
"""


def setup() -> bool:
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    out = subprocess.run([*cmd, "-c", SETUP], capture_output=True, text=True, check=False)
    print(out.stdout.strip() or out.stderr[-800:])
    return "READY" in out.stdout


if sys.argv[1:] == ["--setup"]:
    sys.exit(0 if setup() else 1)

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = sys.argv[1]
ONLY_PRODUCT = "--only-product" in sys.argv
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
DLG = "dialog.ui-bwin"
WINDOW = U + "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder"
ok, fail = 0, []
MODE = {"code": ""}  # "" — перевод, иначе код отказа эндпоинта
SENT = []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def fake_translate(route):
    """Ответ эндпоинта AIS-5 без модели: тот же контракт JSON (`state: done`, `items`)."""
    body = route.request.post_data or ""
    items = json.loads(re.search(r'name="items"\r\n\r\n(.*?)\r\n--', body, re.S).group(1))
    target = re.search(r'name="target"\r\n\r\n(\w+)\r\n', body).group(1)
    SENT.append((target, [i["text"] for i in items]))
    if MODE["code"]:
        data = {"code": MODE["code"]}
    else:
        got = {
            i["id"]: f"{target.upper()} {i['text']}" for i in items if i["text"] != "Firmenfeier"
        }
        data = {"state": "done", "items": got, "skipped": len(items) - len(got)}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))


def login(pg):
    pg.goto(U + "/accounts/login/")
    pg.fill("input[name=login]", "owner@ptx.test")
    pg.fill("input[name=password]", "Stand-Passwort-123")
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def busy_done(pg):
    pg.wait_for_timeout(300)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def settle(pg, js=True):
    pg.wait_for_load_state()
    if js:
        pg.wait_for_function("!document.getAnimations().length")


def discard(pg):
    pg.goto(U + "/dashboard/site/aufbau/?seite=anfrage")
    if pg.locator("button[name=op][value=discard]").count():
        pg.click("button[name=op][value=discard]")
        pg.wait_for_load_state()


def status_text(pg, scope):
    return pg.locator(f"{scope} [data-i18n-translate-status]").text_content() or ""


def wait_status(pg, scope):
    pg.wait_for_function(
        """(sel) => { const s = document.querySelector(sel + ' [data-i18n-translate-status]');
                      const b = document.querySelector(sel + ' [data-i18n-translate]');
                      return s && s.textContent && b && !b.hasAttribute('aria-busy'); }""",
        arg=scope,
        timeout=15000,
    )


def value(pg, scope, sel):
    return pg.locator(f"{scope} {sel}").input_value()


def window_flow(pg, tag, loc, w):
    scope = f"{DLG} [data-form-felder]"
    pg.goto(WINDOW + ("" if loc == "ru" else f"&sprache={loc}"))
    settle(pg)
    btn = pg.locator(f"{scope} [data-i18n-translate]")
    check(btn.count() == 1 and btn.is_visible(), f"{tag}: кнопка видна в блоке языков")
    check(btn.get_attribute("type") == "button", f"{tag}: type=button")
    check(btn.get_attribute("data-loc") == loc, f"{tag}: язык кнопки — {loc}")
    h = btn.evaluate("b => b.getBoundingClientRect().height")
    check(h >= 43.5, f"{tag}: кнопка ≥ 44 px ({h})")
    check(pg.locator(f"{scope} [data-ai-notice]").count() <= 1, f"{tag}: плашка ИИ не дублируется")
    et = pg.locator(f"{scope} input[name^=f_et_][name$=_{loc}]")
    pg.click(f"{scope} details[data-form-et-tr] summary")  # варианты события свёрнуты
    et.nth(0).fill("Мой текст" if loc == "ru" else "My text")  # заполнено владельцем
    SENT.clear()
    MODE["code"] = ""
    btn.click()
    wait_status(pg, scope)
    busy_done(pg)
    up = loc.upper()
    phone = value(pg, scope, f"input[name=f_label_phone_{loc}]")
    check(phone == f"{up} Handy", f"{tag}: своя подпись переведена ({phone!r})")
    email = value(pg, scope, f"input[name=f_label_email_{loc}]")
    check(email == "", f"{tag}: поле без своей подписи не трогается ({email!r})")
    q1 = value(pg, scope, f"input[name=f_q_q1_label_{loc}]")
    want_q1 = "Комната" if loc == "ru" else "EN Raum"
    check(
        q1 == want_q1,
        f"{tag}: вопрос — {'заполненный не тронут' if loc == 'ru' else 'переведён'} ({q1!r})",
    )
    garten = value(pg, scope, f"input[name^=f_q_q1_o][name$=_{loc}] >> nth=1")
    check(garten == f"{up} Garten", f"{tag}: вариант вопроса переведён ({garten!r})")
    check(
        et.nth(0).input_value() in ("Мой текст", "My text"),
        f"{tag}: текст владельца не перезаписан ({et.nth(0).input_value()!r})",
    )
    check(et.nth(1).input_value() == "", f"{tag}: отказ пост-проверки — поле пустое")
    check(
        pg.locator(f"{scope} details[data-form-qo-tr]").get_attribute("open") is not None,
        f"{tag}: свёрнутый список вариантов с переводом раскрыт",
    )
    texts = SENT[0][1] if SENT else []
    check(
        SENT and SENT[0][0] == loc and "Hochzeit" not in texts and "Handy" in texts,
        f"{tag}: отправлены только пустые поля выбранного языка ({SENT[:1]})",
    )
    st = status_text(pg, scope)
    check(st and "·" in st, f"{tag}: живая область — итог и пропуск ({st!r})")
    marked = pg.locator(f"{scope} [data-ai-filled]").count()
    desc = pg.locator(f"{scope} input[name=f_label_phone_{loc}]").get_attribute("aria-describedby")
    check(marked >= 2 and "i18n-ai-note" in (desc or ""), f"{tag}: пометка ИИ ({marked}, {desc!r})")
    pg.screenshot(path=f"{OUT}/m2i5c_felder_{tag}.png")
    # отказ «слишком много текста» — штатное сообщение, поля не меняются
    pg.fill(f"{scope} input[name=f_label_phone_{loc}]", "")
    MODE["code"] = "too_large"
    btn.click()
    wait_status(pg, scope)
    st = status_text(pg, scope)
    check("Zu viel Text" in st or "Слишком" in st or len(st) > 10, f"{tag}: отказ лимита ({st!r})")
    check(value(pg, scope, f"input[name=f_label_phone_{loc}]") == "", f"{tag}: при отказе пусто")
    MODE["code"] = ""
    btn.click()
    wait_status(pg, scope)
    busy_done(pg)
    # перевод ушёл в черновик сам (change → aufbau.js, как «Übernehmen») — после перезагрузки
    pg.reload()
    settle(pg)
    phone = value(pg, scope, f"input[name=f_label_phone_{loc}]")
    check(phone == f"{up} Handy", f"{tag}: перевод в черновике после перезагрузки ({phone!r})")
    # смена языка кнопкой — у новой панели свой язык, кнопка снова видна
    other = "en" if loc == "ru" else "ru"
    with pg.expect_navigation():
        pg.click(f"{scope} button[name=f_sprache][value={other}]")
    settle(pg)
    btn = pg.locator(f"{scope} [data-i18n-translate]")
    check(
        btn.is_visible() and btn.get_attribute("data-loc") == other,
        f"{tag}: после смены языка кнопка видна, язык {other}",
    )
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")
    discard(pg)


def nojs_flow(pg, tag):
    pg.goto(WINDOW)
    pg.wait_for_load_state()
    btn = pg.locator("[data-form-felder] [data-i18n-translate]")
    n = btn.count()
    check(n == 1 and not btn.is_visible(), f"{tag}: без JS кнопка в DOM, но не видна ({n})")
    check(
        pg.locator("[data-form-felder] button[data-schema-apply]").is_visible(),
        f"{tag}: без JS — «Übernehmen» на месте",
    )


def product_flow(pg, tag):
    """Регресс AIS-5: форма товара — выпадашка языка, тот же клиент."""
    pg.goto(U + "/catalog/products/new/")
    pg.wait_for_load_state()
    btn = pg.locator("[data-i18n-translate]")
    check(btn.count() == 1 and not btn.is_visible(), f"{tag}: товар — кнопка скрыта на de")
    pg.fill("input[name=name_de]", "Stand Brezel")
    pg.select_option("[data-i18n-select]", "en")
    check(btn.is_visible(), f"{tag}: товар — кнопка видна на en")
    SENT.clear()
    MODE["code"] = ""
    btn.click()
    pg.wait_for_function(
        "document.querySelector('input[name=name_en]').value !== ''", timeout=15000
    )
    name_en = pg.locator("input[name=name_en]").input_value()
    check(name_en == "EN Stand Brezel", f"{tag}: товар — name_en заполнен ({name_en!r})")
    check(
        pg.locator("input[name=name_en][data-ai-filled]").count() == 1,
        f"{tag}: товар — пометка ИИ",
    )
    pg.wait_for_function(
        "document.querySelector('[data-i18n-translate-status]').textContent !== ''", timeout=5000
    )
    st = pg.locator("[data-i18n-translate-status]").text_content() or ""
    check(bool(st), f"{tag}: товар — живая область ({st!r})")
    pg.select_option("[data-i18n-select]", "de")
    st = pg.locator("[data-i18n-translate-status]").text_content() or ""
    check(not btn.is_visible() and st == "", f"{tag}: товар — на de кнопка скрыта, статус сброшен")


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    runs = [(1440, 900, "ru"), (390, 844, "en"), (1440, 900, "en"), (390, 844, "ru")]
    for w, h, loc in runs:
        tag = f"{w}_{loc}"
        print(f"— {tag}")
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="de-DE")
        ctx.route("**/dashboard/uebersetzen/", fake_translate)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
        login(pg)
        if not ONLY_PRODUCT:
            discard(pg)
            check(setup(), f"{tag}: стенд сброшен")
            window_flow(pg, tag, loc, w)
        if loc == "en":
            product_flow(pg, tag)
        check(not errors, f"{tag}: без JS-ошибок {errors[:2]}")
        ctx.close()
    if not ONLY_PRODUCT:
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        nojs_flow(pg, "1440_nojs")
        ctx.close()
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
