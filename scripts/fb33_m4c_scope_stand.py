"""FB-33 M4c: стенд «Ansicht gilt für» в окне блока «Liste» (1440/390, de/ru, с JS и без).

Окно блока «Liste» с акциями типа «Räumung», вкладка «Wie anordnen»: селект «Ansicht gilt
für» с подписью и подсказкой (цель ≥ 44 px), у «Liste» с товарами его нет. «Den ganzen Typ»
→ черновик (на сайте пока ничего), предпросмотр показывает оба блока типа лентой купонов;
«Speichern» → вид у типа, оси у блока сняты; «Abbrechen» окна → как было. У блока без своих
осей поля нет — строка «folgt der Ansicht des Typs»; при «Den ganzen Typ» — видимое
предупреждение; предупреждения экрана — жёлтым. В Студии селекта
нет. Без JS: то же обычной формой с «Übernehmen».

Запуск:
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8051 --settings=config.settings.stand
    DB_NAME=<стенд-БД> STAND_URL=http://ptx.siteadaptor.de:8051 \\
        uv run --with playwright==1.55.0 python scripts/fb33_m4c_scope_stand.py <папка>
Блоки и акции стенда скрипт ставит сам перед каждым сценарием (`manage.py shell`, та же
стенд-БД). Chromium — /opt/pw-browsers/chromium (playwright install не запускать).
Итог: «N ✓, 0 ✗».
"""

import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8051")
SLUG = "ptx"
TYPE = "Räumung"
A1, A2, PR = "m4ca1", "m4ca2", "m4cpr"
ok, fail = 0, []
DLG = "dialog.ui-bwin"
LABEL = {"de": "Ansicht gilt für", "ru": "Вид применяется к"}

RESET = f"""
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
from apps.promotions.models import Promotion
t = Tenant.objects.get(schema_name={SLUG!r})
t.disabled_modules = [m for m in (t.disabled_modules or []) if m != "promotions"]
cfg = dict(t.site_config or {{}})
rows = [r for r in cfg.get("sections") or [] if r.get("id") not in ({A1!r}, {A2!r}, {PR!r})]
def block(bid, **data):
    return {{"key": "list", "id": bid, "enabled": True, "data": data}}
rows += [
    block({A1!r}, source="promotions", type={TYPE!r}, out="slider", card="coupon", title="M4c eins"),
    block({A2!r}, source="promotions", type={TYPE!r}, title="M4c zwei"),
    block({PR!r}, source="products", title="M4c Produkte"),
]
cfg["sections"] = rows
groups = dict(cfg.get("promo_groups") or {{}})
groups[{TYPE!r}] = "countdown"
cfg["promo_groups"] = groups
t.site_config = cfg
t.save(update_fields=["site_config", "disabled_modules"])
with schema_context({SLUG!r}):
    if not Promotion.objects.filter(group={TYPE!r}).exists():
        for n in (1, 2, 3):
            Promotion.objects.create(title={{"de": f"Räumung {{n}}"}}, status="active",
                promo_type="discount", discount_percent=10 * n, group={TYPE!r})
print("READY")
"""

STATE = f"""
import json
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
cfg = siteconfig.normalize(Tenant.objects.get(schema_name={SLUG!r}).site_config)
row = next(r for r in cfg["sections"] if r.get("id") == {A1!r})
print("STATE" + json.dumps({{"type": cfg["promo_groups"].get({TYPE!r}), "data": row["data"]}}))
"""


def shell(code: str) -> str:
    res = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode:
        print(res.stderr[-2000:])
        raise SystemExit("stand: manage.py shell failed")
    return res.stdout


def reset():
    assert "READY" in shell(RESET)


def state() -> dict:
    out = shell(STATE)
    return json.loads(out[out.index("STATE") + 5 :].splitlines()[0])


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


def window(pg, ref):
    pg.goto(U + f"/dashboard/site/aufbau/?seite=home&block={ref}&tab=wie")


def idle(pg):
    pg.wait_for_timeout(600)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=20000
    )


def strips(pg, js=True):
    """Сколько блоков типа в предпросмотре черновика — лентой купонов."""
    page = pg.context.new_page()
    page.goto(U + "/?preview=1&aufbau=home")
    n = page.evaluate(
        "() => [document.querySelectorAll('[data-promo-strip]').length,"
        " document.querySelectorAll('[data-card-form=\"coupon\"]').length]"
    )
    page.close()
    return n


def run(b, w, h, lang, js=True):
    tag = f"{w}_{lang}" + ("" if js else "_nojs")
    print(f"— {w}px {lang}" + ("" if js else " без JS"))
    reset()
    ctx = b.new_context(
        viewport={"width": w, "height": h}, locale=f"{lang}-DE", java_script_enabled=js
    )
    ctx.add_cookies([{"name": "django_language", "value": lang, "url": U}])
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    login(pg)
    root = f"{DLG}[open]" if js else "aside#schema-panel"

    # 1. поле: только у «Liste» с типом акции; подпись, подсказка, цель
    window(pg, PR)
    pg.wait_for_selector(root, timeout=15000)
    check(pg.locator("select[name=f_scope]").count() == 0, "у «Liste» с товарами поля нет")
    window(pg, A1)
    pg.wait_for_selector(root, timeout=15000)
    sel = pg.locator(f"{root} form[data-schema-listview] select[name=f_scope]")
    check(sel.count() == 1 and sel.is_visible(), "селект «Ansicht gilt für» во «Wie anordnen»")
    label = pg.locator(f"{root} label[for=schema-l-scope]")
    check(
        label.count() == 1 and label.inner_text().strip() == LABEL[lang], f"подпись «{LABEL[lang]}»"
    )
    hint = pg.locator("#schema-l-scope-hint")
    check(
        hint.count() == 1
        and TYPE in hint.inner_text()
        and sel.get_attribute("aria-describedby") == "schema-l-scope-hint",
        "подсказка с именем типа связана с полем",
    )
    sel.scroll_into_view_if_needed()
    box = sel.bounding_box()
    check(box and box["height"] >= 44, f"цель ≥ 44 px ({box and round(box['height'])})")
    check(sel.input_value() == "", "по умолчанию «Nur diesen Block»")
    option = sel.locator("option[value=type]").inner_text().strip()
    check(option.endswith(f": {TYPE}"), f"имя типа в варианте ({option})")
    check(pg.locator("#schema-l-scope-warn").count() == 0, "без выбора предупреждения нет")
    if js:
        pg.wait_for_function("!document.getAnimations().length")
    pg.screenshot(path=f"{OUT}/m4c_window_{tag}.png")
    wide = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    check(not wide, "нет горизонтальной прокрутки")

    # 2. «Den ganzen Typ» → черновик; на сайте ничего; предпросмотр — вид типа у обоих блоков
    sel.select_option("type")
    if js:
        idle(pg)
    else:
        pg.locator("form[data-schema-listview] button[name=op][value=update]").click()
        pg.wait_for_load_state()
    sel = pg.locator("select[name=f_scope]")
    check(sel.input_value() == "type", "выбор «Den ganzen Typ» держится в окне")
    warn = pg.locator("#schema-l-scope-warn")
    look = (
        warn.evaluate(
            "e => [getComputedStyle(e).backgroundColor, parseFloat(getComputedStyle(e).fontSize)]"
        )
        if warn.count()
        else ["", 0]
    )
    check(
        warn.count() == 1
        and warn.is_visible()
        and "schema-l-scope-warn" in (sel.get_attribute("aria-describedby") or "")
        and look[1] >= 14
        and look[0] not in ("rgba(0, 0, 0, 0)", "rgb(249, 250, 251)"),
        f"предупреждение видно, не серое, связано с полем ({look})",
    )
    check(
        pg.locator("[data-schema-inherit]").count() == 0
        or "nur für diesen Block" not in pg.locator("[data-schema-inherit]").inner_text(),
        "строка наследования не говорит «nur für diesen Block»",
    )
    check(
        pg.locator("input[name=f_out][value=slider]").is_checked(),
        "оси блока в окне — как были (Slider)",
    )
    st = state()
    check(st["type"] == "countdown" and st["data"].get("card") == "coupon", "на сайте пока ничего")
    n = strips(pg)
    check(n[0] >= 2 and n[1] >= 2, f"предпросмотр: оба блока типа — лентой купонов ({n})")
    pg.screenshot(path=f"{OUT}/m4c_type_{tag}.png")

    # 3. «Speichern» → вид у типа, оси у блока сняты
    pg.goto(U + "/dashboard/site/aufbau/?seite=home")
    pg.locator("button[name=op][value=save]").first.click()
    pg.wait_for_load_state()
    st = state()
    entry = st["type"] if isinstance(st["type"], dict) else {}
    check(
        entry.get("card") == "coupon"
        and (entry.get("layout") or {}).get("scroll") is True
        and entry.get("style") == "countdown",
        f"«Speichern»: вид у типа ({st['type']})",
    )
    check(
        not {"out", "card", "scope"} & set(st["data"]), f"оси у блока сняты ({sorted(st['data'])})"
    )
    # 4. блок без своих осей (второй блок типа и первый после записи): поля нет, строка-подсказка
    for ref in (A1, A2):
        window(pg, ref)
        pg.wait_for_selector(root, timeout=15000)
        note = pg.locator("[data-schema-scope-note]")
        check(
            pg.locator("select[name=f_scope]").count() == 0
            and note.count() == 1
            and note.is_visible()
            and TYPE in note.inner_text(),
            f"{ref}: без своих осей — поля нет, блок следует виду типа",
        )
    if js:
        pg.wait_for_function("!document.getAnimations().length")
    pg.screenshot(path=f"{OUT}/m4c_note_{tag}.png")
    check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
    ctx.close()


def cancel(b, js=True):
    """«Abbrechen» окна возвращает блок и выбор охвата; черновика нет."""
    print("— Abbrechen" + ("" if js else " без JS"))
    reset()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=js)
    pg = ctx.new_page()
    login(pg)
    before = state()
    window(pg, A1)
    pg.locator("select[name=f_scope]").select_option("type")
    if js:
        idle(pg)
    else:
        pg.locator("form[data-schema-listview] button[name=op][value=update]").click()
        pg.wait_for_load_state()
    check(pg.locator("select[name=f_scope]").input_value() == "type", "охват выбран")
    pg.locator("form[data-window-actions] button[name=op][value=revert]").first.click()
    pg.wait_for_load_state()
    if js:
        idle(pg)
    pg.goto(U + "/dashboard/site/aufbau/?seite=home")
    check(pg.locator("[data-schema-draft]").count() == 0, "после «Abbrechen» черновика нет")
    window(pg, A1)
    check(
        pg.locator("select[name=f_scope]").input_value() == "", "охват — снова «Nur diesen Block»"
    )
    check(state() == before, "на сайте — как было")
    ctx.close()


def warning(b):
    """Предупреждение экрана — жёлтым (не «успехом»): «Abbrechen» окна без правок, без JS."""
    print("— жёлтое сообщение")
    reset()
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        window(pg, A1)
        pg.locator("form[data-window-actions] button[name=op][value=revert]").first.click()
        pg.wait_for_load_state()
        msg = pg.locator("[data-schema-messages] [role=status]").first
        bg = msg.evaluate("e => getComputedStyle(e).backgroundColor") if msg.count() else ""
        check(
            msg.count() == 1
            and msg.inner_text().strip().startswith("⚠")
            and bg == "rgb(255, 251, 235)",
            f"{w}: предупреждение жёлтым со знаком ⚠ ({bg})",
        )
        pg.screenshot(path=f"{OUT}/m4c_warning_{w}.png")
        ctx.close()


def studio(b):
    print("— Студия")
    reset()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    login(pg)
    pg.goto(U + "/dashboard/site/home/")
    pg.wait_for_load_state()
    check(pg.locator(f"[name^=cb_{A1}_]").count() >= 1, "строка «Liste» в Студии есть")
    check(
        pg.locator("[data-lb-scope-row], [name$=_scope], #lb-type-views").count() == 0,
        "в Студии «Ansicht gilt für» нет",
    )
    check(pg.locator(f"[name=cb_{A1}_speed]").count() == 1, "темп ленты — на месте")
    check(not errs, "Студия без JS-ошибок: " + "; ".join(errs[:2]))
    pg.screenshot(path=f"{OUT}/m4c_studio.png")
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for width, height in ((1440, 900), (390, 844)):
        for language in ("de", "ru"):
            run(browser, width, height, language)
            run(browser, width, height, language, js=False)
    cancel(browser)
    cancel(browser, js=False)
    warning(browser)
    studio(browser)
    browser.close()
print(f"\n{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
