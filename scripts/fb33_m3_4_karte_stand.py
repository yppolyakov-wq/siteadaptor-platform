"""FB-33 M3-4: стенд вкладки «Karte» окна блока (макет M0-2), 1440 и 390, de и ru, со скриптами
и без: товары и акции на сетке, ленте и прайс-листе (у прайс-листа вкладки нет), две группы
«Wie eine Kachel / Zeile aussieht», «Wie im Design: X · ändern», «zurücksetzen», плашка
«N … haben eine eigene Kartenform» с «anzeigen», «Abbrechen» возвращает форму.

Запуск (как fb33_m3_3_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    uv run python scripts/fb33_m3_4_karte_stand.py --setup   # товары, акции и блоки стенда
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_4_karte_stand.py <папка>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Правки стенд оставляет
только в черновике и в конце его отбрасывает.
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import subprocess
import sys

SLUG = "ptx"

#: товары: 2 со своей формой, 1 — с формой категории; акции: 1 со своей формой; блоки главной
SETUP = f"""
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions.tests.factories import PromotionFactory
tenant = Tenant.objects.get(schema_name={SLUG!r})
with schema_context({SLUG!r}):
    from apps.catalog.models import Category, Product
    from apps.promotions.models import Promotion
    Product.objects.filter(sku__startswith="M34-").delete()
    Category.objects.filter(slug__startswith="m34-").delete()
    Promotion.objects.filter(title__de__startswith="M34 ").delete()
    tee = CategoryFactory(slug="m34-tee", name={{"de": "Tee", "en": "Tea"}})
    kraut = CategoryFactory(slug="m34-kraut", name={{"de": "Kräuter", "en": "Herbs"}},
        card_style="lookbook")
    for i, (cat, form) in enumerate([(tee, "overlay"), (tee, "overlay"), (tee, ""),
                                     (tee, ""), (kraut, "")]):
        ProductFactory(category=cat, card_style=form, sku=f"M34-{{i}}",
            name={{"de": f"M34 Tee {{i}}", "en": f"M34 Tea {{i}}"}})
    for i, form in enumerate(["coupon", "", ""]):
        PromotionFactory(card_style=form, title={{"de": f"M34 Aktion {{i}}", "en": f"M34 Promo {{i}}"}})
cfg = dict(tenant.site_config or {{}})
keep = [s for s in cfg.get("sections") or [] if not str(s.get("id", "")).startswith("m34")]
blocks = [
    {{"key": "list", "id": "m34g", "enabled": True, "data": {{"source": "products"}}}},
    {{"key": "list", "id": "m34s", "enabled": True, "data": {{"source": "products", "out": "slider"}}}},
    {{"key": "list", "id": "m34p", "enabled": True,
      "data": {{"source": "products", "style": "preisliste"}}}},
    {{"key": "list", "id": "m34a", "enabled": True, "data": {{"source": "promotions"}}}},
]
if not any(s.get("key") == "products" for s in keep):
    keep.append({{"key": "products", "enabled": True}})
cfg["sections"] = keep + blocks
tenant.site_config = cfg
tenant.save(update_fields=["site_config"])
print("M34 READY")
"""


def setup():
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
        capture_output=True,
        text=True,
        check=False,
    )
    print((out.stdout + out.stderr)[-1500:])
    sys.exit(0 if "M34 READY" in out.stdout else 1)


if len(sys.argv) > 1 and sys.argv[1] == "--setup":
    setup()

from playwright.sync_api import sync_playwright  # noqa: E402 — после --setup (там его нет)

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
ok, fail = 0, []
DLG = "dialog.ui-bwin"
KARTE = f"{DLG} [data-window-tab=karte]"
FORM = f"{DLG} #bw-form-card_pick"

#: подписи по языку кабинета
TEXT = {
    "de": {
        "tile": "Wie eine Kachel aussieht",
        "row": "Wie eine Zeile aussieht",
        "first": "Standard",
        "inherit": "Wie im Design: Standard",
        "own3": "3 Produkte haben eine eigene Kartenform",
        "own1": "1 Aktion hat eine eigene Kartenform",
        "show": "anzeigen",
    },
    "ru": {
        "tile": "Как выглядит плитка",
        "row": "Как выглядит строка",
        "first": "Стандартный",
        "inherit": "Как в дизайне: ",
        "own3": "3 товара имеют свою форму карточки",
        "own1": "1 акция имеет свою форму карточки",
        "show": "показать",
    },
}


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


def discard(pg):
    pg.goto(U + "/dashboard/site/aufbau/?seite=home")
    if pg.locator("button[name=op][value=discard]").count():
        post(pg, seite="home", op="discard")


def small_targets(pg, scope):
    return pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' :is(a,button,summary,select,input,textarea)')]
          .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
          .filter(e => !(e.tagName === 'A' && getComputedStyle(e).display === 'inline'))
          .map(e => (e.type === 'radio' || e.type === 'checkbox') ? (e.closest('label') || e) : e)
          .filter(e => e.getBoundingClientRect().height < 44)
          .map(e => e.tagName + ':' + (e.textContent || e.name || '').trim().slice(0, 14) + ':'
            + e.getBoundingClientRect().height.toFixed(1))""",
        scope,
    )


def open_karte(pg, ref):
    pg.goto(U + f"/dashboard/site/aufbau/?seite=home&block={ref}&tab=karte")
    settle(pg)


def checked(pg, scope=FORM):
    return pg.locator(f"{scope} input[name=f_card]:checked").get_attribute("value")


def radios(pg, shape):
    return pg.locator(f"{FORM} [data-schema-card-shape={shape}] input[name=f_card]").evaluate_all(
        "l => l.map(i => i.value)"
    )


def products_grid(pg, w, lang):
    t = TEXT[lang]
    open_karte(pg, "m34g")
    check(pg.locator(KARTE).is_visible(), f"{w}/{lang}: вкладка «Karte» открыта")
    legends = pg.locator(f"{FORM} legend").all_inner_texts()
    check(legends == [t["tile"], t["row"]], f"{w}/{lang}: две группы ({legends})")
    tiles, rows = radios(pg, "tile"), radios(pg, "row")
    check(
        tiles == ["", "overlay", "etikett", "regal", "lookbook"] and rows == ["compact", "deal"],
        f"{w}/{lang}: плитки и строки по геометрии ({tiles} · {rows})",
    )
    first = pg.locator(f"{FORM} label:has(input[value='']) .font-semibold").inner_text()
    check(first == t["first"], f"{w}/{lang}: первая плитка «{first}»")
    line = pg.locator(f"{DLG} [data-schema-card-inherit]").inner_text()
    check(line.startswith(t["inherit"]), f"{w}/{lang}: строка наследования ({line!r})")
    link = pg.locator(f"{DLG} [data-schema-card-inherit-link]").get_attribute("href")
    check("#dd-product_card_form" in (link or ""), f"{w}/{lang}: «ändern» ведёт в Design")
    check(
        not pg.locator(f"{FORM} button[value=update]").is_visible(),
        f"{w}/{lang}: «Übernehmen» скрыта (плитки применяются сами)",
    )
    note = pg.locator(f"{DLG} [data-schema-card-own]")
    text = note.inner_text()
    check(t["own3"] in text and t["show"] in text, f"{w}/{lang}: плашка ({text[:60]!r})")
    pg.click(f"{DLG} [data-schema-card-own] summary")
    links = pg.locator(f"{DLG} [data-schema-card-own-list] a").count()
    check(links == 3, f"{w}/{lang}: «anzeigen» — три ссылки на правку ({links})")
    small = small_targets(pg, KARTE)
    check(not small, f"{w}/{lang}: цели «Karte» не ниже 44 px ({small[:4]})")
    sw = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    check(sw, f"{w}/{lang}: без горизонтальной прокрутки")
    pg.screenshot(path=f"{OUT}/m34_grid_{w}_{lang}.png")
    # плитка применяется сама, затем «zurücksetzen»
    pg.click(f"{FORM} label:has(input[value=deal])")
    pg.wait_for_selector(f"{DLG} [data-schema-card-reset]", timeout=15000)
    busy_done(pg)
    check(checked(pg) == "deal", f"{w}/{lang}: «Deal» применилась сама")
    pg.screenshot(path=f"{OUT}/m34_grid_own_{w}_{lang}.png")
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-schema-card-reset]")
    settle(pg)
    check(
        checked(pg) == "" and not pg.locator(f"{DLG} [data-schema-card-reset]").count(),
        f"{w}/{lang}: «zurücksetzen» — снова «как в Design»",
    )
    win = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel);
        return !!(d && d.open && d.querySelector('[data-window-tab=karte]:not([hidden])')) }""",
        DLG,
    )
    check(win, f"{w}/{lang}: после сброса окно открыто на «Karte»")
    # «Abbrechen» возвращает форму на момент открытия
    open_karte(pg, "m34g")
    pg.click(f"{FORM} label:has(input[value=overlay])")
    busy_done(pg)
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-window-actions] button[value=revert]")
    open_karte(pg, "m34g")
    check(checked(pg) == "", f"{w}/{lang}: «Abbrechen» вернул форму ({checked(pg)!r})")


def others(pg, w, lang):
    t = TEXT[lang]
    open_karte(pg, "m34s")
    check(
        pg.locator(KARTE).is_visible() and radios(pg, "row") == ["compact", "deal"],
        f"{w}/{lang}: лента — вкладка с плитками и строками",
    )
    pg.screenshot(path=f"{OUT}/m34_slider_{w}_{lang}.png")
    open_karte(pg, "m34p")
    check(
        pg.locator(f"{DLG} [data-window-tab=karte]").count() == 0
        and pg.locator(f"{DLG} input[name=f_card]").count() == 0,
        f"{w}/{lang}: у прайс-листа вкладки «Karte» нет",
    )
    open_karte(pg, "m34a")
    tiles = radios(pg, "tile")
    check("coupon" in tiles and "ring" in tiles, f"{w}/{lang}: формы акций ({tiles})")
    text = pg.locator(f"{DLG} [data-schema-card-own]").inner_text()
    check(t["own1"] in text, f"{w}/{lang}: плашка акций ({text[:50]!r})")
    link = pg.locator(f"{DLG} [data-schema-card-inherit-link]").get_attribute("href")
    check("#dd-promo_card_form" in (link or ""), f"{w}/{lang}: акции — Design акций")
    pg.screenshot(path=f"{OUT}/m34_promos_{w}_{lang}.png")
    open_karte(pg, "products")
    check(pg.locator(KARTE).is_visible(), f"{w}/{lang}: встроенный список — вкладка «Karte»")
    look = pg.locator(f"{DLG} [data-schema-listview] input[name=f_card]").count()
    check(look == 0, f"{w}/{lang}: в «Wie anordnen» карточки больше нет")


def nojs(b):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        url = U + "/dashboard/site/aufbau/?seite=home&block=m34g&tab=karte"
        pg.goto(url)
        scope = "#bw-form-card_pick"
        apply = pg.locator(f"{scope} button[value=update]")
        check(apply.is_visible(), f"{w}: без JS — «Übernehmen» во вкладке «Karte»")
        pg.click(f"{scope} label:has(input[value=lookbook])")
        with pg.expect_navigation():
            apply.click()
        pg.goto(url)
        now = checked(pg, scope)
        check(now == "lookbook", f"{w}: без JS — форма записана ({now})")
        pg.screenshot(path=f"{OUT}/m34_nojs_{w}.png")
        with pg.expect_navigation():
            pg.click("[data-schema-card-reset]")
        pg.goto(url)
        check(checked(pg, scope) == "", f"{w}: без JS — «zurücksetzen»")
        discard(pg)
        ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for lang in ("de", "ru"):
        for w, h in ((1440, 900), (390, 844)):
            print(f"— {w}px {lang}")
            ctx = b.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=1,
                locale=lang,
                extra_http_headers={"Accept-Language": lang},
            )
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            login(pg)
            discard(pg)
            products_grid(pg, w, lang)
            others(pg, w, lang)
            check(not errors, f"{w}/{lang}: без ошибок скриптов ({errors[:2]})")
            discard(pg)
            ctx.close()
    nojs(b)
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
