"""FB-33 стопка 15 M5e-1b: «Texte» секций главной в окне блока (артборд M5eTexte).

План — `docs/fb33-stack15-plan-2026-11-25.md` §2 «M5e-1», §5.3 (строка M5e-1), §14.2 Y1/Y2/Y5/Y6.
Кит `friseur` (секции «Über uns», «Aufruf zum Handeln», «Unser Team»). Проверки на 1440/390,
de/ru, с JS и без: часть `hometext` на «Texte» (форма `bw-form-hometext`, подсказка «Dieselben
Felder wie im Studio.»), у каждого поля видимая метка, пункты команды — fieldset/legend; окно
без горизонтальной прокрутки; `a11y_check` по окну (цели 44). С JS, de: 320×568 и 720×450
(200 %); проход только клавиатурой (вкладка → поле → «Übernehmen», видимый фокус, Esc);
негативный контроль — `javascript:` в ссылке кнопки (ошибка у поля, `aria-invalid`) и
2001 знак в тексте «Über uns» (`maxlength` 2000). В конце черновик отбрасывается.

Запуск:

    DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 python manage.py runserver 0.0.0.0:8082 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://friseur.siteadaptor.de:8082 \\
        uv run --no-project --with playwright python scripts/fb33_m5e1b_hometext_stand.py <папка>

Итог: «N ✓, M ✗». Не входит в CI.
"""

import sys
from urllib.parse import urlparse

import standlib as sl

PORT = urlparse(sl.BASE_URL).port or 80
SLUG = "friseur"
BASE = f"http://{SLUG}.{sl.BASE_DOMAIN}:{PORT}"
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
DLG = "dialog.ui-bwin"
FORM = "#bw-form-hometext"
REFS = ("about", "cta", "team")
HINT = {"de": "Dieselben Felder wie im Studio.", "ru": ""}
MODEL_JS = """() => {
  const f = document.querySelector('#bw-form-hometext');
  if (!f) return null;
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const fields = [...f.querySelectorAll('input[type=text], textarea')].filter(vis);
  const labelled = fields.every(el => {
    const l = f.querySelector('label[for="' + el.id + '"]');
    return l && vis(l) && l.innerText.trim().length > 0;
  });
  const win = document.querySelector('dialog.ui-bwin[open]') || document.querySelector('[data-schema-panel]');
  return {
    hint: (f.querySelector('#bw-htx-hint') || {}).innerText || '',
    fields: fields.length, labelled,
    legends: [...f.querySelectorAll('fieldset > legend')].map(l => l.innerText.trim()),
    pxHeight: [...f.querySelectorAll('textarea')].some(t => /height/.test(t.getAttribute('style') || '')),
    winOver: win ? win.scrollWidth - win.clientWidth : 0,
  };
}"""


def aufbau(pg, query=""):
    pg.goto(f"{BASE}/dashboard/site/aufbau/?seite=home{query}")


def open_texte(pg, ref, js) -> bool:
    """Окно секции на вкладке «Texte»: с JS — кликом по строке и вкладке, без JS — ссылками."""
    if not js:
        aufbau(pg, f"&block={ref}&tab=texte")
        return pg.query_selector(FORM) is not None
    aufbau(pg)
    sel = f'a[data-schema-block="{ref}"]'
    if pg.query_selector(sel) is None:
        return False
    pg.click(sel)
    try:
        pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        tab = pg.query_selector(f'{DLG}[open] [data-window-tab-link="texte"]')
        if tab is not None:
            tab.click()
            pg.wait_for_selector(f"{DLG}[open] {FORM}", state="visible", timeout=10000)
    except Exception:  # noqa: BLE001 — стенд сообщает ✗, а не падает
        return False
    sl.settle(pg, js)
    return pg.query_selector(FORM) is not None


def check_window(rep, pg, t, ref, lang, js):
    m = pg.evaluate(MODEL_JS)
    if not rep.check(m is not None, f"{t}: форма «Texte» есть", code="form"):
        return
    if HINT[lang]:
        rep.check(m["hint"] == HINT[lang], f"{t}: подсказка «{m['hint']}»", code="hint")
    else:
        rep.check(bool(m["hint"]), f"{t}: подсказка есть ({m['hint']})", code="hint")
    rep.check(m["fields"] > 0 and m["labelled"], f"{t}: видимые метки у {m['fields']} полей")
    if ref == "team":
        rep.check(len(m["legends"]) >= 2, f"{t}: пункты — fieldset/legend ({m['legends'][:3]})")
    rep.check(not m["pxHeight"], f"{t}: высота textarea не в px", code="px")
    rep.check(m["winOver"] <= 0, f"{t}: окно без гор. прокрутки ({m['winOver']}px)", code="win")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{t}: без гор. скролла ({over}px)", code="overflow")
    sl.a11y_check(rep, pg, t, scope=f"{DLG}[open]" if js else FORM, minimum=44)


def keyboard_pass(rep, pg, out):
    """Только клавиатура (с JS, de, 1440): вкладка «Texte» → первое поле → «Übernehmen»;
    видимый фокус у каждого шага; Esc закрывает окно."""
    if not open_texte(pg, "about", True):
        rep.check(False, "клавиатура: окно открыто")
        return
    pg.focus(f'{DLG}[open] [data-window-tab-link="texte"]')
    seen = []
    for _ in range(12):
        pg.keyboard.press("Tab")
        info = pg.evaluate(
            """() => { const a = document.activeElement; const s = getComputedStyle(a);
              return {name: a.getAttribute('name') || a.tagName, inForm: !!a.closest('#bw-form-hometext'),
                ring: s.outlineStyle !== 'none' || s.boxShadow !== 'none'}; }"""
        )
        seen.append(info)
        if info["name"] == "op":
            break
    names = [s["name"] for s in seen]
    rep.check("f_about_title" in names, f"клавиатура: до поля «Überschrift» ({names})")
    rep.check(
        all(s["ring"] for s in seen if s["inForm"]),
        "клавиатура: видимый фокус в форме",
        code="ring",
    )
    sl.shot(pg, out, "keyboard_about")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(400)
    rep.check(pg.query_selector(f"{DLG}[open]") is None, "клавиатура: Esc закрывает окно")


def negative(rep, pg, out, js):
    """`javascript:` в ссылке кнопки — ошибка у поля; 2001 знак — не больше 2000."""
    tag = "js" if js else "nojs"
    if not open_texte(pg, "cta", js):
        rep.check(False, f"{tag} негатив: окно cta открыто")
        return
    pg.fill(f"{FORM} [name=f_cta_button_url]", "javascript:alert(1)")
    if js:
        pg.dispatch_event(f"{FORM} [name=f_cta_button_url]", "change")
        pg.wait_for_timeout(1200)
    else:
        with pg.expect_navigation():
            pg.click(f"{FORM} button[name=op][value=update]:not(.sr-only)")
    # ошибка показывается один раз — в ответе на эту правку (окно не открываем заново)
    field = pg.query_selector(f"{FORM} [name=f_cta_button_url]")
    invalid = field.get_attribute("aria-invalid") if field else None
    err = pg.query_selector("#schema-f-cta_button_url-err")
    rep.check(
        invalid == "true" and err is not None,
        f"{tag} негатив: ошибка у поля ссылки (aria-invalid={invalid})",
        code="url-err",
    )
    sl.shot(pg, out, f"negative_url_{tag}")
    if not open_texte(pg, "about", js):
        return
    sel = f"{FORM} [name=f_about_text]"
    pg.fill(sel, "")
    pg.focus(sel)
    pg.keyboard.insert_text("A" * 1990)
    pg.keyboard.type("B" * 11)
    size = pg.eval_on_selector(sel, "el => el.value.length")
    rep.check(size <= 2000, f"{tag} негатив: 2001 знак — в поле {size}", code="maxlength")


def discard(pg):
    aufbau(pg)
    btn = pg.query_selector("button[name=op][value=discard]")
    if btn is not None:
        btn.click()
        pg.wait_for_load_state()


def main(out):
    rep = sl.Report()
    with sl.launch() as browser:
        for js in sl.JS_MODES:
            for lang in sl.LANGS:
                pg = sl.open_page(browser, 1440, 900, js=js, lang=lang, url=BASE)
                tag = f"{lang} {'js' if js else 'nojs'}"
                if not rep.check(
                    sl.login(pg, BASE, f"{SLUG}@example.com", PASSWORD), f"{tag}: вход"
                ):
                    pg.context.close()
                    continue
                for w, h in sl.SIZES:
                    pg.set_viewport_size({"width": w, "height": h})
                    for ref in REFS:
                        t = f"{w} {tag} {ref}"
                        if rep.check(open_texte(pg, ref, js), f"{t}: окно «Texte» открыто"):
                            check_window(rep, pg, t, ref, lang, js)
                            sl.shot(pg, out, t.replace(" ", "_"))
                if lang == "de":
                    pg.set_viewport_size({"width": 1440, "height": 900})
                    negative(rep, pg, out, js)
                    if js:
                        keyboard_pass(rep, pg, out)
                        for w, h, name in ((320, 568, "320"), (720, 450, "200 %")):
                            pg.set_viewport_size({"width": w, "height": h})
                            t = f"{name} ({w}×{h}) about"
                            if rep.check(open_texte(pg, "about", True), f"{t}: окно открыто"):
                                m = pg.evaluate(MODEL_JS)
                                rep.check(
                                    m is not None and m["winOver"] <= 0,
                                    f"{t}: окно без гор. прокрутки ({m and m['winOver']})",
                                    code="extreme",
                                )
                                sl.shot(pg, out, t.replace(" ", "_").replace("%", ""))
                    discard(pg)
                rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
                pg.context.close()
    rep.finish("M5e-1b Texte")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5e1b_stand")
