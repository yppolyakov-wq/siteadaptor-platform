"""FB-33 стопка 14 E9: «Abbrechen» окна блока — к якорю строки, сообщение у строки.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 «E9», §5.3, правки ревью диффа E9. Без JS: адрес
несёт `abbruch` и `#schema-row-<ref>`, строка — цель якоря (`:target`), строка и абзац
`#schema-cancel-msg` видны (не под липкой шапкой — `elementFromPoint`), абзац перед строкой, живая
область пуста. С JS: фокус на ⚙ строки (у скрытой — на её ссылке в раскрытом «Ausgeblendet»),
в адресе нет ни якоря, ни `abbruch`, описание абзацем снято (текст звучит один раз — живой
областью, без «⚠»); F5 молчит. Tab после возврата — «⋯» этой строки. Итоги: «нечего» (все
сочетания), «zurückgenommen» (другая ширина в «Platz») и конфликт (вторым контекстом «Speichern» того же блока) — на
1440 de и 390 ru. Проход ru с JS — с `prefers-reduced-motion: reduce`.

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
#: итоги «zurückgenommen» и конфликт — на этих сочетаниях (оба режима JS)
FULL = {(1440, "de"), (390, "ru")}

IN_VIEW = """(sel) => { const e = document.querySelector(sel); if (!e) return null;
  const r = e.getBoundingClientRect();
  return {top: r.top, bottom: r.bottom, h: innerHeight}; }"""
#: центр элемента не закрыт ничем чужим (липкая шапка, полоса черновика)
HIT = """(sel) => { const e = document.querySelector(sel); if (!e) return null;
  const r = e.getBoundingClientRect();
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!t && (t === e || e.contains(t)); }"""
ACTIVE = """() => { const a = document.activeElement; return a ? (a.getAttribute('data-schema-gear')
  || a.getAttribute('data-schema-block') || a.id || a.tagName) : null; }"""
#: текст абзаца без `aria-hidden` («⚠») — то, что должно прозвучать
SPOKEN = """() => { const m = document.getElementById('schema-cancel-msg'); if (!m) return '';
  const c = m.cloneNode(true); c.querySelectorAll('[aria-hidden]').forEach(n => n.remove());
  return c.textContent.replace(/\\s+/g, ' ').trim(); }"""


def rows(pg):
    """Видимые строки с «⋯» (их можно скрыть), сверху вниз."""
    return pg.evaluate(
        "() => [...document.querySelectorAll('[data-schema-lines] [data-schema-gear]')]"
        ".map(a => a.getAttribute('data-schema-gear'))"
        ".filter(r => document.getElementById('schema-more-' + r))"
    )


def wide_line(pg):
    """ref среднего блока ряда из 3+ блоков (или None)."""
    return pg.evaluate(
        "() => { for (const li of document.querySelectorAll('[data-schema-lines] > li')) {"
        " const g = [...li.querySelectorAll('[data-schema-gear]')];"
        " if (g.length >= 3) return g[1].getAttribute('data-schema-gear'); } return null; }"
    )


def hide(pg, ref):
    pg.click(f"#schema-more-{ref}")
    with pg.expect_navigation():
        pg.click(f"details:has(> #schema-more-{ref}) button[value=toggle]")
    pg.wait_for_selector(f"[data-schema-hidden] #schema-row-{ref}", state="attached")


def open_window(pg, ref, js, tab=""):
    pg.goto(AUFBAU + f"&block={ref}" + (f"&tab={tab}" if tab else ""))
    if js:
        pg.wait_for_selector("[data-window-actions] button[value=revert]", state="visible")


def edit_width(pg, ref, js):
    """Правка строки в окне — другая ширина (кнопка формы «Platz»; без JS — обычная отправка).
    Ждём новое состояние (нажатая плитка), а не загрузку."""
    open_window(pg, ref, js, "wie")
    btn = pg.locator("[data-schema-width] button[name=value]:not(.border-2)").first
    value = btn.get_attribute("value")
    btn.click()
    pg.wait_for_selector(f"[data-schema-width] button.border-2[value='{value}']", state="attached")
    if js:
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=10000
        )
        pg.wait_for_selector("[data-window-actions] button[value=revert]", state="visible")


def make_row3(pg, refs, js):
    """Первые три строки с выбором ширины — по трети (черновик сессии): ряд из трёх блоков."""
    done = 0
    for ref in refs:
        if done == 3:
            break
        open_window(pg, ref, js, "wie")
        btn = pg.locator("[data-schema-width] button[name=value][value=w13]")
        done += bool(btn.count())
        if btn.count() and "border-2" not in (btn.get_attribute("class") or ""):
            btn.click()
            pg.wait_for_selector("[data-schema-width] button.border-2[value=w13]", state="attached")
            if js:
                pg.wait_for_function(
                    "!+document.documentElement.getAttribute('data-schema-busy')", timeout=10000
                )
    pg.goto(AUFBAU)
    return wide_line(pg)


def width_ref(pg, refs, js):
    for ref in refs:
        open_window(pg, ref, js, "wie")
        if pg.locator("[data-schema-width] button[name=value]:not(.border-2)").count():
            return ref
    return None


def revert(pg, js):
    with pg.expect_navigation():
        pg.click("[data-window-actions] button[value=revert]")
    pg.wait_for_load_state("load")
    if js:
        pg.wait_for_timeout(800)  # задержанная озвучка ~300 мс


def check_back(rep, pg, tag, ref, js, kind, out):
    """Страница после «Abbrechen»: всё про сообщение, якорь, фокус и озвучку."""
    sl.settle(pg, js, rep)
    url = pg.url
    msg = pg.locator("#schema-cancel-msg")
    rep.check(msg.count() == 1, f"{tag}: сообщение у строки ({msg.count()})", code="msg")
    got = msg.get_attribute("data-schema-cancel") if msg.count() else None
    rep.check(got == kind, f"{tag}: итог {kind} ({got})", code="kind")
    text = " ".join(msg.inner_text().split()) if msg.count() else ""
    rep.check(text not in pg.locator("[data-schema-messages]").inner_text(), f"{tag}: вверху нет")
    if kind == "conflict":
        strong = msg.locator("strong")
        rep.check(
            strong.count() == 1 and text.startswith(" ".join(strong.inner_text().split())),
            f"{tag}: префикс «Nicht übernommen:» ({text[:30]!r})",
            code="prefix",
        )
    hidden = pg.evaluate(
        f"() => !!document.querySelector('[data-schema-hidden] #schema-row-{ref}')"
    )
    order = pg.evaluate(
        """(ref) => { const m = document.getElementById('schema-cancel-msg');
        const a = document.getElementById('schema-row-' + ref); if (!m || !a) return null;
        return !!(m.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING); }""",
        ref,
    )
    rep.check(order is True, f"{tag}: абзац перед строкой ({order})", code="order")
    described = pg.evaluate(
        f"() => (document.getElementById('schema-row-{ref}').getAttribute('aria-describedby')"
        " || '').includes('schema-cancel-msg')"
    )
    if hidden:
        opened = pg.evaluate("() => !!document.querySelector('[data-schema-hidden][open]')")
        rep.check(opened, f"{tag}: «Ausgeblendet» раскрыт", code="details")
    for sel, what in ((f"#schema-row-{ref}", "строка"), ("#schema-cancel-msg", "сообщение")):
        box = pg.evaluate(IN_VIEW, sel)
        rep.check(
            box is not None and 0 <= box["top"] and box["bottom"] <= box["h"],
            f"{tag}: {what} в окне просмотра ({box})",
            code="in-view",
        )
        rep.check(pg.evaluate(HIT, sel) is True, f"{tag}: {what} ничем не закрыта", code="hit")
    live = " ".join((pg.locator("[data-schema-live]").text_content() or "").split())
    if js:
        rep.check(pg.evaluate(ACTIVE) == ref, f"{tag}: фокус на строке ({pg.evaluate(ACTIVE)})")
        rep.check("#" not in url and "abbruch" not in url, f"{tag}: адрес чистый ({url[-50:]})")
        rep.check(not described, f"{tag}: описание абзацем снято (звучит раз)", code="twice")
        spoken = pg.evaluate(SPOKEN)
        rep.check(
            live == spoken and "⚠" not in live, f"{tag}: живая область ({live!r})", code="live"
        )
    else:
        rep.check(
            f"abbruch={kind}" in url and url.endswith(f"#schema-row-{ref}"),
            f"{tag}: адрес — abbruch и якорь ({url[-60:]})",
        )
        target = pg.evaluate("() => (document.querySelector(':target') || {}).id || null")
        rep.check(target == f"schema-row-{ref}", f"{tag}: цель якоря — строка ({target})")
        rep.check(described, f"{tag}: aria-describedby на абзац", code="described")
        rep.check(not live, f"{tag}: живая область пуста ({live!r})", code="live")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
    # схема (строки и «Ausgeblendet») — область среза; сайдбар кабинета без JS даёт прежние
    # цели < 44 px (до E9 так же, не предмет среза)
    sl.a11y_check(rep, pg, tag, scope="[data-schema-blocks]", minimum=44)
    if hidden:
        sl.a11y_check(rep, pg, tag + " hidden-list", scope="[data-schema-hidden]", minimum=44)
    sl.shot(pg, out, tag.replace(" ", "_"))
    if not hidden and pg.locator(f"#schema-more-{ref}").count():
        pg.keyboard.press("Tab")
        nxt = pg.evaluate("() => document.activeElement && document.activeElement.id")
        rep.check(nxt == f"schema-more-{ref}", f"{tag}: Tab → «⋯» строки ({nxt})", code="tab")
    if js:
        pg.reload()
        pg.wait_for_load_state("load")
        pg.wait_for_timeout(800)
        again = pg.locator("[data-schema-live]").text_content() or ""
        rep.check(
            not again and pg.locator("#schema-cancel-msg").count() == 0,
            f"{tag}: F5 молчит ({again!r})",
            code="f5",
        )


def main(out):
    rep = sl.Report()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            pg = sl.open_page(browser, w, h, js=js, lang=lang, url=URL)
            base = f"{w} {lang} {'js' if js else 'nojs'}"
            if js and lang == "ru":
                pg.emulate_media(reduced_motion="reduce")
                base += " reduce"
            if not rep.check(sl.login(pg, URL, EMAIL, PASSWORD), f"{base}: вход"):
                pg.context.close()
                continue
            pg.goto(AUFBAU)
            refs = rows(pg)
            if rep.check(len(refs) >= 2, f"{base}: строк с «⋯» ≥ 2 ({refs})"):
                open_window(pg, refs[-1], js)
                revert(pg, js)
                check_back(rep, pg, f"{base} visible", refs[-1], js, "same", out)
                three = make_row3(pg, refs, js) if w == 390 else None
                if three:
                    open_window(pg, three, js)
                    revert(pg, js)
                    check_back(rep, pg, f"{base} row3", three, js, "same", out)
                elif w == 390:
                    rep.note(f"{base}: ряда из 3 блоков на главной нет")
                pg.goto(AUFBAU)
                hide(pg, refs[-2])
                open_window(pg, refs[-2], js)
                revert(pg, js)
                check_back(rep, pg, f"{base} hidden", refs[-2], js, "same", out)
            if (w, lang) in FULL:
                pg.goto(AUFBAU)
                ref = width_ref(pg, rows(pg), js)
                if rep.check(ref is not None, f"{base}: строка с «Platz»"):
                    edit_width(pg, ref, js)
                    revert(pg, js)
                    check_back(rep, pg, f"{base} done", ref, js, "done", out)
                    # конфликт: окно открыто и правлено здесь, «Speichern» — в другом контексте
                    edit_width(pg, ref, js)
                    other = sl.open_page(browser, w, h, js=js, lang=lang, url=URL)
                    if rep.check(sl.login(other, URL, EMAIL, PASSWORD), f"{base}: вход 2"):
                        edit_width(other, ref, js)
                        other.goto(AUFBAU)
                        with other.expect_navigation():
                            other.click("button[name=op][value=save]")
                    other.context.close()
                    revert(pg, js)
                    check_back(rep, pg, f"{base} conflict", ref, js, "conflict", out)
            pg.context.close()
    rep.finish()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_e9_stand")
