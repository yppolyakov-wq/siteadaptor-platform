"""FB-33 M3-5a: стенд вкладки «Texte» окна блока (1440 и 390, кабинет de/ru, с JS и без).

Без JS: набрал во «Texte» → клик «Wie anordnen» (кнопка формы вкладки) → текст в черновике и
открыта «Wie»; Enter в поле — остаётся на «Texte»; отказ (небезопасная ссылка) — остаётся на
«Texte»; потолки ввода и подсказки. С JS (окно): вкладки — обычные вкладки (кнопки без
отправки), набрал → «Wie» → текст в черновике; без окна (`?drawer=`) переключатель и сразу клик
по вкладке — одна отправка. «Felder»: фокус после «+ Frage»/↑/Entfernen — на вопрос; сообщение о
сброшенном переводе — в живой области блока языков.

Запуск (как fb33_m3_window_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    uv run python scripts/text_pages_stand.py --jobs         # модуль заявок (вкладка «Felder»)
    uv run python scripts/fb33_m3_5a_texte_stand.py --setup  # языки de/ru, блоки стенда, вопрос
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_5a_texte_stand.py <папка>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Правки стенд оставляет
только в черновике и в конце его отбрасывает.
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import subprocess
import sys

SETUP = """
from apps.tenants.models import Tenant
from apps.tenants import siteconfig
t = Tenant.objects.get(schema_name="ptx")
t.enabled_locales = ["de", "ru"]
cfg = siteconfig.normalize(t.site_config)
rows = [s for s in cfg["sections"] if s.get("id") not in ("s5at", "s5ab")]
for s in rows:
    if s.get("key") == "usp_bar":
        s["enabled"] = True
rows += [
    {"key": "text", "id": "s5at", "enabled": True, "data": {"title": "Hallo", "body": "Welt"}},
    {"key": "button", "id": "s5ab", "enabled": True, "data": {"label": "Los", "url": "/x"}},
]
cfg["sections"] = rows
cfg["form_fields"] = {"anfrage": {"custom": [
    {"id": "q1", "type": "choice", "label": "Raum", "options": ["Saal", "Garten"],
     "options_i18n": {"Saal": {"ru": "Зал"}}},
    {"id": "q2", "type": "text", "label": "Budget"}], "next_id": 2}}
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
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
DLG = "dialog.ui-bwin"
PAGE = U + "/dashboard/site/aufbau/?seite=home"
TEXT = PAGE + "&block=s5at"
BUTTON = PAGE + "&block=s5ab"
USP = PAGE + "&block=usp_bar"
FELDER = U + "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder"
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def settle(pg):
    pg.wait_for_function("document.fonts.status === 'loaded' && !document.getAnimations().length")


def busy_done(pg):
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def login(pg):
    # язык кабинета — из Accept-Language (контекст браузера `locale`), выбора в сессии нет
    pg.goto(U + "/accounts/login/")
    pg.fill("input[name=login]", "owner@ptx.test")
    pg.fill("input[name=password]", "Stand-Passwort-123")
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def post(pg, **fields):
    with pg.expect_navigation():
        pg.evaluate(
            """(fields) => {
              const csrf = document.querySelector('input[name=csrfmiddlewaretoken]').value;
              const f = document.createElement('form');
              f.method = 'post'; f.action = '/dashboard/site/aufbau/';
              for (const [k, v] of [['csrfmiddlewaretoken', csrf], ...Object.entries(fields)]) {
                const i = document.createElement('input'); i.type = 'hidden';
                i.name = k; i.value = v; f.appendChild(i);
              }
              document.body.appendChild(f); HTMLFormElement.prototype.submit.call(f);
            }""",
            fields,
        )


def discard(pg, seite):
    pg.goto(U + f"/dashboard/site/aufbau/?seite={seite}")
    if pg.locator("button[name=op][value=discard]").count():
        post(pg, seite=seite, op="discard")


def draft_title(pg):
    """Заголовок блока в черновике — по свежей странице (без окна: `?drawer=`)."""
    pg.goto(TEXT + "&tab=texte")
    settle(pg)
    return pg.locator("#schema-f-title").input_value()


def small_targets(pg, scope):
    return pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' :is(a,button,input,textarea)')]
          .filter(e => e.getClientRects().length && !e.classList.contains('sr-only'))
          .filter(e => !(e.tagName === 'A' && getComputedStyle(e).display === 'inline'))
          .filter(e => e.getBoundingClientRect().height < 43.5)
          .map(e => e.tagName + ':' + (e.textContent || e.name || '').trim().slice(0, 14))""",
        scope,
    )


def window_tabs(pg, tag):
    """С JS: окно, вкладки — APG-вкладки (кнопки не отправляют), набранное уходит в черновик."""
    pg.goto(TEXT + "&tab=texte")
    settle(pg)
    wie = pg.locator(f"{DLG} [data-window-tab-link=wie]")
    attrs = wie.evaluate(
        "b => [b.tagName, b.type, b.getAttribute('form'), b.getAttribute('name'),"
        " b.getAttribute('role'), b.getAttribute('aria-selected')]"
    )
    check(
        attrs == ["BUTTON", "button", None, None, "tab", "false"],
        f"{tag}: «Wie» — вкладка без отправки ({attrs})",
    )
    title = f"{DLG} #schema-f-title"
    check(pg.locator(title).get_attribute("maxlength") == "200", f"{tag}: maxlength заголовка")
    pg.fill(title, f"JS {tag}")
    wie.click()
    check(
        pg.locator(f"{DLG} [data-window-tab=wie]").is_visible()
        and not pg.locator(f"{DLG} [data-window-tab=texte]").is_visible(),
        f"{tag}: клик по «Wie» — вкладка на месте",
    )
    busy_done(pg)
    check("tab=wie" in pg.url, f"{tag}: адрес помнит вкладку")
    pg.screenshot(path=f"{OUT}/m35a_js_wie_{tag}.png")
    pg.goto(TEXT + "&tab=texte&drawer=/dashboard/")
    settle(pg)
    now = pg.locator("#schema-f-title").input_value()
    check(now == f"JS {tag}", f"{tag}: набранное в черновике ({now!r})")
    # Enter в поле окна — не переключает вкладку
    pg.goto(TEXT + "&tab=texte")
    settle(pg)
    pg.fill(title, f"Enter {tag}")
    pg.press(title, "Enter")  # со скриптами правка уходит fetch'ем, страница остаётся
    pg.wait_for_timeout(300)
    busy_done(pg)
    settle(pg)
    check(
        pg.locator(f"{DLG} [data-window-tab=texte]").is_visible(),
        f"{tag}: Enter в поле — осталась «Texte»",
    )
    small = small_targets(pg, f"{DLG} [data-window-tabs]")
    check(not small, f"{tag}: вкладки ≥ 44 px ({small})")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")
    pg.screenshot(path=f"{OUT}/m35a_js_texte_{tag}.png")
    pg.goto(TEXT + "&tab=texte&drawer=/dashboard/")
    now = pg.locator("#schema-f-title").input_value()
    check(now == f"Enter {tag}", f"{tag}: Enter — текст записан ({now!r})")


def one_post(pg, tag):
    """С JS без окна (`?drawer=`): переключатель вида полосы доверия и сразу «Wie» — одна
    отправка, вид записан."""
    pg.goto(USP + "&tab=texte&drawer=/dashboard/")
    settle(pg)
    if not pg.locator("[data-schema-panel] [data-window-tab-link=wie]").count():
        check(False, f"{tag}: у полосы доверия нет вкладки «Wie» — сценарий не проверен")
        return
    posts = []
    pg.on(
        "request",
        lambda r: posts.append(r.url) if r.method == "POST" and "/site/aufbau/" in r.url else None,
    )
    pg.locator("[data-schema-usp] [data-schema-style-pick] summary").click()
    radio = pg.locator("[data-schema-usp] input[name=f_style]:not(:checked)").first
    value = radio.get_attribute("value")
    radio.locator("xpath=..").click()
    with pg.expect_navigation():
        pg.click("[data-schema-panel] [data-window-tab-link=wie]")
    settle(pg)
    pg.wait_for_timeout(800)
    check(len(posts) == 1, f"{tag}: переключатель → сразу вкладка = одна отправка ({len(posts)})")
    check("tab=wie" in pg.url, f"{tag}: открыта «Wie»")
    pg.goto(USP + "&tab=texte&drawer=/dashboard/")
    now = pg.locator("[data-schema-usp] input[name=f_style]:checked").get_attribute("value")
    check(now == value, f"{tag}: вид записан один раз ({now!r} == {value!r})")


def felder(pg, tag):
    """«Felder»: фокус после «+ Frage» / ↑ / Entfernen — на вопрос (список); сброшенный
    перевод — в живой области блока языков, общая живая область окна его не повторяет."""
    pg.goto(FELDER)
    settle(pg)
    pg.fill(f"{DLG} input[name=f_new_label]", f"Neu {tag}")
    pg.click(f"{DLG} [data-form-add]")
    pg.wait_for_selector(f"{DLG} [data-form-question] input[value='Neu {tag}']", timeout=15000)
    settle(pg)
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    added = pg.locator(f"{DLG} [data-form-question]").last.get_attribute("id")
    check(
        focus == added and focus.startswith("schema-tab-q-n"), f"{tag}: «+ Frage» → фокус ({focus})"
    )
    box = pg.locator(f"{DLG} [data-form-question]").last
    with pg.expect_navigation():
        box.locator("button[value^='up:']").click()
    settle(pg)
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    check(focus == added, f"{tag}: ↑ → фокус на том же вопросе ({focus})")
    pg.wait_for_function(
        "() => (document.querySelector('dialog.ui-bwin [data-form-status]') || {}).textContent",
        timeout=5000,
    )
    said = pg.locator(f"{DLG} [data-form-status]").inner_text()
    common = pg.locator(f"{DLG} [data-bwin-status]").inner_text()
    check(said and said not in common, f"{tag}: ↑ — объявлено во вкладке ({said!r}), не дважды")
    box = pg.locator(f"{DLG} #{added}")
    with pg.expect_navigation():
        box.locator("button[value^='del:']").click()
    settle(pg)
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    check(
        focus.startswith("schema-tab-q-") and focus != added,
        f"{tag}: Entfernen → фокус на соседнем вопросе ({focus})",
    )
    pg.screenshot(path=f"{OUT}/m35a_felder_{tag}.png")
    status = f"{DLG} [data-form-status]"
    check(pg.locator(status).count() == 1, f"{tag}: живая область вкладки «Felder»")
    options = f"{DLG} #ff-q-q1-options"
    pg.fill(options, "Halle\nGarten")
    pg.locator(f"{DLG} #ff-q-q1-label").focus()  # change по уходу из поля
    busy_done(pg)
    pg.wait_for_function(
        "s => (document.querySelector(s) || {}).textContent", arg=status, timeout=5000
    )
    said = pg.locator(status).inner_text()
    check("Saal" in said, f"{tag}: сброшенный перевод — в блоке языков ({said[:60]!r})")
    common = pg.locator(f"{DLG} [data-bwin-status]").inner_text()
    check("Saal" not in common, f"{tag}: общая живая область не повторяет ({common[:40]!r})")


def nojs(b):
    for w, h, lang in ((1440, 900, "de"), (390, 844, "ru")):
        tag = f"nojs-{w}-{lang}"
        ctx = b.new_context(
            viewport={"width": w, "height": h}, java_script_enabled=False, locale=lang
        )
        pg = ctx.new_page()
        login(pg)
        discard(pg, "home")
        pg.goto(TEXT + "&tab=texte")
        nav = pg.locator("[data-window-tabs]")
        kinds = nav.locator("[data-window-tab-link]").evaluate_all(
            "l => l.map(e => e.tagName + ':' + e.getAttribute('data-window-tab-link'))"
        )
        check(kinds == ["BUTTON:wie", "A:texte"], f"{tag}: «Wie» — кнопка формы ({kinds})")
        hint = pg.locator("#schema-f-title-max").inner_text()
        check("200" in hint, f"{tag}: подсказка потолка ({hint!r})")
        pg.fill("#schema-f-title", f"Ohne JS {w}")
        with pg.expect_navigation():
            pg.click("[data-window-tab-link=wie]")
        check("tab=wie" in pg.url and pg.url.endswith("#schema-tab-wie"), f"{tag}: открыта «Wie»")
        check(
            pg.locator("[data-window-tab=wie]").is_visible()
            and pg.locator("[data-window-tab=texte]").is_hidden(),
            f"{tag}: видна «Wie»",
        )
        pg.screenshot(path=f"{OUT}/m35a_nojs_wie_{w}.png")
        pg.goto(TEXT + "&tab=texte")
        now = pg.locator("#schema-f-title").input_value()
        check(now == f"Ohne JS {w}", f"{tag}: набранное в черновике ({now!r})")
        # Enter в поле — «Übernehmen», вкладка та же
        pg.fill("#schema-f-title", f"Enter {w}")
        with pg.expect_navigation():
            pg.press("#schema-f-title", "Enter")
        check("tab=wie" not in pg.url and "tab=texte" in pg.url, f"{tag}: Enter — осталась «Texte»")
        check(pg.locator("#schema-f-title").input_value() == f"Enter {w}", f"{tag}: Enter записал")
        # отказ: небезопасная ссылка кнопки — без перехода
        pg.goto(BUTTON + "&tab=texte")
        pg.fill("#schema-f-url", "javascript:alert(1)")
        with pg.expect_navigation():
            pg.click("[data-window-tab-link=wie]")
        check("tab=texte" in pg.url and "tab=wie" not in pg.url, f"{tag}: отказ — осталась «Texte»")
        check(pg.locator("[data-schema-messages] [role=alert]").count() == 1, f"{tag}: отказ виден")
        check(pg.locator("#schema-f-url").get_attribute("maxlength") == "500", f"{tag}: url ≤ 500")
        pg.screenshot(path=f"{OUT}/m35a_nojs_refused_{w}.png")
        # «Felder» без JS: якорь после ↓ — вопрос
        pg.goto(FELDER)
        with pg.expect_navigation():
            pg.locator("[data-form-question]").first.locator("button[value^='down:']").click()
        check(pg.url.endswith("#schema-tab-q-q1"), f"{tag}: «Felder» ↓ — якорь вопроса")
        discard(pg, "home")
        discard(pg, "anfrage")
        ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for w, h, lang in ((1440, 900, "de"), (390, 844, "ru")):
        tag = f"{w}-{lang}"
        print(f"— {tag}")
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale=lang)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        login(pg)
        discard(pg, "home")
        discard(pg, "anfrage")
        window_tabs(pg, tag)
        one_post(pg, tag)
        felder(pg, tag)
        check(not errors, f"{tag}: без ошибок скриптов ({errors[:2]})")
        discard(pg, "home")
        discard(pg, "anfrage")
        ctx.close()
    nojs(b)
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
