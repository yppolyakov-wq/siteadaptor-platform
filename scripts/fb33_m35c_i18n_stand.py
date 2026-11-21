"""FB-33 M3-5c: стенд переводов текстов блока в окне «Seitenaufbau» (1440 и 390, кабинет de/ru,
со скриптами и без).

Окно блока «Text» (вкладка «Texte») → кнопки языка (aria-pressed, 44 px) → видны поля перевода
выбранного языка, других — в DOM скрыты и без name → ввод ru → смена языка кнопкой (адрес
`sprache`, фокус/якорь на кнопке) не теряет введённое → en → «Fertig» + «Speichern» → витрина
на ru/en показывает перевод, на de — немецкий. Правка немецкого текста снимает перевод поля
(«Abbrechen» возвращает). Окно FAQ — поля перевода у вопросов.

Запуск:
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    uv run python scripts/fb33_m35c_i18n_stand.py --setup    # языки de/ru/en, блок «Text», FAQ
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m35c_i18n_stand.py <папка скриншотов>
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import subprocess
import sys

SETUP = """
from apps.tenants.models import Tenant
from apps.tenants import siteconfig
t = Tenant.objects.get(schema_name="ptx")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {})
rows = [r for r in cfg["sections"] if r.get("id") != "st35c"]
rows.insert(1, {"key": "text", "id": "st35c", "enabled": True,
    "data": {"title": "Willkommen bei uns", "body": "Schön, dass Sie da sind."}})
for r in rows:
    if r.get("key") == "faq":
        r["enabled"] = True
cfg["sections"] = rows
cfg["faq"] = [{"q": "Haben Sie Parkplätze?", "a": "Ja, vor dem Haus."},
    {"q": "Kann ich reservieren?", "a": "Gern telefonisch."}]
cfg["i18n"] = {"ru": {"faq": [{"q": "Есть парковка?"}]}}
t.site_config = cfg
t.save(update_fields=["enabled_locales", "default_locale", "site_config"])
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
WINDOW = U + "/dashboard/site/aufbau/?seite=home&block=st35c&tab=texte"
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
    pg.goto(U + "/dashboard/site/aufbau/?seite=home")
    if pg.locator("button[name=op][value=discard]").count():
        pg.click("button[name=op][value=discard]")
        pg.wait_for_load_state()


def field(pg, scope, name):
    return pg.locator(f"{scope} [name={name}]")


def visible(pg, scope, name):
    loc = field(pg, scope, name)
    return loc.count() == 1 and loc.is_visible()


def apply(pg, scope, js):
    """Применить форму окна: со скриптами — сама (change) и перезагрузка, без — «Übernehmen»."""
    if js:
        pg.keyboard.press("Tab")
        busy_done(pg)
        pg.reload()
    else:
        with pg.expect_navigation():
            pg.click(f"{scope} button[name=op][value=update]:not(.sr-only)")
    settle(pg, js)


def geometry(pg, scope, tag):
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' button[name=f_sprache]')]
           .filter(e => e.getBoundingClientRect().height < 43.5).length""",
        scope,
    )
    check(small == 0, f"{tag}: кнопки языка ≥ 44 px")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{tag}: без горизонтальной прокрутки ({sw})")


def text_flow(pg, tag, js=True):
    root = DLG if js else "[data-site-schema]"
    scope = f"{root} #bw-form-fields"
    pg.goto(WINDOW)
    settle(pg, js)
    pressed = pg.eval_on_selector_all(
        f"{scope} button[name=f_sprache]",
        "bs => bs.map(b => [b.value, b.getAttribute('aria-pressed')])",
    )
    check(pressed == [["ru", "true"], ["en", "false"]], f"{tag}: кнопки языка ru/en ({pressed})")
    check(
        visible(pg, scope, "f_tr_title_ru")
        and pg.locator(f"{scope} #schema-f-title-en").count()
        and not pg.locator(f"{scope} #schema-f-title-en").is_visible(),
        f"{tag}: видны поля ru, поля en — в DOM скрыты",
    )
    named = pg.eval_on_selector_all(
        f"{scope} [name]", "es => es.filter(e => /_en$/.test(e.name)).length"
    )
    check(named == 0, f"{tag}: у полей невыбранного языка нет name ({named})")
    check(
        pg.locator(f"{root} [data-schema-translate]").count() == 0,
        f"{tag}: прежней ссылки «Übersetzungen auf der Seite bearbeiten» нет",
    )
    src = pg.locator(f"{scope} #schema-f-title-ru-src").inner_text()
    check("Willkommen" in src, f"{tag}: под полем — что покажет сайт без перевода ({src!r})")
    geometry(pg, scope, tag)
    pg.fill(f"{scope} [name=f_tr_title_ru]", "Добро пожаловать")
    with pg.expect_navigation():
        pg.click(f"{scope} button[name=f_sprache][value=en]")
    settle(pg, js)
    check("sprache=en" in pg.url, f"{tag}: кнопка языка — en в адресе")
    if js:
        pg.wait_for_function("document.activeElement && document.activeElement.id", timeout=5000)
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    check(
        focus == "schema-tab-lang-en" if js else pg.url.endswith("#schema-tab-lang-en"),
        f"{tag}: после смены языка фокус/якорь — на кнопке языка ({focus!r})",
    )
    check(
        pg.locator(f"{scope} #schema-f-title-ru").input_value() == "Добро пожаловать",
        f"{tag}: введённый ru-перевод не потерялся при смене языка",
    )
    pg.fill(f"{scope} [name=f_tr_title_en]", "Welcome")
    pg.screenshot(path=f"{OUT}/m35c_texte_{tag}.png", full_page=not js)
    apply(pg, scope, js)
    check(
        field(pg, scope, "f_tr_title_en").input_value() == "Welcome",
        f"{tag}: перевод en записан в черновик, язык en остался",
    )
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    for lang, want in (("ru", "Добро пожаловать"), ("en", "Welcome"), ("de", "Willkommen bei uns")):
        pg.goto(U + f"/lang/?lang={lang}&next=/")
        pg.wait_for_load_state()
        check(want in pg.content(), f"{tag}: витрина {lang} — «{want}»")
    pg.screenshot(path=f"{OUT}/m35c_home_en_{tag}.png", full_page=False)


def german_flow(pg, tag, js=True):
    root = DLG if js else "[data-site-schema]"
    scope = f"{root} #bw-form-fields"
    pg.goto(WINDOW)
    settle(pg, js)
    check(
        field(pg, scope, "f_tr_title_ru").input_value() == "Добро пожаловать",
        f"{tag}: сохранённый перевод виден в окне",
    )
    pg.fill(f"{scope} #schema-f-title", "Herzlich willkommen")
    if js:
        # со скриптами поле применяется само (окно не перерисовывается); перезагрузка начала бы
        # новое открытие окна — «Abbrechen» прямо в этом окне
        pg.keyboard.press("Tab")
        busy_done(pg)
        live = pg.locator(f"{root} [data-form-status]").inner_text()
        check(
            "Übersetzung entfernt" in live or "Перевод удал" in live,
            f"{tag}: живая область окна — снятый перевод ({live!r})",
        )
    else:
        apply(pg, scope, js)
        check(
            field(pg, scope, "f_tr_title_ru").input_value() == "",
            f"{tag}: правка немецкого текста сняла перевод поля",
        )
        note = pg.locator("[data-schema-messages]").inner_text()
        check(
            "Übersetzung entfernt" in note or "Перевод удал" in note, f"{tag}: сообщение ({note!r})"
        )
    if js:
        pg.click(f"{root} [data-window-actions] button[value=revert]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    else:
        with pg.expect_navigation():
            pg.click(f"{root} [data-window-actions] button[value=revert]")
    settle(pg, js)
    pg.goto(WINDOW)
    settle(pg, js)
    check(
        field(pg, scope, "f_tr_title_ru").input_value() == "Добро пожаловать",
        f"{tag}: «Abbrechen» вернул перевод",
    )
    discard(pg)


def faq_flow(pg, tag, js=True):
    root = DLG if js else "[data-site-schema]"
    scope = f"{root} #bw-form-faq"
    pg.goto(U + "/dashboard/site/aufbau/?seite=home&block=faq&tab=texte")
    settle(pg, js)
    check(
        visible(pg, scope, "faq_0_q_ru")
        and field(pg, scope, "faq_0_q_ru").input_value() == "Есть парковка?",
        f"{tag}: FAQ — поле перевода у вопроса с переводом",
    )
    geometry(pg, scope, tag + " FAQ")
    pg.screenshot(path=f"{OUT}/m35c_faq_{tag}.png", full_page=not js)


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
        check(setup(), f"{tag}: стенд сброшен")
        text_flow(pg, tag, js)
        german_flow(pg, tag, js)
        faq_flow(pg, tag, js)
        ctx.close()
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
