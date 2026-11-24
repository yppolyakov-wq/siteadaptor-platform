"""FB-33 стопка 14 E9: «Abbrechen» окна блока — к якорю строки, сообщение у строки.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 «E9», §5.3. Без JS: адрес несёт `abbruch` и
`#schema-row-<ref>`, строка в окне просмотра, абзац `#schema-cancel-msg` виден перед ней, живая
область пуста. С JS: фокус на ⚙ строки (у скрытой — на её ссылке в раскрытом «Ausgeblendet»),
в адресе нет ни якоря, ни `abbruch`, текст в живой области один раз; F5 молчит. Проход ru с JS —
с `prefers-reduced-motion: reduce`.

Запуск (демо-киты стенда владельца, тенант `shop`):

    DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 python manage.py runserver 0.0.0.0:8149 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:8149 \\
        uv run --no-project --with playwright python scripts/fb33_e9_cancel_stand.py <папка>
"""

import os
import sys

import standlib as sl

URL = os.environ.get("STAND_URL", "http://shop.siteadaptor.de:8149").rstrip("/")
EMAIL = os.environ.get("STAND_EMAIL", "shop@example.com")
PASSWORD = os.environ.get("STAND_PASSWORD", "demo-12345678")  # seed_demo_tenants.DEMO_PASSWORD
AUFBAU = URL + "/dashboard/site/aufbau/?seite=home"

IN_VIEW = """(sel) => { const e = document.querySelector(sel); if (!e) return null;
  const r = e.getBoundingClientRect();
  return {top: r.top, bottom: r.bottom, h: innerHeight}; }"""
ACTIVE = """() => { const a = document.activeElement; return a ? (a.getAttribute('data-schema-gear')
  || a.getAttribute('data-schema-block') || a.id || a.tagName) : null; }"""


def rows(pg):
    """Видимые строки с «⋯» (их можно скрыть), сверху вниз."""
    return pg.evaluate(
        "() => [...document.querySelectorAll('[data-schema-lines] [data-schema-gear]')]"
        ".map(a => a.getAttribute('data-schema-gear'))"
        ".filter(r => document.getElementById('schema-more-' + r))"
    )


def hide(pg, ref):
    pg.click(f"#schema-more-{ref}")
    with pg.expect_navigation():
        pg.click(f"details:has(> #schema-more-{ref}) button[value=toggle]")
    pg.wait_for_selector(f"[data-schema-hidden] #schema-row-{ref}", state="attached")


def cancel(pg, ref, js):
    pg.goto(AUFBAU + f"&block={ref}")
    if js:
        pg.wait_for_selector("[data-window-actions] button[value=revert]", state="visible")
    with pg.expect_navigation():
        pg.click("[data-window-actions] button[value=revert]")
    pg.wait_for_load_state("load")
    if js:
        pg.wait_for_timeout(800)  # задержанная озвучка ~300 мс


def run_case(rep, pg, tag, ref, js, hidden, out):
    cancel(pg, ref, js)
    sl.settle(pg, js, rep)
    url = pg.url
    msg = pg.locator("#schema-cancel-msg")
    rep.check(msg.count() == 1, f"{tag}: сообщение у строки ({msg.count()})", code="msg")
    kind = msg.get_attribute("data-schema-cancel") if msg.count() else None
    rep.check(kind == "same", f"{tag}: итог «нечего» без правок ({kind})", code="kind")
    text = " ".join(msg.inner_text().split()) if msg.count() else ""
    top_text = pg.locator("[data-schema-messages]").inner_text()
    rep.check(not text or text not in top_text, f"{tag}: вверху сообщения нет", code="top")
    order = pg.evaluate(
        """(ref) => { const m = document.getElementById('schema-cancel-msg');
        const a = document.getElementById('schema-row-' + ref); if (!m || !a) return null;
        return !!(m.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)
          && (a.getAttribute('aria-describedby') || '').includes('schema-cancel-msg'); }""",
        ref,
    )
    rep.check(
        order is True, f"{tag}: абзац перед строкой, aria-describedby ({order})", code="order"
    )
    if hidden:
        opened = pg.evaluate("() => !!document.querySelector('[data-schema-hidden][open]')")
        rep.check(opened, f"{tag}: «Ausgeblendet» раскрыт", code="details")
    row = pg.evaluate(IN_VIEW, f"#schema-row-{ref}")
    box = pg.evaluate(IN_VIEW, "#schema-cancel-msg")
    rep.check(
        row is not None and 0 <= row["top"] and row["bottom"] <= row["h"],
        f"{tag}: строка в окне просмотра ({row})",
        code="row-view",
    )
    rep.check(
        box is not None and 0 <= box["top"] and box["bottom"] <= box["h"],
        f"{tag}: сообщение в окне просмотра ({box})",
        code="msg-view",
    )
    live = pg.locator("[data-schema-live]").text_content() or ""
    if js:
        rep.check(pg.evaluate(ACTIVE) == ref, f"{tag}: фокус на строке ({pg.evaluate(ACTIVE)})")
        rep.check(
            "#" not in url and "abbruch" not in url, f"{tag}: адрес без якоря и abbruch ({url})"
        )
        rep.check(" ".join(live.split()) == text, f"{tag}: живая область — текст ({live!r})")
        pg.reload()
        pg.wait_for_load_state("load")
        pg.wait_for_timeout(800)
        live2 = pg.locator("[data-schema-live]").text_content() or ""
        rep.check(
            not live2 and pg.locator("#schema-cancel-msg").count() == 0,
            f"{tag}: F5 молчит ({live2!r})",
            code="f5",
        )
    else:
        rep.check(
            "abbruch=same" in url and url.endswith(f"#schema-row-{ref}"),
            f"{tag}: адрес — abbruch и якорь строки ({url[-60:]})",
        )
        rep.check(not live.strip(), f"{tag}: живая область пуста ({live!r})", code="live")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
    # схема (строки и «Ausgeblendet») — область среза; сайдбар кабинета без JS даёт прежние
    # цели < 44 px (до E9 так же, не предмет среза)
    sl.a11y_check(rep, pg, tag, scope="[data-schema-blocks]", minimum=44)
    if hidden:
        sl.a11y_check(rep, pg, tag + " hidden-list", scope="[data-schema-hidden]", minimum=44)
    sl.shot(pg, out, tag.replace(" ", "_"))


def main(out):
    rep = sl.Report()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            pg = sl.open_page(browser, w, h, js=js, lang=lang, url=URL)
            base = f"{w} {lang} {'js' if js else 'nojs'}"
            if js and lang == "ru":
                pg.emulate_media(reduced_motion="reduce")
                base += " reduce"
            if rep.check(sl.login(pg, URL, EMAIL, PASSWORD), f"{base}: вход"):
                pg.goto(AUFBAU)
                refs = rows(pg)
                if rep.check(len(refs) >= 2, f"{base}: строк с «⋯» ≥ 2 ({refs})"):
                    run_case(rep, pg, f"{base} visible", refs[-1], js, False, out)
                    pg.goto(AUFBAU)
                    hide(pg, refs[-2])
                    run_case(rep, pg, f"{base} hidden", refs[-2], js, True, out)
            pg.context.close()
    rep.finish()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_e9_stand")
