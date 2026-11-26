"""FB-33 стопка 16 T1a: стенд переводов полосы доверия в окне блока «Vorteile» → «Texte».

Кит `shop` стенд-БД владельца (демо-киты, `seed_demo_tenants --kit shop …`): пункты A, B, C, у A и
B — перевод ru, у C — нет. Обход `matrix()` (1440/390, кабинет de/ru, без JS и с JS) + 320 px:
кнопки языка формы USP (свой ns — id `schema-tab-lang-usp-<код>`, ✓ и `aria-pressed`), поля
перевода у пункта (подпись «„…“ – Übersetzung (…)», «Ohne Übersetzung:», `maxlength` 120/200),
ввод перевода C → «↓» у A (перевод едет с A, введённое у C осталось) → Enter в поле перевода —
«Übernehmen» (порядок не меняется) → «✕» у B → «＋ Punkt» без полей перевода → кнопка языка en
(якорь/фокус на её id) → «Fertig» + «Speichern» → витрина ru: переводы на своих пунктах; витрина
de — немецкое; негативный контроль — новый пункт на ru показывает немецкий текст.

Запуск (стенд-БД — копия `platform_m39_stand`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_s16_t1a_usp_stand.py --setup
    DB_CONN_MAX_AGE=0 DB_NAME=<стенд-БД> REDIS_CACHE_URL=redis://localhost:6379/<N> \\
        uv run python manage.py runserver 0.0.0.0:<порт> --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> DB_NAME=<стенд-БД> \\
        uv run --no-project --with playwright python scripts/fb33_s16_t1a_usp_stand.py <папка>
Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import subprocess
import sys

import standlib as sl

EMAIL = "shop@example.com"
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
SETUP = """
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="shop")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {})
cfg["usp_bar"] = [
    {"icon": "bio", "label": "Frisch gebacken", "text": "Jeden Morgen"},
    {"icon": "local", "label": "Aus Solingen", "text": "Seit 1950"},
    {"icon": "clock", "label": "Ab 6 Uhr"},
]
for s in cfg["sections"]:
    if s.get("key") == "usp_bar":
        s["enabled"] = True
i18n = dict(cfg.get("i18n") or {})
i18n["ru"] = {**(i18n.get("ru") or {}), "usp_bar": [
    {"label": "Свежая выпечка", "text": "Каждое утро"},
    {"label": "Из Золингена", "text": "С 1950 года"},
]}
for loc in ("en", "tr", "uk"):
    (i18n.get(loc) or {}).pop("usp_bar", None)
cfg["i18n"] = i18n
t.site_config = cfg
t.save(update_fields=["enabled_locales", "default_locale", "site_config"])
from django.core.cache import cache
cache.clear()
print("READY")
"""


def setup() -> bool:
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    out = subprocess.run([*cmd, "-c", SETUP], capture_output=True, text=True, check=False)
    ok = "READY" in out.stdout
    if not ok:
        print(out.stdout[-400:], out.stderr[-800:])
    return ok


if sys.argv[1:] == ["--setup"]:
    sys.exit(0 if setup() else 1)

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://shop.siteadaptor.de:8000").rstrip("/")
WINDOW = U + "/dashboard/site/aufbau/?seite=home&block=usp_bar&tab=texte"
DLG = "dialog.ui-bwin"
rep = sl.Report()


def scope_of(js):
    return f"{DLG} #bw-form-usp" if js else "[data-site-schema] #bw-form-usp"


def busy_done(pg):
    pg.wait_for_timeout(400)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def labels(pg, sc):
    return pg.eval_on_selector_all(
        f"{sc} input[name$=_label][name^=f_usp_]", "es => es.map(e => e.value)"
    )


def submit(pg, js, selector):
    """Кнопка формы окна: обычный POST (и со скриптами — ждём новую страницу)."""
    with pg.expect_navigation():
        pg.click(selector)
    sl.settle(pg, js)


def flow(pg, tag, js, w):
    sc = scope_of(js)
    pg.goto(WINDOW)
    sl.settle(pg, js)
    pressed = pg.eval_on_selector_all(
        f"{sc} button[name=f_sprache]", "bs => bs.map(b => [b.id, b.getAttribute('aria-pressed')])"
    )
    rep.check(
        pressed == [["schema-tab-lang-usp-ru", "true"], ["schema-tab-lang-usp-en", "false"]],
        f"{tag}: кнопки языка USP — свой ns, ru выбран ({pressed})",
    )
    ru0 = pg.locator(f"{sc} #bw-usp-0-label-ru")
    rep.check(
        ru0.is_visible() and ru0.input_value() == "Свежая выпечка",
        f"{tag}: поле перевода пункта 1 видно, перевод ru на месте",
    )
    rep.check(pg.locator(f"{sc} #bw-usp-0-label-en").is_hidden(), f"{tag}: поле en — в DOM скрыто")
    label = pg.locator(f"{sc} label[for=bw-usp-0-label-ru]").inner_text()
    rep.check("Frisch gebacken" in label, f"{tag}: подпись поля цитирует немецкий ({label!r})")
    rep.check(
        pg.locator(f"{sc} #bw-usp-0-label-ru").get_attribute("maxlength") == "120"
        and pg.locator(f"{sc} #bw-usp-0-text-ru").get_attribute("maxlength") == "200",
        f"{tag}: maxlength 120/200",
    )
    rep.check(
        pg.locator(f"{sc} #bw-usp-2-text-ru").count() == 0,
        f"{tag}: у пункта без немецкого текста нет поля перевода текста",
    )
    first = pg.eval_on_selector(
        f"{sc}",
        "f => { const b = f.querySelector('button'); "
        "return [b.value, b.tabIndex, b.hasAttribute('aria-hidden')] }",
    )
    rep.check(first == ["update", -1, False], f"{tag}: первая кнопка — «Übernehmen» ({first})")
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' button[name=f_sprache],' + sel +
           ' button[name=f_usp_move],' + sel + ' button[name=f_usp_remove]')]
           .filter(e => e.offsetParent && e.getBoundingClientRect().height < 43.5).length""",
        sc,
    )
    rep.check(small == 0, f"{tag}: кнопки языка и ↑/↓/✕ ≥ 44 px")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag}: без гор. прокрутки ({over}px)", code="overflow")
    sl.a11y_check(rep, pg, tag, scope=sc, minimum=44)
    sl.shot(pg, OUT, f"t1a_usp_{tag.replace(' ', '_')}")
    if w < 400:
        return  # телефон: вид, цели и прокрутка; поток правок — на 1440
    # ввод перевода C и «↓» у A в той же форме
    pg.fill(f"{sc} #bw-usp-2-label-ru", "С 6 утра")
    if js:
        busy_done(pg)
    submit(pg, js, f"{sc} button[name=f_usp_move][value='0:down']")
    sc = scope_of(js)
    rep.check(
        labels(pg, sc)[:3] == ["Aus Solingen", "Frisch gebacken", "Ab 6 Uhr"],
        f"{tag}: «↓» — порядок ({labels(pg, sc)})",
    )
    vals = [pg.locator(f"{sc} #bw-usp-{i}-label-ru").input_value() for i in range(3)]
    rep.check(
        vals == ["Из Золингена", "Свежая выпечка", "С 6 утра"],
        f"{tag}: переводы едут со своими пунктами, введённое у C осталось ({vals})",
    )
    # Enter в поле перевода — «Übernehmen», не ↓/✕ первого пункта
    pg.fill(f"{sc} #bw-usp-0-text-ru", "С 1950")
    if js:
        pg.press(f"{sc} #bw-usp-0-text-ru", "Enter")
        busy_done(pg)
        pg.reload()
        sl.settle(pg, js)
    else:
        with pg.expect_navigation():
            pg.press(f"{sc} #bw-usp-0-text-ru", "Enter")
        sl.settle(pg, js)
    rep.check(
        labels(pg, sc)[:3] == ["Aus Solingen", "Frisch gebacken", "Ab 6 Uhr"]
        and pg.locator(f"{sc} #bw-usp-0-text-ru").input_value() == "С 1950",
        f"{tag}: Enter в поле перевода — «Übernehmen» ({labels(pg, sc)})",
    )
    # «✕» у пункта B (теперь первый)
    submit(pg, js, f"{sc} button[name=f_usp_remove][value='0']")
    rep.check(
        labels(pg, sc)[:2] == ["Frisch gebacken", "Ab 6 Uhr"]
        and pg.locator(f"{sc} #bw-usp-0-label-ru").input_value() == "Свежая выпечка",
        f"{tag}: «✕» уносит свой перевод",
    )
    # «＋ Punkt» — без полей перевода до «Speichern»
    pg.click(f"{sc} [data-schema-usp-new] summary")
    pg.fill(f"{sc} input[name=f_usp_2_label]", "Neu im Laden")
    if js:
        pg.keyboard.press("Tab")  # со скриптами правка уходит по `change`
        busy_done(pg)
        pg.reload()
        sl.settle(pg, js)
    else:
        submit(pg, js, f"{sc} button.ui-btn-primary[value=update]")
    rep.check(
        "Neu im Laden" in labels(pg, sc) and pg.locator(f"{sc} #bw-usp-2-label-ru").count() == 0,
        f"{tag}: новый пункт — без полей перевода ({labels(pg, sc)})",
    )
    # кнопка языка en: якорь/фокус — на её id (ns)
    submit(pg, js, f"{sc} #schema-tab-lang-usp-en")
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    rep.check(
        pg.url.endswith("#schema-tab-lang-usp-en") or focus == "schema-tab-lang-usp-en",
        f"{tag}: после кнопки языка — её якорь/фокус ({focus!r}, {pg.url[-28:]})",
    )
    rep.check(
        pg.locator(f"{sc} #bw-usp-0-label-en").is_visible()
        and pg.locator(f"{sc} #bw-usp-0-label-ru").input_value() == "Свежая выпечка",
        f"{tag}: видны поля en, ru-перевод не потерян",
    )
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    with pg.expect_navigation():
        pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    storefront(pg, tag)


def storefront(pg, tag):
    for lang, want, unwanted in (
        ("ru", ["Свежая выпечка", "С 6 утра", "Neu im Laden"], ["Frisch gebacken"]),
        ("de", ["Frisch gebacken", "Ab 6 Uhr", "Neu im Laden"], ["Свежая выпечка"]),
    ):
        pg.goto(f"{U}/lang/?lang={lang}&next=/")
        pg.wait_for_load_state()
        html = pg.content()
        got = [w for w in want if w in html]
        bad = [w for w in unwanted if w in html]
        rep.check(got == want and not bad, f"{tag}: витрина {lang} — {got}, лишнее {bad}")
        if lang == "ru":
            rep.check(
                "Aus Solingen" not in html and "Из Золингена" not in html,
                f"{tag}: витрина ru — удалённый пункт ушёл с переводом",
            )
        sl.shot(pg, OUT, f"t1a_store_{lang}_{tag.replace(' ', '_')}", full=True)


with sl.launch() as browser:
    combos = list(sl.matrix()) + [(320, 640, "de", True), (720, 450, "ru", True)]
    for w, h, lang, js in combos:
        if not setup():
            rep.check(False, "setup")
            break
        pg = sl.open_page(browser, w, h, js=js, lang=lang, url=U)
        tag = f"{w} {lang} {'js' if js else 'nojs'}"
        if rep.check(sl.login(pg, U, EMAIL, PASSWORD), f"{tag}: вход"):
            flow(pg, tag, js, w)
            rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
        pg.context.close()
rep.finish("T1a USP")
