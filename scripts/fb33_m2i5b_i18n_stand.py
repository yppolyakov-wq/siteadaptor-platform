"""FB-33 M2i-5b: стенд переводов вкладки «Felder» (1440 и 390, кабинет de/ru, витрина ru, без JS).

Окно формы «Anfrage» → кнопки языка (aria-pressed) → поля перевода выбранного языка видны, других —
в DOM скрытыми → ввод перевода подписи, варианта события и своего выбора → смена языка кнопкой и
«Übernehmen» не теряют язык и введённое → Fertig + Speichern → витрина /anfrage/ на ru показывает
переводы, value вариантов — немецкие; на de — немецкие подписи. Без JS — то же серверными кнопками.
Стопка 16 T2: бизнес с основным русским (`default_locale=ru`, языки de/en/ru) — «Русский» первой
кнопкой и выбран (✓), «Deutsch (Ausgangstext)» у своей подписи и «Frage 1», «Ihre Seite zeigt
zuerst Русский.» в блоке языков (id, aria-describedby группы), `?sprache=en` помнится; негативный
контроль — бизнес с de: подписи и подсказки нет, порядок ru/en прежний.

Запуск:
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    uv run python scripts/text_pages_stand.py --jobs         # модуль заявок
    uv run python scripts/fb33_m2i5b_i18n_stand.py --setup   # языки de/ru/en и форма заявки ptx
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m2i5b_i18n_stand.py <папка скриншотов>
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import subprocess
import sys

SETUP = """
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="ptx")
t.enabled_locales = LOCALES
t.default_locale = DEFAULT
cfg = dict(t.site_config or {})
cfg["anfrage"] = {"fields": ["event_type"], "event_types": ["Hochzeit", "Firmenfeier"]}
cfg["form_fields"] = {"anfrage": {"custom": [{"id": "q1", "type": "choice", "label": "Raum",
    "options": ["Saal", "Garten"]}], "next_id": 1}}
i18n = dict(cfg.get("i18n") or {})
i18n["ru"] = {**(i18n.get("ru") or {}), "anfrage": {"event_types": ["Свадьба (стар.)"]}}
cfg["i18n"] = i18n
t.site_config = cfg
t.save(update_fields=["enabled_locales", "default_locale", "site_config"])
print("READY", t.active_locales)
"""


def setup(default: str = "de", locales=("de", "ru", "en")) -> bool:
    """Языки ptx и форма заявки с позиционным переводом (Django — через `uv run`: сам стенд
    идёт в окружении playwright без проекта). Стопка 16 T2: `default` — язык бизнеса."""
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    code = f"LOCALES = {list(locales)!r}\nDEFAULT = {default!r}\n" + SETUP
    out = subprocess.run([*cmd, "-c", code], capture_output=True, text=True, check=False)
    print(out.stdout.strip() or out.stderr[-800:])
    return "READY" in out.stdout


if sys.argv[1:] == ["--setup"]:
    sys.exit(0 if setup() else 1)

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
DLG = "dialog.ui-bwin"
WINDOW = U + "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder"
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


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


def visible(pg, scope, name):
    loc = pg.locator(f"{scope} input[name={name}]")
    return loc.count() == 1 and loc.is_visible()


def tab_flow(pg, tag, js=True):
    scope = f"{DLG} [data-form-felder]" if js else "[data-site-schema] [data-form-felder]"
    pg.goto(WINDOW)
    settle(pg, js)
    pressed = pg.eval_on_selector_all(
        f"{scope} button[name=f_sprache]",
        "bs => bs.map(b => [b.value, b.getAttribute('aria-pressed')])",
    )
    check(pressed == [["ru", "true"], ["en", "false"]], f"{tag}: кнопки языка ru/en ({pressed})")
    check(
        visible(pg, scope, "f_label_phone_ru") and not visible(pg, scope, "f_label_phone_en"),
        f"{tag}: видны поля ru, поля en — в DOM скрыты",
    )
    et = pg.locator(f"{scope} input[name^=f_et_][name$=_ru]").first
    check(
        et.input_value() == "Свадьба (стар.)",
        f"{tag}: старый позиционный перевод виден у варианта ({et.input_value()!r})",
    )
    pg.fill(f"{scope} input[name=f_label_phone_ru]", "Мобильный")
    et.fill("Свадьба")
    details = pg.locator(f"{scope} details[data-form-qo-tr]")
    check(
        details.count() == 1 and details.get_attribute("open") is None,
        f"{tag}: переводы вариантов вопроса свёрнуты (<details>), пока пусто",
    )
    details.locator("summary").click()
    pg.fill(f"{scope} input[name^=f_q_q1_o][name$=_ru] >> nth=1", "Сад")
    src = pg.locator(f"{scope} #ff-label-phone-ru-src").inner_text()
    check("Ohne" in src or "Без" in src, f"{tag}: основной текст виден под полем ({src!r})")
    named = pg.eval_on_selector_all(
        f"{scope} [name]", "es => es.filter(e => /_en$/.test(e.name)).length"
    )
    check(named == 0, f"{tag}: у полей невыбранного языка нет name ({named})")
    with pg.expect_navigation():
        pg.click(f"{scope} button[name=f_sprache][value=en]")
    settle(pg, js)
    check("sprache=en" in pg.url, f"{tag}: кнопка языка — en в адресе")
    if js:
        pg.wait_for_function("document.activeElement && document.activeElement.id", timeout=5000)
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    check(
        focus == "schema-tab-lang-en" if js else pg.url.endswith("#schema-tab-lang-en"),
        f"{tag}: после смены языка фокус/якорь — на кнопке языка ({focus!r}, {pg.url[-24:]})",
    )
    check(
        visible(pg, scope, "f_label_phone_en") and not visible(pg, scope, "f_label_phone_ru"),
        f"{tag}: после смены видны поля en",
    )
    check(
        pg.locator(f"{scope} #ff-label-phone-ru").input_value() == "Мобильный",
        f"{tag}: введённый ru-перевод не потерялся при смене языка",
    )
    pg.fill(f"{scope} input[name=f_label_phone_en]", "Mobile")
    pg.screenshot(path=f"{OUT}/m2i5b_felder_{tag}.png", full_page=not js)
    if js:
        # со скриптами правка уходит сама (change); «Übernehmen» скрыта — перезагрузка окна
        pg.keyboard.press("Tab")
        busy_done(pg)
        pg.reload()
    else:
        with pg.expect_navigation():
            pg.click(f"{scope} button[data-schema-apply]")
    settle(pg, js)
    check(
        pg.locator(f"{scope} input[name=f_label_phone_en]").input_value() == "Mobile",
        f"{tag}: перевод en записан в черновик",
    )
    check(
        "sprache=en" in pg.url
        and pg.locator(f"{scope} button[name=f_sprache][value=en]").get_attribute("aria-pressed")
        == "true",
        f"{tag}: «Übernehmen» — язык en остался",
    )
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' button[name=f_sprache]')]
           .filter(e => e.getBoundingClientRect().height < 43.5).length""",
        scope,
    )
    check(small == 0, f"{tag}: кнопки языка ≥ 44 px")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()


def storefront(pg, tag):
    pg.goto(U + "/lang/?lang=ru&next=/anfrage/")
    pg.wait_for_load_state()
    html = pg.content()
    check(
        '<option value="Hochzeit">Свадьба</option>' in html
        and '<option value="Garten">Сад</option>' in html,
        f"{tag}: витрина ru — переводы вариантов, value немецкие",
    )
    check(">Мобильный<" in html or "Мобильный" in html, f"{tag}: витрина ru — подпись «Мобильный»")
    pg.screenshot(path=f"{OUT}/m2i5b_anfrage_ru_{tag}.png", full_page=True)
    pg.goto(U + "/lang/?lang=de&next=/anfrage/")
    pg.wait_for_load_state()
    html = pg.content()
    check(
        '<option value="Hochzeit">Hochzeit</option>' in html and "Мобильный" not in html,
        f"{tag}: витрина de — немецкие подписи",
    )


BASE_NOTE = {"de": "Deutsch (Ausgangstext)", "ru": "Немецкий (исходный текст)"}
FIRST = {
    "de": "Ihre Seite zeigt zuerst Русский.",
    "ru": "Ваш сайт сначала показывает язык: Русский.",
}


def business_language(pg, tag, cab, js=True):
    """Стопка 16 T2: язык бизнеса (ru) первым и выбран, подпись немецкого поля и подсказка."""
    scope = f"{DLG} [data-form-felder]" if js else "[data-site-schema] [data-form-felder]"
    pg.goto(WINDOW)
    settle(pg, js)
    pressed = pg.eval_on_selector_all(
        f"{scope} button[name=f_sprache]",
        "bs => bs.map(b => [b.value, b.getAttribute('aria-pressed'), b.innerText.includes('✓')])",
    )
    check(
        pressed == [["ru", "true", True], ["en", "false", False]],
        f"{tag}: язык бизнеса ru — первой кнопкой, выбран, с ✓ ({pressed})",
    )
    check(
        visible(pg, scope, "f_label_phone_ru") and not visible(pg, scope, "f_label_phone_en"),
        f"{tag}: при открытии видны поля ru",
    )
    note = pg.locator(f"{scope} [data-langs-first]")
    text = note.inner_text() if note.count() == 1 else ""
    check(text == FIRST[cab], f"{tag}: подсказка «{FIRST[cab]}» в блоке языков ({text!r})")
    described = pg.locator(f"{scope} [data-form-langs] [role=group]").get_attribute(
        "aria-describedby"
    )
    check(
        note.count() == 1 and note.get_attribute("id") in (described or "").split(),
        f"{tag}: группа кнопок ссылается на подсказку ({described!r})",
    )
    check(
        note.get_attribute("role") is None and note.get_attribute("aria-live") is None,
        f"{tag}: подсказка — не живая область",
    )
    label = pg.locator(f"{scope} label[for=ff-label-phone]").inner_text()
    check(BASE_NOTE[cab] in label, f"{tag}: «{BASE_NOTE[cab]}» у своей подписи ({label!r})")
    q = pg.locator(f"{scope} label[for=ff-q-q1-label]").inner_text()
    check(BASE_NOTE[cab] in q, f"{tag}: «{BASE_NOTE[cab]}» у «Frage 1» ({q!r})")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")
    pg.screenshot(path=f"{OUT}/s16_t2_felder_ru_business_{tag}.png", full_page=not js)
    with pg.expect_navigation():
        pg.click(f"{scope} button[name=f_sprache][value=en]")
    settle(pg, js)
    check(
        "sprache=en" in pg.url
        and pg.locator(f"{scope} button[name=f_sprache][value=en]").get_attribute("aria-pressed")
        == "true"
        and visible(pg, scope, "f_label_phone_en"),
        f"{tag}: «English» кнопкой — выбран en, язык в адресе",
    )
    pg.goto(WINDOW + "&sprache=en")
    settle(pg, js)
    check(
        pg.locator(f"{scope} button[name=f_sprache][value=en]").get_attribute("aria-pressed")
        == "true",
        f"{tag}: ?sprache=en помнится при открытии",
    )
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()


def german_business(pg, tag, js=True):
    """Негативный контроль: бизнес с de — подписи и подсказки нет, порядок прежний."""
    scope = f"{DLG} [data-form-felder]" if js else "[data-site-schema] [data-form-felder]"
    pg.goto(WINDOW)
    settle(pg, js)
    order = pg.eval_on_selector_all(f"{scope} button[name=f_sprache]", "bs => bs.map(b => b.value)")
    check(order == ["ru", "en"], f"{tag}: бизнес de — порядок прежний ({order})")
    check(
        pg.locator(f"{scope} [data-langs-first]").count() == 0
        and "Ausgangstext" not in pg.locator(scope).inner_text()
        and "исходный текст" not in pg.locator(scope).inner_text(),
        f"{tag}: бизнес de — без подписи и подсказки",
    )


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    runs = [(1440, 900, "de-DE", True), (390, 844, "ru-RU", True), (1440, 900, "ru-RU", False)]
    runs.append((390, 844, "de-DE", False))
    for w, h, locale, js in runs:
        tag = f"{w}_{locale[:2]}{'' if js else '_nojs'}"
        print(f"— {tag}")
        ctx = b.new_context(
            viewport={"width": w, "height": h}, locale=locale, java_script_enabled=js
        )
        pg = ctx.new_page()
        login(pg)
        discard(pg)
        check(setup(), f"{tag}: стенд сброшен к позиционному оверлею")
        tab_flow(pg, tag, js)
        storefront(pg, tag)
        german_business(pg, tag, js)
        discard(pg)
        check(setup("ru", ("de", "en", "ru")), f"{tag}: язык бизнеса — ru")
        business_language(pg, tag, locale[:2], js)
        discard(pg)
        check(setup(), f"{tag}: язык бизнеса снова de")
        ctx.close()
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
