"""FB-33 C5: стенд вкладки «Felder» формы корзины в окне блока (Python-Playwright, не в CI).

Кафе m35b (корзина, заказ к столику): «Seitenaufbau» → «Warenkorb» → строка «form» → вкладка
«Felder». Порядок полей Name 🔒 · E-Mail · Telefon · Notiz, подсказка про столик на языке
кабинета, без немецких строк в ru; «Abbrechen» возвращает прежнее; e-mail «Nicht fragen» и свой
вопрос «Allergien» (Pflicht) → «Fertig» → «Speichern» → /warenkorb/ без e-mail и с вопросом
(required). 1440/390, кабинет de/ru, с JS и без; цели ≥ 44 px, без горизонтальной прокрутки.

    DB_NAME=<стенд-БД> uv run python scripts/fb33_m2i34_c5_window_stand.py --setup   # исходное
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8045 --settings=config.settings.stand
    DB_NAME=<стенд-БД> STAND_URL=http://m35b.siteadaptor.de:8045 \\
      uv run --with playwright==1.55.0 python scripts/fb33_m2i34_c5_window_stand.py <папка>

`--setup` возвращает настройку корзины (`form_fields.checkout`) к той, что была при первом
запуске (снимок — в файле `STAND_SNAPSHOT`, по умолчанию во временной папке); каждый прогон
начинает с неё и в конце возвращает её же.
Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import re
import subprocess
import sys
import tempfile

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "m35b"
PASSWORD = "Stand-Passwort-123"
SNAPSHOT = os.environ.get(
    "STAND_SNAPSHOT", os.path.join(tempfile.gettempdir(), "fb33_c5_checkout.json")
)

SETUP = f"""
import json, os
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
cfg = siteconfig.normalize(t.site_config or {{}})
ff = dict(cfg.get("form_fields") or {{}})
path = {SNAPSHOT!r}
if not os.path.exists(path):
    with open(path, "w") as fh:
        json.dump({{"checkout": ff.get("checkout")}}, fh)
with open(path) as fh:
    orig = json.load(fh).get("checkout")
if orig:
    ff["checkout"] = orig
else:
    ff.pop("checkout", None)
if ff:
    cfg["form_fields"] = ff
else:
    cfg.pop("form_fields", None)
t.site_config = cfg
t.save(update_fields=["site_config"])
print("READY", (t.site_config.get("form_fields") or {{}}).get("checkout"))
"""


def setup() -> bool:
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    out = subprocess.run([*cmd, "-c", SETUP], capture_output=True, text=True, check=False)
    print(out.stdout.strip()[-400:] or out.stderr[-1500:])
    return "READY" in out.stdout


if sys.argv[1:2] == ["--setup"]:
    sys.exit(0 if setup() else 1)

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", f"http://{SLUG}.{BASE}:8045")
DLG = "dialog.ui-bwin"
PAGE = U + "/dashboard/site/aufbau/?seite=cart"
WINDOW = PAGE + "&block=form&tab=felder"
TEXT = {
    "de": {
        "table": "Bei Bestellung am Tisch (QR-Code)",
        "intro": "Was der Warenkorb beim Bestellen fragt",
    },
    "ru": {
        "table": "При заказе за столиком (QR-код)",
        "intro": "Что корзина спрашивает при заказе",
    },
}
#: немецкие строки вкладки, которых в ru-кабинете быть не должно
GERMAN = ("Nicht fragen", "Eigene Fragen", "am Tisch", "Was der Warenkorb", "immer Pflicht")
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def login(pg):
    pg.goto(U + "/accounts/login/")
    pg.fill("input[name=login]", f"owner@{SLUG}.test")
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def busy_done(pg):
    pg.wait_for_timeout(300)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def settle(pg, js):
    pg.wait_for_load_state()
    if js:
        pg.wait_for_function("!document.getAnimations().length")


def discard(pg):
    pg.goto(PAGE)
    if pg.locator("button[name=op][value=discard]").count():
        pg.click("button[name=op][value=discard]")
        pg.wait_for_load_state()


def part_info(pg, scope):
    return pg.evaluate(
        """(sel) => { const f = document.querySelector(sel);
          if (!f) return null;
          const small = [...f.querySelectorAll('label, button:not(.sr-only), summary')]
            .filter(e => e.offsetParent && e.getBoundingClientRect().height < 43.5
                    && (e.querySelector('input[type=radio],input[type=checkbox]')
                        || e.tagName !== 'LABEL'))
            .map(e => e.textContent.trim().slice(0, 30));
          const checked = n => (f.querySelector(`input[name="${n}"]:checked`) || {}).value;
          return {keys: [...f.querySelectorAll('[data-form-field]')].map(e => e.dataset.formField),
            text: f.textContent.replace(/\\s+/g, ' '),
            hints: [...f.querySelectorAll('[data-form-hint]')].map(e => e.textContent.trim()),
            email: checked('f_mode_email'), small,
            questions: [...f.querySelectorAll('[data-form-question] input[type=text]')]
              .map(e => e.value),
            preset: !!f.querySelector('[data-form-preset]'),
            events: !!f.querySelector('[name=f_event_types]'),
            sw: document.documentElement.scrollWidth, iw: innerWidth};
        }""",
        scope,
    )


def submit(pg, scope, js, button=None):
    """Правка вкладки. Кнопка (`+ Frage`, «Übernehmen») — обычный POST и в окне со скриптами;
    переключатель со скриптами уходит сам фоновым запросом (через 350 мс после выбора)."""
    if js and not button:
        pg.wait_for_timeout(700)
        busy_done(pg)
        pg.reload()
    else:
        with pg.expect_navigation():
            pg.click(f"{scope} {button or 'button[data-schema-apply]'}")
    settle(pg, js)


def window_flow(pg, tag, lang, js):
    scope = f"{DLG} [data-form-felder]" if js else "[data-site-schema] [data-form-felder]"
    pg.goto(WINDOW)
    settle(pg, js)
    if js:
        check(pg.locator(DLG).count() == 1, f"{tag}: окно блока — <dialog>")
        name = pg.evaluate(
            "(s) => { const d = document.querySelector(s); const id ="
            " d && d.getAttribute('aria-labelledby'); return id &&"
            " (document.getElementById(id) || {}).textContent }",
            DLG,
        )
        check(bool((name or "").strip()), f"{tag}: у окна есть имя ({(name or '').strip()!r})")
    info = part_info(pg, scope)
    check(info is not None, f"{tag}: вкладка «Felder» открыта")
    if info is None:
        return False
    check(info["keys"] == ["name", "email", "phone", "note"], f"{tag}: порядок {info['keys']}")
    check("🔒" in info["text"], f"{tag}: имя 🔒")
    check(not info["preset"] and not info["events"], f"{tag}: без пресета и событий")
    check(TEXT[lang]["intro"] in info["text"], f"{tag}: вводная корзины на {lang}")
    check(
        any(TEXT[lang]["table"] in h for h in info["hints"]),
        f"{tag}: подсказка про столик ({info['hints']})",
    )
    if lang == "ru":
        left = [g for g in GERMAN if g in info["text"]]
        check(not left, f"{tag}: нет немецких строк ({left})")
    # M3-9c: «Übernehmen» без скриптов тоже 44 px (правило панели в app.css) — без исключений
    check(not info["small"], f"{tag}: цели ≥ 44 px ({info['small'][:4]})")
    check(info["sw"] <= info["iw"], f"{tag}: без горизонтальной прокрутки")
    pg.screenshot(path=f"{OUT}/c5_felder_{tag}.png", full_page=not js)

    # «Abbrechen» — правка уходит, черновика нет
    pg.check(f"{scope} input[name=f_mode_note][value=req]")
    if js:  # правка уходит сама; окно не перезагружаем — «Abbrechen» того же открытия
        pg.wait_for_timeout(700)
        busy_done(pg)
        dirty = pg.locator("button[name=op][value=save]").count() > 0
    else:
        submit(pg, scope, js)
        dirty = pg.locator(f"{scope} input[name=f_mode_note][value=req]").is_checked()
    check(dirty, f"{tag}: «Notiz» Pflicht — в черновике")
    revert = (
        f"{DLG} [data-window-actions] button[value=revert]"
        if js
        else ("[data-window-actions] button[value=revert]")
    )
    with pg.expect_navigation():
        pg.click(revert)
    pg.wait_for_load_state()
    pg.goto(WINDOW)
    settle(pg, js)
    check(
        pg.locator(f"{scope} input[name=f_mode_note][value=opt]").is_checked(),
        f"{tag}: «Abbrechen» — «Notiz» снова Optional",
    )

    # e-mail «Nicht fragen» и свой вопрос «Allergien» (Pflicht)
    pg.check(f"{scope} input[name=f_mode_email][value=off]")
    if js:
        submit(pg, scope, js)
    pg.fill(f"{scope} #ff-new-label", "Allergien")
    pg.check(f"{scope} input[name=f_new_req]")
    submit(pg, scope, js, "button[data-form-add]")
    info = part_info(pg, scope)
    check(info["email"] == "off", f"{tag}: e-mail «Nicht fragen» в черновике ({info['email']})")
    check(info["questions"] == ["Allergien"], f"{tag}: вопрос в черновике ({info['questions']})")
    pg.screenshot(path=f"{OUT}/c5_felder_edited_{tag}.png", full_page=not js)
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    else:
        pg.goto(PAGE)
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    return True


def storefront(b, tag, lang, js, w, h):
    ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=js)
    pg = ctx.new_page()
    pg.goto(U + f"/?hl={lang}")
    pg.goto(U + "/sortiment/")
    m = re.search(r'name="product" value="([0-9a-f-]{36})"', pg.content())
    if m:
        form = pg.locator(f'form:has(input[name=product][value="{m.group(1)}"])').first
        form.locator("button[type=submit], button:not([type])").first.click()
        pg.wait_for_load_state("networkidle")
    pg.goto(U + "/warenkorb/")
    info = pg.evaluate(
        """() => { const f = document.getElementById('checkout-form');
          if (!f) return null;
          const q = n => f.querySelector(`[name="${n}"]`);
          return {names: [...f.querySelectorAll('[name]')].map(e => e.name),
            q1: !!(q('q1') && q('q1').required), text: f.textContent,
            sw: document.documentElement.scrollWidth, iw: innerWidth}; }"""
    )
    pg.screenshot(path=f"{OUT}/c5_cart_{tag}.png", full_page=True)
    check(info is not None, f"{tag}: корзина с формой")
    if info:
        check("email" not in info["names"], f"{tag}: витрина без e-mail")
        check(info["q1"] and "Allergien" in info["text"], f"{tag}: вопрос «Allergien» required")
        check(info["sw"] <= info["iw"], f"{tag}: витрина без горизонтальной прокрутки")
    ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
    )
    for js in (True, False):
        for lang in ("de", "ru"):
            for w, h in ((1440, 900), (390, 844)):
                tag = f"{w}_{lang}{'' if js else '_nojs'}"
                print(f"— {tag}")
                check(setup(), f"{tag}: настройка корзины — исходная")
                locale = "de-DE" if lang == "de" else "ru-RU"
                ctx = b.new_context(
                    viewport={"width": w, "height": h}, locale=locale, java_script_enabled=js
                )
                pg = ctx.new_page()
                login(pg)
                discard(pg)
                if window_flow(pg, tag, lang, js):
                    storefront(b, tag, lang, js, w, h)
                ctx.close()
    b.close()
check(setup(), "настройка корзины возвращена к исходной")
print(f"{ok} ✓, {len(fail)} ✗")
for f in fail:
    print("  ✗", f)
sys.exit(1 if fail else 0)
