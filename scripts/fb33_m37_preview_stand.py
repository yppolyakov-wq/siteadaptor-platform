"""FB-33 M3-7: стенд «Vorschau» в окне блока «Seitenaufbau» (1440 и 390, с JS и без).

Кадр черновика страницы в окне: виден на компьютере, блок в зоне видимости кадра; правка текста
за ≤ 2 с видна в кадре; на телефоне область свёрнута (aria-expanded=false, кадра нет), раскрытие
строит кадр; Esc/«Fertig» убирает кадр; кадр без скриптов и форм (sandbox); Tab по кадру не
ходит; без JS кадра нет, ссылка «Vorschau» в шапке осталась; деталь товара: «Ähnliche» и
«Kaufen» — якорь или начало страницы.

Запуск (как fb33_m3_window_stand.py; тенант ptx, owner@ptx.test, у ptx нужен хотя бы один товар):
    python manage.py runserver 0.0.0.0:8037 --settings=config.settings.stand
    STAND_URL=http://ptx.siteadaptor.de:8037 \\
        uv run --no-project --with playwright python scripts/fb33_m37_preview_stand.py <папка>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")
REF = os.environ.get("STAND_REF", "m3d1")  # текстовый блок главной ptx
DLG = "dialog.ui-bwin"
PV = f"{DLG} [data-bwin-preview]"
FRAME = f"{PV} iframe"
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def login(ctx):
    pg = ctx.new_page()
    pg.goto(U + "/accounts/login/")
    pg.fill("input[name=login]", "owner@ptx.test")
    pg.fill("input[name=password]", "Stand-Passwort-123")
    pg.click("button[type=submit]")
    pg.wait_for_load_state()
    return pg


def frame_state(pg):
    """Где блок в кадре: видим ли, текст кадра, пометка «не видно»."""
    return pg.evaluate(
        """([sel, ref]) => { const f = document.querySelector(sel); if (!f) return null;
        const d = f.contentDocument; if (!d || !d.body) return {loaded: false};
        const v = f.contentWindow, el = [...d.querySelectorAll('[data-sf-section="' + ref + '"]')]
          .map(e => e.getClientRects().length ? e : [...e.querySelectorAll('*')].find(c => c.getClientRects().length))
          .find(Boolean);
        const r = el ? el.getBoundingClientRect() : null;
        const note = document.querySelector('.ui-bwin-pv-missing');
        return {loaded: d.readyState === 'complete', y: v.scrollY, ih: v.innerHeight,
          top: r && r.top, bottom: r && r.bottom, text: d.body.innerText,
          missing: !!note && !note.hidden, title: f.title, tab: f.tabIndex,
          sandbox: f.getAttribute('sandbox'), src: f.getAttribute('src'),
          scripts: d.defaultView.__m37probe === undefined,
          forms: [...d.forms].length} }""",
        [FRAME, REF],
    )


def wait_frame(pg, what="complete"):
    pg.wait_for_function(
        """(sel) => { const f = document.querySelector(sel);
        return f && f.contentDocument && f.contentDocument.readyState === 'complete'
          && f.contentDocument.body && f.contentDocument.body.childElementCount > 0; }""",
        arg=FRAME,
        timeout=15000,
    )
    pg.wait_for_timeout(150)  # прокрутка к блоку — в обработчике load


def busy_done(pg):
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def desktop(pg, w):
    url = U + f"/dashboard/site/aufbau/?seite=home&block={REF}&tab=texte"
    pg.goto(url)
    pg.evaluate("() => { try { sessionStorage.clear(); } catch (e) {} }")
    pg.goto(url)
    pg.wait_for_selector(PV, timeout=10000)
    btn = pg.locator(f"{PV} button[aria-controls]")
    check(btn.get_attribute("aria-expanded") == "true", "1440: «Vorschau» раскрыта по умолчанию")
    h = btn.bounding_box()["height"]
    check(h >= 44, f"кнопка «Vorschau» не ниже 44 px ({h})")
    wait_frame(pg)
    st = frame_state(pg)
    check(
        st["top"] is not None and -2 <= st["top"] < st["ih"],
        f"блок в зоне видимости кадра (top {st['top']}, высота {st['ih']}, scrollY {st['y']})",
    )
    check(not st["missing"], "пометки «не видно» нет")
    check(
        st["sandbox"] == "allow-same-origin" and st["tab"] == -1 and st["title"],
        f"sandbox без скриптов, tabindex=-1, title ({st['sandbox']}, {st['tab']}, {st['title']!r})",
    )
    check("preview=1" in st["src"] and "aufbau=home" in st["src"], f"адрес черновика ({st['src']})")
    geo = pg.evaluate(
        """(sel) => { const f = document.querySelector(sel), s = f.parentElement.getBoundingClientRect(),
        d = document.querySelector('dialog.ui-bwin').getBoundingClientRect();
        return {fw: f.offsetWidth, tr: getComputedStyle(f).transform, sw: s.width, sh: s.height,
          inside: s.bottom <= d.bottom + 1 && s.left >= d.left, dh: d.height, ih: innerHeight}; }""",
        FRAME,
    )
    check(
        geo["fw"] == 1280 and geo["tr"].startswith("matrix(") and geo["inside"],
        f"страница 1280 уменьшена, область внутри окна ({geo})",
    )
    # скрипты кадра не выполняются: инлайн-скрипт витрины ставит класс js-reveal — его нет
    js = pg.evaluate(
        "(sel) => document.querySelector(sel).contentDocument.documentElement.className", FRAME
    )
    check("js-reveal" not in js, f"скрипты витрины в кадре не выполняются ({js[:40]!r})")
    pg.screenshot(path=f"{OUT}/m37_open_{w}.png")
    # прокрутка колесом
    box = pg.locator(FRAME).bounding_box()
    y0 = frame_state(pg)["y"]
    pg.mouse.move(box["x"] + 100, box["y"] + 60)
    pg.mouse.wheel(0, -300)
    pg.wait_for_timeout(300)
    check(
        frame_state(pg)["y"] != y0 or y0 == 0,
        f"кадр крутится колесом ({y0} → {frame_state(pg)['y']})",
    )
    # Tab: по кадру не ходит, из окна не выходит
    pg.focus(f"{PV} button[aria-controls]")
    seen = []
    for _ in range(40):
        pg.keyboard.press("Tab")
        seen.append(
            pg.evaluate(
                "() => { const a = document.activeElement; return [a.tagName, "
                "!!a.closest('dialog.ui-bwin')]; }"
            )
        )
    # BODY — фокус ушёл в оболочку браузера после последней цели модального окна (так ведёт
    # себя сам <dialog> в Chromium) и вернулся в окно; IFRAME — фокус в кадре (так нельзя)
    check(
        all(inside or t == "BODY" for t, inside in seen)
        and not any(t == "IFRAME" for t, _i in seen)
        and sum(inside for _t, inside in seen) > 30,
        f"Tab не заходит в кадр и не уходит из окна ({seen[:3]})",
    )
    # правка текста → кадр показывает новый текст за ≤ 2 с
    new = f"Vorschau neu {int(time.time()) % 10000}"
    pg.fill("[data-schema-fields] input[name=f_title]", new)
    t0 = time.time()
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    busy_done(pg)
    try:
        pg.wait_for_function(
            """([sel, txt]) => { const f = document.querySelector(sel);
            return f && f.contentDocument && f.contentDocument.body
              && f.contentDocument.body.innerText.includes(txt); }""",
            arg=[FRAME, new],
            timeout=6000,
        )
        took = time.time() - t0
    except Exception:  # noqa: BLE001
        took = 99
    check(took <= 2.0, f"правка видна в кадре за ≤ 2 с ({took:.2f} с)")
    wait_frame(pg)
    st = frame_state(pg)
    check(
        st["top"] is not None and -2 <= st["top"] < st["ih"],
        f"после перерисовки кадр снова у блока (top {st['top']})",
    )
    pg.screenshot(path=f"{OUT}/m37_edited_{w}.png")
    # свернуть → помнится на вкладку
    btn.click()
    check(
        btn.get_attribute("aria-expanded") == "false"
        and not pg.locator(f"{PV} #bw-preview-area").is_visible(),
        "свернуть: aria-expanded=false, область скрыта",
    )
    pg.reload()
    pg.wait_for_selector(PV)
    check(
        pg.locator(f"{PV} button[aria-controls]").get_attribute("aria-expanded") == "false",
        "свёрнутость помнится после F5",
    )
    pg.locator(f"{PV} button[aria-controls]").click()
    wait_frame(pg)
    # Esc закрывает окно — кадра нет
    pg.keyboard.press("Escape")
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()
    check(pg.locator("iframe.ui-bwin-pv-frame").count() == 0, "Esc: окно и кадр ушли")
    # разделы детали товара: «Ähnliche» (якоря на витрине нет → пометка), «Kaufen» (обёртка)
    for ref, missing in (("related", True), ("__kauf", False)):
        pg.goto(U + f"/dashboard/site/aufbau/?seite=product&block={ref}")
        pg.wait_for_selector(PV)
        wait_frame(pg)
        st = frame_state(pg)
        check(
            st["missing"] == missing,
            f"товар «{ref}»: пометка «не видно» {'есть' if missing else 'нет'} ({st['missing']})",
        )
        pg.screenshot(path=f"{OUT}/m37_product_{ref.strip('_')}_{w}.png")


def phone(pg, w):
    url = U + f"/dashboard/site/aufbau/?seite=home&block={REF}&tab=texte"
    pg.goto(url)
    pg.wait_for_selector(PV, timeout=10000)
    btn = pg.locator(f"{PV} button[aria-controls]")
    check(btn.get_attribute("aria-expanded") == "false", "390: «Vorschau» свёрнута")
    check(pg.locator(FRAME).count() == 0, "390: кадра нет, пока не раскрыли")
    sw = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    check(sw, "390: без горизонтальной прокрутки")
    pg.screenshot(path=f"{OUT}/m37_closed_{w}.png")
    btn.scroll_into_view_if_needed()
    btn.click()
    wait_frame(pg)
    check(btn.get_attribute("aria-expanded") == "true", "390: раскрытие → aria-expanded=true")
    geo = pg.evaluate(
        """(sel) => { const f = document.querySelector(sel);
        return {fw: f.offsetWidth, sw: f.parentElement.clientWidth, tr: getComputedStyle(f).transform}; }""",
        FRAME,
    )
    check(
        geo["fw"] == geo["sw"] and geo["tr"] == "none",
        f"390: страница шириной окна, без масштаба ({geo})",
    )
    st = frame_state(pg)
    head = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel).contentDocument,
        h = d.querySelector('[data-sf-section="header"]'); return h ? h.getBoundingClientRect().bottom : 0; }""",
        FRAME,
    )
    check(
        st["top"] is not None and head - 1 <= st["top"] < st["ih"],
        f"390: блок в кадре виден под липкой шапкой (top {st['top']}, шапка до {head})",
    )
    pg.locator(FRAME).scroll_into_view_if_needed()
    pg.screenshot(path=f"{OUT}/m37_open_{w}.png")
    pg.reload()
    pg.wait_for_selector(PV)
    check(
        pg.locator(f"{PV} button[aria-controls]").get_attribute("aria-expanded") == "false",
        "390: после F5 снова свёрнута",
    )


def nojs(b):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = login(ctx)
        pg.goto(U + f"/dashboard/site/aufbau/?seite=home&block={REF}")
        html = pg.content()
        check(
            "<iframe" not in html.split("data-site-schema", 1)[-1].split("js/aufbau", 1)[0]
            and pg.locator("iframe").count() == 0,
            f"{w}: без JS кадра нет",
        )
        head = pg.locator("[data-schema-status] a[target=_blank]")
        check(
            head.count() == 1 and "preview=1" in (head.get_attribute("href") or ""),
            f"{w}: без JS ссылка «Vorschau» в шапке осталась",
        )
        pg.screenshot(path=f"{OUT}/m37_nojs_{w}.png")
        ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for w, h in ((1440, 900), (390, 844)):
        print(f"— {w}px")
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg = login(ctx)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))  # noqa: B023
        (desktop if w > 500 else phone)(pg, w)
        check(not errors, f"{w}: без ошибок скриптов ({errors[:2]})")
        ctx.close()
    nojs(b)
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
