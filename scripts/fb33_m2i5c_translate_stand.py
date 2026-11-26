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

`--only-t4` — только перевод частями (T4). `--only-product` — только регресс формы товара (прогон до и после выноса клиента). Сервер на
другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Итог: «N ✓, 0 ✗».

FB-33 стопка 16 T4 (`t4_flow`, кабинет de и ru, 1440 и 390, 320 px): перевод частями одним
нажатием. В форму окна добавляются поля без имени с `data-i18n-base` (в черновик не уходят),
ответ эндпоинта — через задачу (`job` → опрос через 1,5 с), чтобы видеть очередь: 80 полей —
2 части в лимитах и повтор теми же частями; поле длиннее потолка — пометка; `quota` во второй
части — в черновике значения первой; 5 частей — живая область ≤ 3 раз, `aria-busy`,
`aria-disabled`, Enter по занятой и кнопка языка не стартуют второе; подмена панели посреди
очереди — остановка с `console.error`, фокус и итог на новой кнопке; `data-status`; сервер без
деления по-прежнему отвечает `too_large` (негативный контроль).
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import json
import os
import re
import subprocess
import sys
import uuid

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
ONLY_T4 = "--only-t4" in sys.argv  # FB-33 стопка 16 T4: только перевод частями
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
DLG = "dialog.ui-bwin"
WINDOW = U + "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder"
ok, fail = 0, []
MODE = {"code": ""}  # "" — перевод, иначе код отказа эндпоинта
SENT = []
PLAN = []  # T4: ответы частей по очереди ("" — перевод, иначе код отказа)
JOBS = {}  # T4: ответ через задачу (job → опрос), иначе сразу `done`
ASYNC = {"on": False}
PEND = {"n": 0}  # T4: сколько опросов задачи отвечают «pending» (окно для подмены панели)
DRAFTS = []  # T4: POST черновика окна (правка части → aufbau.js)


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
    code = MODE["code"] or (PLAN.pop(0) if PLAN else "")
    if code:
        data = {"code": code}
    else:
        got = {
            i["id"]: f"{target.upper()} {i['text']}" for i in items if i["text"] != "Firmenfeier"
        }
        data = {"state": "done", "items": got, "skipped": len(items) - len(got)}
        if ASYNC["on"]:
            job = uuid.uuid4().hex
            JOBS[job] = [PEND["n"], data]
            data = {"job": job}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))


def fake_result(route):
    job = route.request.url.rstrip("/").rsplit("/", 1)[-1]
    entry = JOBS.get(job)
    if entry and entry[0] > 0:
        entry[0] -= 1
        data = {"state": "pending"}
    else:
        data = JOBS.pop(job, [0, {"state": "error", "code": "error"}])[1]
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


# --- FB-33 стопка 16 T4: перевод частями -----------------------------------------------------

SCOPE = f"{DLG} [data-form-felder]"


def tr_msgs(pg):
    """Строки клиента на языке кабинета — из отрисованного TR_MSG (escapejs → JSON)."""
    block = re.search(r"var TR_MSG = \{(.*?)\n  \};", pg.content(), re.S).group(1)
    return {k: json.loads(f'"{v}"') for k, v in re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', block)}


def tr_lim(pg):
    got = re.search(r"var TR_LIM = \{ items: (\d+), item: (\d+), total: (\d+) \}", pg.content())
    return {"items": int(got.group(1)), "item": int(got.group(2)), "total": int(got.group(3))}


def fmt(text, n, m=0):
    return text.replace("{n}", str(n)).replace("{m}", str(m))


def t4_open(pg, loc):
    discard(pg)
    setup()
    pg.goto(WINDOW + ("" if loc == "ru" else f"&sprache={loc}"))
    settle(pg)


def inject(pg, loc, texts):
    """Поля без имени с базой в атрибуте — в конце формы (по DOM — после настоящих)."""
    pg.evaluate(
        """([scope, loc, texts]) => {
          const f = document.querySelector(scope + ' [data-i18n-translate]').form;
          const box = document.createElement('div');
          box.setAttribute('data-t4-extra', ''); box.setAttribute('data-i18n-loc', loc);
          texts.forEach(t => { const a = document.createElement('textarea');
            a.setAttribute('data-i18n-base', t); a.rows = 1; box.appendChild(a); });
          f.appendChild(box);
        }""",
        [SCOPE, loc, texts],
    )


def observe(pg):
    """Что озвучила живая область (смены текста при aria-live ≠ off)."""
    pg.evaluate(
        """(scope) => { const st = document.querySelector(scope + ' [data-i18n-translate-status]');
          window.__t4said = [];
          new MutationObserver(() => {
            if (st.getAttribute('aria-live') !== 'off' && st.textContent) window.__t4said.push(st.textContent);
          }).observe(st, {childList: true, characterData: true, subtree: true}); }""",
        SCOPE,
    )


def queue_done(pg):
    pg.wait_for_function(
        """(scope) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
          const s = document.querySelector(scope + ' [data-i18n-translate-status]');
          return b && !b.hasAttribute('aria-busy') && s && s.textContent; }""",
        arg=SCOPE,
        timeout=60000,
    )
    busy_done(pg)


def wait_sent(pg, n):
    for _ in range(300):
        if len(SENT) >= n:
            return True
        pg.wait_for_timeout(50)
    return False


def t4_flow(pg, tag, loc):
    up = loc.upper()
    t4_open(pg, loc)
    M, lim = tr_msgs(pg), tr_lim(pg)
    check(lim["items"] >= 1 and lim["total"] >= lim["item"], f"{tag}: T4 потолки на странице {lim}")
    btn = pg.locator(f"{SCOPE} [data-i18n-translate]")
    # A. 80 полей + одно длиннее потолка → 2 части в лимитах; повтор — те же части
    long_text = ("Wort " * (lim["item"] // 5 + 2)).strip()
    inject(pg, loc, [f"Feld {k}" for k in range(1, 81)] + [long_text])
    SENT.clear()
    DRAFTS.clear()
    ASYNC["on"] = True
    observe(pg)
    btn.click()
    queue_done(pg)
    first = [list(t) for _, t in SENT]
    check(len(SENT) == 2, f"{tag}: 80 полей — 2 части ({len(SENT)})")
    check(
        all(len(t) <= lim["items"] and sum(map(len, t)) <= lim["total"] for t in first),
        f"{tag}: каждая часть в лимитах {[(len(t), sum(map(len, t))) for t in first]}",
    )
    check(all(long_text not in t for t in first), f"{tag}: поле > потолка не отправлено")
    note = pg.evaluate(
        """(scope) => { const a = [...document.querySelectorAll(scope + ' [data-t4-extra] textarea')].pop();
          const ids = (a.getAttribute('aria-describedby') || '').split(' ');
          const n = ids.map(i => document.getElementById(i)).find(e => e && e.hasAttribute('data-i18n-tr-long'));
          return n ? [n.textContent, n.offsetParent !== null] : null; }""",
        SCOPE,
    )
    check(
        note == [M["long"], True],
        f"{tag}: пометка «zu lang» у поля видна и в aria-describedby ({note})",
    )
    sent_n = sum(len(t) for t in first)
    want = f"{sent_n - 1} {M['done']} · 1 {M['skipped']} · {fmt(M['longSum'], 1)}"
    st = status_text(pg, SCOPE)
    check(st == want, f"{tag}: итог — число, «Zahlen oder Links» 1, пропуск длинного ({st!r})")
    said = pg.evaluate("window.__t4said")
    check(
        said and said[0] == fmt(M["part"], 1, 2) and said[-1] == want and len(said) <= 3,
        f"{tag}: озвучено «Teil 1 von 2» и итог ({said})",
    )
    check(len(DRAFTS) == 2, f"{tag}: правка каждой части — в черновик ({len(DRAFTS)} POST)")
    check(
        any(f'name="f_label_phone_{loc}"\r\n\r\n{up} Handy' in d for d in DRAFTS[:1]),
        f"{tag}: первая правка несёт перевод первой части",
    )
    pg.screenshot(path=f"{OUT}/s16_t4_parts_{tag}.png")
    pg.evaluate(
        """(scope) => document.querySelectorAll(scope + ' [data-ai-filled]').forEach(e => {
          e.value = ''; e.removeAttribute('data-ai-filled'); })""",
        SCOPE,
    )
    SENT.clear()
    btn.click()
    queue_done(pg)
    check([list(t) for _, t in SENT] == first, f"{tag}: повтор нажатия — те же части")
    # B. quota во второй части → в черновике значения первой, строка ошибки части
    t4_open(pg, loc)
    inject(pg, loc, [f"Feld {k}" for k in range(1, 81)])
    SENT.clear()
    DRAFTS.clear()
    PLAN[:] = ["", "quota"]
    observe(pg)
    btn.click()
    queue_done(pg)
    st = status_text(pg, SCOPE)
    check(
        st == f"{fmt(M['partFail'], 2, 2)} {M['quota']}",
        f"{tag}: quota во 2-й — строка части ({st!r})",
    )
    check(len(DRAFTS) == 1, f"{tag}: quota — один POST черновика ({len(DRAFTS)})")
    check(
        bool(DRAFTS) and f'name="f_label_phone_{loc}"\r\n\r\n{up} Handy' in DRAFTS[0],
        f"{tag}: в черновике — значения первой части",
    )
    filled = pg.evaluate(
        "(s) => [...document.querySelectorAll(s + ' [data-t4-extra] textarea')].filter(a => a.value).length",
        SCOPE,
    )
    in_first = sum(1 for t in SENT[0][1] if t.startswith("Feld ")) if SENT else -1
    check(filled == in_first, f"{tag}: заполнены поля только первой части ({filled}/{in_first})")
    said = pg.evaluate("window.__t4said")
    check(len(said) <= 3 and said[-1] == st, f"{tag}: ошибка озвучена ({said})")
    pg.reload()
    settle(pg)
    phone = value(pg, SCOPE, f"input[name=f_label_phone_{loc}]")
    check(
        phone == f"{up} Handy", f"{tag}: после ошибки перевод первой части в черновике ({phone!r})"
    )
    # C. 5+ частей: озвучка ≤ 3, aria-busy/aria-disabled, Enter и кнопка языка не стартуют второе
    t4_open(pg, loc)
    big = [(f"Satz {k} " * (lim["item"] // 8))[: lim["item"] - 100].strip() for k in range(13)]
    inject(pg, loc, big)
    SENT.clear()
    observe(pg)
    url = pg.url
    btn.click()
    wait_sent(pg, 2)
    state = pg.evaluate(
        """(scope) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
          const langs = [...b.form.querySelectorAll('[data-form-lang]')];
          return [b.form.getAttribute('aria-busy'), b.getAttribute('aria-disabled'),
                  langs.length > 0 && langs.every(x => x.getAttribute('aria-disabled') === 'true'),
                  document.activeElement === b]; }""",
        SCOPE,
    )
    check(
        state == ["true", "true", True, True],
        f"{tag}: во время очереди busy/disabled/фокус {state}",
    )
    btn.focus()
    pg.keyboard.press("Enter")
    pg.keyboard.press(" ")
    other = "en" if loc == "ru" else "ru"
    # force: Playwright ждёт снятия aria-disabled — клик нужен именно по занятой кнопке
    pg.click(f"{SCOPE} button[name=f_sprache][value={other}]", force=True, no_wait_after=True)
    pg.wait_for_timeout(300)
    check(pg.url == url and len(SENT) <= 3, f"{tag}: клик языка во время очереди не ушёл")
    queue_done(pg)
    said = pg.evaluate("window.__t4said")
    m = len(SENT)
    check(m >= 5, f"{tag}: 13 длинных полей — {m} частей")
    check(
        said and said[0] == fmt(M["part"], 1, m) and len(said) <= 3,
        f"{tag}: {m} частей — живая область {len(said)} раз ({said[:1]})",
    )
    check(pg.url == url, f"{tag}: кнопка языка во время очереди не перерисовала панель")
    after = pg.evaluate(
        """(scope) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
          return [b.form.hasAttribute('aria-busy'), b.hasAttribute('aria-disabled')]; }""",
        SCOPE,
    )
    check(after == [False, False], f"{tag}: после очереди aria-busy и aria-disabled сняты {after}")
    # D. подмена панели посреди очереди → остановка, console.error, фокус и итог — новая кнопка
    t4_open(pg, loc)
    inject(pg, loc, [f"Feld {k}" for k in range(1, 81)])
    SENT.clear()
    PEND["n"] = 3
    logs = []
    pg.on("console", lambda msg: logs.append(msg.text) if msg.type == "error" else None)
    pg.evaluate(
        "(s) => { window.__t4old = document.querySelector(s + ' [data-i18n-translate]'); }", SCOPE
    )
    btn.click()
    wait_sent(pg, 2)
    pg.evaluate(
        """(scope) => { const f = window.__t4old.form;
          const r = f.querySelector('input[type=radio][name^=f_mode_]:not(:checked)');
          r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }""",
        SCOPE,
    )
    try:
        pg.wait_for_function(
            """(scope) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
              const s = document.querySelector(scope + ' [data-i18n-translate-status]');
              return !window.__t4old.isConnected && b && s && s.textContent; }""",
            arg=SCOPE,
            timeout=30000,
        )
    except Exception:  # noqa: BLE001 — таймаут Playwright: состояние — в подпись проверки
        dbg = pg.evaluate(
            """(scope) => [window.__t4old.isConnected, !!document.querySelector(scope),
              (document.querySelector(scope + ' [data-i18n-translate-status]') || {}).textContent,
              [...document.querySelectorAll('[data-i18n-translate]')].map(b => [b.getAttribute('data-loc'),
                b.getAttribute('data-note'), b.closest(scope) !== null, b.closest('[data-i18n-translate-box]').hidden])]""",
            SCOPE,
        )
        tr_logs = [x for x in logs if "translate" in x]
        check(False, f"{tag}: подмена панели не дождались {dbg} {tr_logs}")
    busy_done(pg)
    PEND["n"] = 0
    st = status_text(pg, SCOPE)
    check(
        st == fmt(M["partFail"], 2, 2), f"{tag}: подмена панели — остановка строкой части ({st!r})"
    )
    check(any("panel replaced" in x for x in logs), f"{tag}: остановка — console.error")
    focus = pg.evaluate(
        "(s) => document.activeElement === document.querySelector(s + ' [data-i18n-translate]')",
        SCOPE,
    )
    check(focus, f"{tag}: фокус на новой кнопке «Übersetzen»")
    # E. data-status — статус в чужую живую область, своя пустая
    t4_open(pg, loc)
    pg.evaluate(
        """(scope) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
          const p = document.createElement('p'); p.id = 't4-form-status'; p.setAttribute('role', 'status');
          b.form.appendChild(p); b.setAttribute('data-status', 't4-form-status'); }""",
        SCOPE,
    )
    ASYNC["on"] = False
    btn.click()
    pg.wait_for_function("document.getElementById('t4-form-status').textContent", timeout=15000)
    busy_done(pg)
    own = status_text(pg, SCOPE)
    check(own == "", f"{tag}: data-status — своя живая область пустая ({own!r})")
    # негативный контроль: сервер без деления по-прежнему отказывает (61 текст — too_large)
    ctx = pg.context
    ctx.unroute("**/dashboard/uebersetzen/", fake_translate)
    code = pg.evaluate(
        """([scope, loc, n]) => { const b = document.querySelector(scope + ' [data-i18n-translate]');
          const body = new FormData();
          body.append('csrfmiddlewaretoken', document.querySelector('input[name=csrfmiddlewaretoken]').value);
          body.append('screen', b.getAttribute('data-screen')); body.append('target', loc);
          body.append('items', JSON.stringify([...Array(n).keys()].map(i => ({id: 't' + i, text: 'Feld ' + i}))));
          return fetch(b.getAttribute('data-url'), {method: 'POST', body, credentials: 'same-origin'})
            .then(r => r.json()).then(d => d.code); }""",
        [SCOPE, loc, lim["items"] + 1],
    )
    ctx.route("**/dashboard/uebersetzen/", fake_translate)
    check(code == "too_large", f"{tag}: негативный контроль — одним запросом too_large ({code!r})")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")
    discard(pg)


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    runs = [(1440, 900, "ru"), (390, 844, "en"), (1440, 900, "en"), (390, 844, "ru")]
    runs = [] if ONLY_T4 else runs
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
        # FB-33 стопка 16 T4: кабинет de и ru (кука языка), 1440 и 390 и 320 px
        for w, h, cab, loc in [
            (1440, 900, "de", "ru"),
            (390, 844, "ru", "en"),
            (1440, 900, "ru", "en"),
            (320, 700, "de", "ru"),
        ]:
            tag = f"t4_{w}_{cab}_{loc}"
            print(f"— {tag}")
            ctx = b.new_context(viewport={"width": w, "height": h}, locale=f"{cab}-DE")
            ctx.add_cookies([{"name": "django_language", "value": cab, "url": U}])
            ctx.route("**/dashboard/uebersetzen/", fake_translate)
            ctx.route("**/dashboard/uebersetzen/*/", fake_result)
            pg = ctx.new_page()
            pg.on(
                "request",
                lambda r: (
                    DRAFTS.append(r.post_data or "")
                    if r.method == "POST" and "/dashboard/site/aufbau/" in r.url
                    else None
                ),
            )
            errors = []
            pg.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            login(pg)
            t4_flow(pg, tag, loc)
            check(not errors, f"{tag}: без JS-ошибок {errors[:2]}")
            ASYNC["on"] = False
            PLAN.clear()
            ctx.close()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        nojs_flow(pg, "1440_nojs")
        ctx.close()
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
