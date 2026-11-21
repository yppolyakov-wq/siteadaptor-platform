"""FB-33 M4b: стенд «из старой панели Студии сняты группы, дублирующие окно блока» (1440/390, de/ru).

Имя секции «Produkte» открывает панель: в ней нет «N in einer Reihe», «Höchstens», «Display
style», «Width», осей «ЧТО»; есть группа «Feinschliff» и ссылка «Fenster öffnen» (tab=wie).
«Raster ▾» на плашке блока канвы ведёт в окно на «Wie anordnen», «Breite ▾» нет. Правка
колонок в окне → «Speichern» схемы → правка текста и «Speichern» Студии → колонки целы.
Без JS: строка секции несёт ссылку в окно, переход открывает окно колонкой.

Запуск (как fb33_m4_studio_settings_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m4b_studio_dupes_stand.py <папка>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`.
"""

import os
import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
KEY = "products"
ok, fail = 0, []
DLG = "dialog.ui-bwin"
REMOVED = ("layout_preset_", "limit_", "style_", "width_", "grid_rows_", "scroll_", "cols_")
LINK = {"de": "Fenster öffnen", "ru": "Открыть окно"}
FINE = {"de": "Feinschliff", "ru": "Тонкая настройка"}


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


def query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def canvas(pg, timeout=30000):
    pg.wait_for_function(
        """() => { const f = document.getElementById('home-prev-frame');
        try { const el = f && f.contentDocument.querySelector('[data-sf-section]');
          return f.contentDocument.readyState === 'complete' && el && el.style.cursor === 'pointer'; }
        catch (e) { return false; } }""",
        timeout=timeout,
    )


def select_block(pg, key):
    pg.evaluate(
        """(k) => { const doc = document.getElementById('home-prev-frame').contentDocument;
        doc.querySelector('[data-sf-section="' + k + '"]')
          .dispatchEvent(new MouseEvent('click', {bubbles: true})); }""",
        key,
    )
    pg.wait_for_selector("#bld-action-bar.bld-ab-on", state="visible")


def window_cols(pg):
    pg.goto(U + f"/dashboard/site/aufbau/?seite=home&block={KEY}&tab=wie")
    return pg.evaluate(
        "() => (document.querySelector('input[name=f_cols]:checked') || {}).value || ''"
    )


def run(b, w, h, lang):
    print(f"— {w}px {lang}")
    ctx = b.new_context(viewport={"width": w, "height": h}, locale=f"{lang}-DE")
    ctx.add_cookies([{"name": "django_language", "value": lang, "url": U}])
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    login(pg)

    # 1. имя секции → панель: содержимое и «Feinschliff», снятого нет, ссылка в окно
    pg.goto(U + "/dashboard/site/home/")
    canvas(pg)
    pg.evaluate(
        "(k) => document.querySelector('.blk-edit.flex-1[data-key=\"' + k + '\"]').click()", KEY
    )
    pg.wait_for_selector("#bld-block-popup:not(.hidden)", timeout=10000)
    names = pg.evaluate(
        """() => [...document.querySelectorAll('#bld-block-popup [name]')].map(e => e.name)"""
    )
    check(names, f"панель «{KEY}» открыта ({len(names)} полей)")
    bad = [n for n in names if n.startswith(REMOVED) or n.startswith("sl_")]
    check(not bad, f"в панели нет снятых полей ({bad[:4]})")
    check(
        f"tail_{KEY}" in names and f"font_{KEY}" in names, "«Feinschliff» на месте (хвост, шрифт)"
    )
    link = pg.locator("#bld-block-popup a[data-stu-window]")
    check(link.count() == 1 and link.inner_text().strip() == LINK[lang], "ссылка «Fenster öffnen»")
    href = link.get_attribute("href") or ""
    check("tab=wie" in href and f"block={KEY}" in href, f"ссылка — окно, «Wie anordnen» ({href})")
    check(
        pg.locator("#bld-block-popup summary", has_text=FINE[lang]).count() >= 1,
        f"группа «{FINE[lang]}»",
    )
    pg.screenshot(path=f"{OUT}/m4b_panel_{w}_{lang}.png")

    # 2. плашка: «Raster ▾» → окно на «Wie anordnen», «Breite ▾» нет
    pg.goto(U + "/dashboard/site/home/")
    canvas(pg)
    select_block(pg, KEY)
    check(pg.locator("#bld-action-bar [data-quick=width]").count() == 0, "«Breite ▾» снята")
    raster = pg.locator("#bld-action-bar [data-quick=layout]")
    check(
        raster.is_visible() and raster.get_attribute("data-quick-window") is not None,
        "«Raster ▾» видна и ведёт в окно",
    )
    pg.screenshot(path=f"{OUT}/m4b_bar_{w}_{lang}.png")
    with pg.expect_navigation(url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u):
        raster.click()
    q = query(pg.url)
    check(q.get("block") == KEY and q.get("tab") == "wie", f"окно {KEY}, вкладка wie ({pg.url})")
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    pg.wait_for_function("!document.getAnimations().length")
    pg.screenshot(path=f"{OUT}/m4b_window_{w}_{lang}.png")
    check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
    ctx.close()


def survives(b):
    """Правка в окне → «Speichern» схемы → «Speichern» Студии: колонки целы (W0)."""
    print("— окно → Студия")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE")
    pg = ctx.new_page()
    login(pg)
    before = window_cols(pg)
    want = "3" if before != "3" else "2"
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    pg.locator(f"{DLG} label:has(input[name=f_cols][value='{want}'])").first.click()
    pg.wait_for_function(
        "(v) => (document.querySelector('input[name=f_cols]:checked') || {}).value === v",
        arg=want,
        timeout=15000,
    )
    pg.wait_for_timeout(800)  # переключатель уходит через 350 мс (aufbau.js, FB-29 R4)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )
    pg.goto(U + "/dashboard/site/aufbau/?seite=home")
    save = pg.locator("button[name=op][value=save]")
    check(save.count() >= 1, "черновик схемы — «Speichern»")
    save.first.click()
    pg.wait_for_load_state()
    check(window_cols(pg) == want, f"окно записало колонки {want} (было {before})")
    pg.goto(U + "/dashboard/site/home/")
    canvas(pg)
    pg.evaluate(
        """() => { const i = document.querySelector('#home-form input[name=hero_title]');
        i.value = i.value + ' '; i.dispatchEvent(new Event('input', {bubbles: true})); }"""
    )
    with pg.expect_navigation():
        pg.click("button[type=submit][form=home-form]")
    check(window_cols(pg) == want, f"«Speichern» Студии колонки окна не стёр ({want})")
    ctx.close()


def nojs(b):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        pg.goto(U + "/dashboard/site/home/")
        link = pg.locator(f"a[data-stu-window][href*='block={KEY}']").first
        href = link.get_attribute("href") or ""
        check("tab=wie" in href, f"{w}: без JS — ссылка в окно у строки ({href})")
        pg.goto(U + href)
        q = query(pg.url)
        check(
            q.get("block") == KEY
            and pg.locator("[data-site-schema] aside#schema-panel").count() == 1,
            f"{w}: без JS — окно {KEY} колонкой ({pg.url})",
        )
        pg.screenshot(path=f"{OUT}/m4b_nojs_{w}.png")
        ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for width, height in ((1440, 900), (390, 844)):
        for language in ("de", "ru"):
            run(browser, width, height, language)
    survives(browser)
    print("— без JS")
    nojs(browser)
    browser.close()
print(f"\n{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
