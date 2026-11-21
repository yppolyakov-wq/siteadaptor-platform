"""FB-33 M4: стенд «⚙ Студии открывает окно блока Seitenaufbau» (1440 и 390).

⚙ плашки над блоком канвы → окно этого блока; переход в канве на «Sortiment» и ⚙ (живой путь
канвы, «Aufbau ändern» — схема той же страницы); несохранённая правка → ⚙ спрашивает
confirm; «Fertig» окна → «Auf der Seite bearbeiten» — Студия на ту же страницу; без JS —
⚙ строки секции ведёт в «Seitenaufbau», окно — колонкой.

Запуск (как fb33_m3_window_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m4_studio_settings_stand.py <папка>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`.
"""

import os
import sys
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
ok, fail = 0, []
DLG = "dialog.ui-bwin"


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


def canvas(pg, path_part, timeout=30000):
    """Кадр канвы на странице `path_part`, уже инструментированный Студией."""
    pg.wait_for_function(
        """(p) => { const f = document.getElementById('home-prev-frame');
        try { return f && f.contentWindow.location.pathname.indexOf(p) === 0
          && f.contentDocument.readyState === 'complete'
          && f.contentDocument.querySelector('[data-sf-section]')
          && f.contentDocument.querySelector('[data-sf-section]').style.cursor === 'pointer'; }
        catch (e) { return false; } }""",
        arg=path_part,
        timeout=timeout,
    )
    return pg.frame_locator("#home-prev-frame")


def pick(pg, keys_ok):
    """Ключ секции канвы, у которой есть строка Студии (`keys_ok` — фильтр JS)."""
    return pg.evaluate(
        """(f) => { const doc = document.getElementById('home-prev-frame').contentDocument;
        const keys = [...doc.querySelectorAll('[data-sf-section]')].map(e => e.getAttribute('data-sf-section'))
          .filter(k => k !== 'header' && k !== 'footer');
        return keys.find(k => eval(f)(k)) || ''; }""",
        keys_ok,
    )


def bar_gear(pg, key):
    """Клик по блоку канвы → плашка действий → ⚙."""
    pg.evaluate(
        """(k) => { const doc = document.getElementById('home-prev-frame').contentDocument;
        const el = doc.querySelector('[data-sf-section="' + k + '"]');
        el.dispatchEvent(new MouseEvent('click', {bubbles: true})); }""",
        key,
    )
    pg.wait_for_selector("#bld-action-bar.bld-ab-on [data-ab=settings]", state="visible")
    pg.click("#bld-action-bar [data-ab=settings]")


def run(b, w, h):
    print(f"— {w}px")
    ctx = b.new_context(viewport={"width": w, "height": h}, locale="de-DE")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    login(pg)

    # 1. ⚙ на главной → окно этого блока
    pg.goto(U + "/dashboard/site/home/")
    canvas(pg, "/")
    key = pick(pg, "k => !!document.querySelector('.blk-edit.flex-1[data-key=\"' + k + '\"]')")
    check(bool(key), f"на канве главной есть блок со строкой Студии ({key})")
    href = pg.get_attribute("[data-stu-aufbau]", "href") or ""
    check(unquote(query(href).get("page", "")) == "/", f"«Aufbau ändern» — главная ({href})")
    with pg.expect_navigation(url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u):
        bar_gear(pg, key)
    q = query(pg.url)
    check(q.get("seite") == "home" and q.get("block") == key, f"⚙ → окно блока {key} ({pg.url})")
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    check(pg.locator(f"{DLG}[open]").count() == 1, "окно блока открыто (dialog)")
    pg.screenshot(path=f"{OUT}/m4_home_window_{w}.png")

    # 2. «Fertig» → «Auf der Seite bearbeiten» → Студия на той же странице
    done = pg.locator(f"{DLG} [data-schema-done]").first
    done.click()
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()
    studio = pg.locator("a:has-text('Auf der Seite bearbeiten')").first.get_attribute("href") or ""
    check(unquote(query(studio).get("page", "")) == "/", f"«Studio» — та же страница ({studio})")
    pg.goto(U + studio if studio.startswith("/") else studio)
    canvas(pg, "/")

    # 3. переход в канве на «Sortiment» — ⚙ и «Aufbau ändern» по живому пути
    pg.evaluate(
        "document.getElementById('home-prev-frame').contentWindow.location.href = '/sortiment/?preview=1'"
    )
    canvas(pg, "/sortiment/")
    pg.wait_for_function(
        """() => (document.querySelector('[data-stu-aufbau]').getAttribute('href') || '')
          .indexOf('sortiment') >= 0""",
        timeout=10000,
    )
    href = pg.get_attribute("[data-stu-aufbau]", "href") or ""
    check(
        unquote(query(href).get("page", "")) == "/sortiment/",
        f"«Aufbau ändern» после перехода в канве — «Sortiment» ({href})",
    )
    key2 = pick(pg, "k => true")
    with pg.expect_navigation(url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u):
        bar_gear(pg, key2)
    q = query(pg.url)
    check(q.get("seite") == "catalog", f"⚙ на «Sortiment» ({key2}) → схема каталога ({pg.url})")
    check(
        "block" in q or pg.locator("text=Diesen Block finden Sie im Seitenaufbau nicht.").count(),
        "открыт блок — или подсказка, что его тут нет",
    )
    pg.screenshot(path=f"{OUT}/m4_catalog_{w}.png")

    # 4. несохранённая правка → ⚙ спрашивает
    pg.goto(U + "/dashboard/site/home/")
    canvas(pg, "/")
    pg.evaluate(
        """() => { const f = document.getElementById('home-form');
        const i = f.querySelector('input[type=text]:not([type=hidden])');
        i.value = i.value + ' '; i.dispatchEvent(new Event('input', {bubbles: true})); }"""
    )
    pg.wait_for_function("!document.getElementById('bld-save-dot').hidden")
    asked = []

    def dismiss(d):
        asked.append(d.message)
        d.dismiss()

    pg.once("dialog", dismiss)
    bar_gear(pg, key)
    pg.wait_for_timeout(500)
    check(
        asked == ["Ungespeicherte Änderungen gehen verloren."] and "/site/home/" in pg.url,
        f"правка → ⚙ спрашивает; «Abbrechen» — остаёмся в Студии ({asked})",
    )
    pg.once("dialog", lambda d: d.accept())
    with pg.expect_navigation(url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u):
        pg.click("#bld-action-bar [data-ab=settings]")
    check(query(pg.url).get("block") == key, "«OK» — окно блока")
    check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
    ctx.close()


def nojs(b):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg)
        pg.goto(U + "/dashboard/site/home/")
        gear = pg.locator("a[data-stu-gear]").first
        key = gear.get_attribute("data-key")
        href = gear.get_attribute("href") or ""
        check(
            "/dashboard/site/aufbau/oeffnen/" in href,
            f"{w}: без JS ⚙ строки — ссылка на окно ({href})",
        )
        pg.goto(U + href)
        q = query(pg.url)
        check(
            q.get("seite") == "home"
            and q.get("block") == key
            and pg.locator(f"{DLG}").count() == 0
            and pg.locator("[data-site-schema] aside#schema-panel").count() == 1,
            f"{w}: без JS — окно блока {key} колонкой ({pg.url})",
        )
        pg.screenshot(path=f"{OUT}/m4_nojs_{w}.png")
        ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for width, height in ((1440, 900), (390, 844)):
        run(browser, width, height)
    print("— без JS")
    nojs(browser)
    browser.close()
print(f"\n{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
