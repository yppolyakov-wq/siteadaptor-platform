"""FB-33 M3-3abc: стенд вкладки «Wie anordnen» окна блока (1440 и 390): виды картинками
(клавиши, авто-применение переключателя, Esc раньше 350 мс), смена вида плитками, «Platz»
(ширина, «Reihe»), как выглядит список и «zurücksetzen», без JS.

Запуск (как fb33_m3_window_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_3_stand.py <папка для скриншотов>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Правки стенд оставляет
только в черновике и в конце его отбрасывает.
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import sys

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
ok, fail = 0, []
DLG = "dialog.ui-bwin"
TILES = f"{DLG} [data-schema-view-tiles=style]"


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


def closed(pg):
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()


def login(pg):
    pg.goto(U + "/accounts/login/")
    pg.fill("input[name=login]", "owner@ptx.test")
    pg.fill("input[name=password]", "Stand-Passwort-123")
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def post(pg, **fields):
    """Действие экрана обычной отправкой формы (как кнопка), с переходом."""
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


def checked(pg):
    return pg.locator(f"{TILES} input:checked").get_attribute("value")


def views(pg, w):
    """M3-3a: вид секции Team картинками — стрелки, авто-применение, Esc раньше 350 мс."""
    url = U + "/dashboard/site/aufbau/?seite=home&block=team&tab=wie"
    pg.goto(url)
    settle(pg)
    values = pg.locator(f"{TILES} input[type=radio]").evaluate_all("l => l.map(i => i.value)")
    check(
        values == ["", "circles", "list", "compact", "duo"], f"{w}: виды Team плитками ({values})"
    )
    legend = pg.locator(f"{TILES} legend").inner_text().strip()
    check(legend in ("Darstellung", "Appearance"), f"легенда группы ({legend})")
    thumbs = pg.locator(f"{TILES} [data-style-thumb]").evaluate_all(
        "l => l.map(e => e.getAttribute('data-style-thumb'))"
    )
    check(len(set(thumbs)) == len(values), f"{w}: у каждого вида своя схема ({thumbs})")
    check(
        not pg.locator(f"{DLG} [data-schema-fields] button[value=update]").is_visible(),
        "«Übernehmen» скрыта скриптом (переключатель применяется сам)",
    )
    start = checked(pg)
    i = values.index(start)
    pg.focus(f"{TILES} input:checked")
    pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(500)
    busy_done(pg)
    now = checked(pg)
    check(now == values[(i + 1) % len(values)], f"{w}: → применилось само ({start!r} → {now!r})")
    focus = pg.evaluate("document.activeElement && document.activeElement.name")
    check(focus == "f_style", f"{w}: фокус остался в группе видов ({focus})")
    small = small_targets(pg, f"{DLG} [data-window-tab=wie]")
    check(not small, f"{w}: цели «Wie anordnen» не ниже 44 px ({small[:4]})")
    pg.screenshot(path=f"{OUT}/m33a_team_{w}.png")
    pg.reload()
    settle(pg)
    check(checked(pg) == now, f"{w}: вид в черновике после F5 ({checked(pg)!r})")
    # правило M3-2: Esc раньше, чем переключатель применится (350 мс) — выбор не теряется
    pg.focus(f"{TILES} input:checked")
    pg.keyboard.press("ArrowRight")
    pg.keyboard.press("Escape")
    closed(pg)
    pg.goto(url)
    settle(pg)
    want = values[(i + 2) % len(values)]
    check(checked(pg) == want, f"{w}: Esc через <350 мс — выбор записан ({checked(pg)!r})")
    # ссылочный блок: «Standard», не «как на главной»
    pg.goto(U + "/dashboard/site/aufbau/?seite=home&block=gallery&tab=wie")
    settle(pg)
    gal = pg.locator(f"{TILES} label").first.inner_text()
    check("Standard" in gal, f"{w}: Galerie — первый вид «Standard» ({gal!r})")
    pg.screenshot(path=f"{OUT}/m33a_gallery_{w}.png")


def add_text(pg, w):
    pg.goto(U + "/dashboard/site/aufbau/?seite=text")
    if w <= 500:
        done = pg.locator("[data-schema-done]")
        if done.count() and done.first.is_visible():
            done.first.click()
            pg.wait_for_load_state()
    pg.click("[data-schema-add] summary")
    pg.select_option("select[name=type]", "text")
    pg.click("form:has(select[name=type]) button")
    pg.wait_for_load_state()
    return pg.url.split("block=")[1].split("&")[0].split("#")[0]


def switch_and_platz(pg, w):
    """M3-3a смена вида плитками · M3-3b «Platz»."""
    ref = add_text(pg, w)
    url = U + f"/dashboard/site/aufbau/?seite=text&block={ref}&tab=wie"
    pg.goto(url)
    settle(pg)
    sw = f"{DLG} [data-schema-switch]"
    names = pg.locator(f"{sw} button").evaluate_all("l => l.map(b => b.value)")
    # стопка FB-33: третья плитка «Von einer Seite» (M3-3d) и плашка «Beide Fassungen…»
    check(names == ["text", "image_text", "textpage"], f"{w}: смена вида — плитки ({names})")
    both = pg.locator(f"{DLG} [data-schema-keeps-both]")
    check(both.count() == 1 and both.first.is_visible(), f"{w}: плашка «Beide Fassungen…»")
    labels = pg.locator(f"{sw} button .font-semibold").all_inner_texts()
    check(
        labels
        in (["Text", "Foto + Text", "Von einer Seite"], ["Text", "Photo + text", "From a page"]),
        f"{w}: подписи «Text», «Foto + Text», «Von einer Seite» ({labels})",
    )
    big = pg.locator(f"{DLG} [data-schema-width] fieldset > div").first.locator("button")
    check(big.count() == 4, f"{w}: четыре крупные плитки ширины ({big.count()})")
    legend = pg.locator(f"{DLG} [data-schema-width] legend").inner_text().strip()
    check(
        legend in ("Breite auf dem Computer", "Width on a computer"),
        f"легенда «Breite auf dem Computer» ({legend})",
    )
    check(pg.locator(f"{DLG} [data-schema-reihe]").count() == 0, f"{w}: «Reihe» только у узкого")
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-schema-width-tile=w13]")
    settle(pg)
    check(
        pg.locator(f"{DLG} [data-schema-width-tile=w13]").get_attribute("aria-pressed") == "true",
        f"{w}: ширина 1/3 выбрана",
    )
    reihe = f"{DLG} [data-schema-reihe]"
    check(pg.locator(reihe).is_visible(), f"{w}: у узкого блока — «Reihe»")
    with pg.expect_navigation():
        pg.click(f"{reihe} [data-schema-reihe-op=newline]")
    settle(pg)
    now = pg.locator(f"{reihe} [data-schema-reihe-op=newline]").get_attribute("aria-pressed")
    check(now == "true", f"{w}: «In einer neuen Reihe» нажата ({now})")
    before = pg.url
    pg.click(f"{reihe} [data-schema-reihe-op=newline]")  # нажатая — без действия
    pg.wait_for_timeout(300)
    check(pg.url == before, f"{w}: нажатая кнопка «Reihe» ничего не отправляет")
    with pg.expect_navigation():
        pg.click(f"{reihe} [data-schema-reihe-op=beside]")
    settle(pg)
    back = pg.locator(f"{reihe} [data-schema-reihe-op=beside]").get_attribute("aria-pressed")
    check(back == "true", f"{w}: снова «Neben dem vorigen Block»")
    small = small_targets(pg, f"{DLG} [data-window-tab=wie]")
    check(not small, f"{w}: цели «Platz» не ниже 44 px ({small[:4]})")
    sw_px = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    check(sw_px, f"{w}: без горизонтальной прокрутки")
    pg.locator(f"{DLG} [data-schema-platz]").scroll_into_view_if_needed()
    pg.screenshot(path=f"{OUT}/m33b_platz_{w}.png")
    # смена вида — последней (у «Foto + Text» свои ширины)
    with pg.expect_navigation():
        pg.click(f"{sw} button[value=image_text]")
    settle(pg)
    pressed = pg.locator(f"{sw} button[aria-pressed=true]").get_attribute("value")
    check(pressed == "image_text", f"{w}: вид сменён на «Foto + Text» ({pressed})")


def list_look(pg, w):
    """M3-3c: как выглядит список — своя форма, строка наследования, «zurücksetzen»."""
    url = U + "/dashboard/site/aufbau/?seite=home&block=products&tab=wie"
    pg.goto(url)
    settle(pg)
    look = f"{DLG} [data-schema-listview]"
    check(pg.locator(look).is_visible(), f"{w}: «Wie … aussehen» во вкладке «Wie anordnen»")
    check(
        pg.locator(f"{DLG} [data-window-tab=was] [name=f_cols]").count() == 0,
        f"{w}: колонок больше нет во вкладке «Was»",
    )
    off = pg.locator(f"{look} [data-schema-style-off]").all_inner_texts()
    check(
        len(off) == 2
        and all(
            ("Vorerst nur auf Katalogseiten." in t or "only on catalogue pages" in t) for t in off
        ),
        f"{w}: Schaufenster/Magazin — недоступны с причиной ({len(off)})",
    )
    check(
        pg.locator(f"{DLG} [data-schema-view-reset]").count() == 0, "своего вида нет — сброса нет"
    )
    pg.click(f"{look} [data-schema-buttons=cols] label:has(input[value='2'])")
    pg.wait_for_selector(f"{DLG} [data-schema-view-reset]", timeout=15000)
    check(
        pg.locator(f"{DLG} [data-schema-view-reset]").is_visible(),
        f"{w}: «zurücksetzen» видна с JS",
    )
    busy_done(pg)
    line = pg.locator(f"{DLG} [data-schema-inherit]").inner_text()
    check(
        "Eigene Einstellung" in line or "Own setting" in line,
        f"{w}: своя раскладка — строка с «zurücksetzen» ({line!r})",
    )
    pg.screenshot(path=f"{OUT}/m33c_list_{w}.png")
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-schema-view-reset]")
    settle(pg)
    win = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel);
        return {open: !!(d && d.open), wie: !!(d && d.querySelector('[data-window-tab=wie]:not([hidden])')),
          focus: !!(d && d.contains(document.activeElement))} }""",
        DLG,
    )
    check(
        all(win.values()),
        f"{w}: после сброса окно снова открыто на «Wie anordnen», фокус в нём ({win})",
    )
    check(
        pg.locator(f"{DLG} [data-schema-inherit-row]").is_visible(),
        f"{w}: строка наследования видна",
    )
    cols = pg.locator(f"{look} [data-schema-buttons=cols] input:checked").get_attribute("value")
    check(
        pg.locator(f"{DLG} [data-schema-view-reset]").count() == 0 and cols == "4",
        f"{w}: «zurücksetzen» — снова стандарт ({cols})",
    )


def nojs(b):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        pg.goto(U + "/dashboard/site/aufbau/?seite=home&block=team&tab=wie")
        apply = pg.locator("[data-schema-fields] button[value=update]")
        check(
            pg.locator("[data-schema-view-tiles=style]").is_visible() and apply.is_visible(),
            f"{w}: без JS — плитки и «Übernehmen»",
        )
        pg.click("[data-schema-view-tiles=style] label:has(input[value=duo])")
        with pg.expect_navigation():
            apply.click()
        pg.goto(U + "/dashboard/site/aufbau/?seite=home&block=team&tab=wie")
        now = pg.locator("[data-schema-view-tiles=style] input:checked").get_attribute("value")
        check(now == "duo", f"{w}: без JS — вид записан ({now})")
        pg.screenshot(path=f"{OUT}/m33_nojs_{w}.png")
        discard(pg, "home")
        ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for w, h in ((1440, 900), (390, 844)):
        print(f"— {w}px")
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        login(pg)
        views(pg, w)
        switch_and_platz(pg, w)
        list_look(pg, w)
        check(not errors, f"{w}: без ошибок скриптов ({errors[:2]})")
        discard(pg, "home")
        discard(pg, "text")
        ctx.close()
    nojs(b)
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
