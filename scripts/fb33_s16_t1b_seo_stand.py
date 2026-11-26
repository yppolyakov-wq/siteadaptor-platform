"""FB-33 стопка 16 T1b: стенд переводов SEO страницы в окне ★ «Einstellungen der Seite» → «Texte».

Кит `shop` стенд-БД владельца: «Über uns» (`info`) с немецким SEO и переводом ru заголовка.
Обход `matrix()` (1440/390, кабинет de/ru, без JS и с JS) + 320 px: кнопки языка формы SEO
(свой ns — id `schema-tab-lang-seo-<код>`), поля перевода (подпись «„Titel in der Suche“ –
Übersetzung (…)», «Höchstens 70/200 Zeichen.», `maxlength` 70/200), первая кнопка формы —
«Übernehmen», цели ≥ 44 px, без гор. прокрутки. На 1440: ввод перевода описания → «Vorschau»
(`?preview=1&aufbau=text`, витрина ru) показывает его до «Speichern», сайт — ещё нет →
кнопка языка en (якорь/фокус) → «Fertig» + «Speichern» → витрина ru: `<title>` и
`meta description` переводом; de — немецкие; негативный контроль — en без перевода — немецкое.

Запуск (стенд-БД — копия `platform_m39_stand`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_s16_t1b_seo_stand.py --setup
    DB_CONN_MAX_AGE=0 DB_NAME=<стенд-БД> REDIS_CACHE_URL=redis://localhost:6379/<N> \\
        uv run python manage.py runserver 0.0.0.0:<порт> --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> DB_NAME=<стенд-БД> \\
        uv run --no-project --with playwright python scripts/fb33_s16_t1b_seo_stand.py <папка>
Итог: «N ✓, 0 ✗».
"""

import os
import re
import subprocess
import sys

import standlib as sl

EMAIL = "shop@example.com"
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
DE_TITLE, DE_DESC = "Über uns — Laden am Markt", "Seit 1950 in Solingen."
RU_TITLE, RU_DESC = "О нас — лавка на рынке", "С 1950 года в Золингене."
SETUP = f"""
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="shop")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {{}})
cfg["seo"] = {{**(cfg.get("seo") or {{}}), "pages": {{"info": {{
    "title": {DE_TITLE!r}, "description": {DE_DESC!r}}}}}}}
i18n = dict(cfg.get("i18n") or {{}})
for loc in ("ru", "en", "tr", "uk"):
    (i18n.get(loc) or {{}}).pop("seo", None)
i18n["ru"] = {{**(i18n.get("ru") or {{}}), "seo": {{"pages": {{"info": {{"title": {RU_TITLE!r}}}}}}}}}
cfg["i18n"] = i18n
t.site_config = cfg
t.save(update_fields=["enabled_locales", "default_locale", "site_config"])
from django.core.cache import cache
cache.clear()
print("READY")
"""


def setup() -> bool:
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    out = subprocess.run([*cmd, "-c", SETUP], capture_output=True, text=True, check=False)
    ok = "READY" in out.stdout
    if not ok:
        print(out.stdout[-400:], out.stderr[-800:])
    return ok


if sys.argv[1:] == ["--setup"]:
    sys.exit(0 if setup() else 1)

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://shop.siteadaptor.de:8000").rstrip("/")
WINDOW = U + "/dashboard/site/aufbau/?seite=text&block=__page&tab=texte"
DLG = "dialog.ui-bwin"
rep = sl.Report()


def scope_of(js):
    return f"{DLG} #bw-form-seo" if js else "[data-site-schema] #bw-form-seo"


def submit(pg, js, selector):
    with pg.expect_navigation():
        pg.click(selector)
    sl.settle(pg, js)


def head(pg, path, lang):
    """`<title>` и описание страницы витрины на языке посетителя."""
    pg.goto(f"{U}/lang/?lang={lang}&next={path}")
    pg.wait_for_load_state()
    html = pg.content()
    title = re.search(r"<title>(.*?)</title>", html, flags=re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    og = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    return (
        title.group(1).strip() if title else "",
        desc.group(1) if desc else "",
        og.group(1) if og else None,
    )


def flow(pg, tag, js, w):
    sc = scope_of(js)
    pg.goto(WINDOW)
    sl.settle(pg, js)
    pressed = pg.eval_on_selector_all(
        f"{sc} button[name=f_sprache]", "bs => bs.map(b => [b.id, b.getAttribute('aria-pressed')])"
    )
    rep.check(
        pressed == [["schema-tab-lang-seo-ru", "true"], ["schema-tab-lang-seo-en", "false"]],
        f"{tag}: кнопки языка SEO — свой ns, ru выбран ({pressed})",
    )
    tr = pg.locator(f"{sc} #bw-seo-title-ru")
    rep.check(
        tr.is_visible() and tr.input_value() == RU_TITLE,
        f"{tag}: поле перевода заголовка видно, перевод ru на месте",
    )
    rep.check(pg.locator(f"{sc} #bw-seo-title-en").is_hidden(), f"{tag}: поле en — скрыто")
    label = pg.locator(f"{sc} label[for=bw-seo-title-ru]").inner_text()
    rep.check("Übersetzung" in label or "Перевод" in label, f"{tag}: подпись поля ({label!r})")
    rep.check(
        tr.get_attribute("maxlength") == "70"
        and pg.locator(f"{sc} #bw-seo-description-ru").get_attribute("maxlength") == "200",
        f"{tag}: maxlength 70/200",
    )
    rep.check(
        pg.locator(f"{sc} #bw-seo-title-ru-max").is_visible(),
        f"{tag}: «Höchstens 70 Zeichen.» под полем перевода",
    )
    first = pg.eval_on_selector(
        sc,
        "f => { const b = f.querySelector('button'); "
        "return [b.value, b.tabIndex, b.hasAttribute('aria-hidden')] }",
    )
    rep.check(first == ["update", -1, False], f"{tag}: первая кнопка — «Übernehmen» ({first})")
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' button[name=f_sprache]')]
           .filter(e => e.offsetParent && e.getBoundingClientRect().height < 43.5).length""",
        sc,
    )
    rep.check(small == 0, f"{tag}: кнопки языка ≥ 44 px")
    dup = pg.evaluate(
        "() => { const c = {}; document.querySelectorAll('[id]').forEach(e => "
        "c[e.id] = (c[e.id] || 0) + 1); return Object.keys(c).filter(k => c[k] > 1) }"
    )
    rep.check(dup == [], f"{tag}: id без дублей ({dup[:3]})")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag}: без гор. прокрутки ({over}px)", code="overflow")
    sl.a11y_check(rep, pg, tag, scope=sc, minimum=44)
    sl.shot(pg, OUT, f"t1b_seo_{tag.replace(' ', '_')}")
    if w < 400:
        return
    pg.fill(f"{sc} #bw-seo-description-ru", RU_DESC)
    if js:
        pg.press(f"{sc} #bw-seo-description-ru", "Tab")  # со скриптами правка — по `change`
        pg.wait_for_timeout(500)
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
        )
    else:
        submit(pg, js, f"{sc} button.ui-btn-primary[value=update]")
    # «Vorschau» из черновика: перевод виден до «Speichern», на сайте — ещё нет
    page = pg.context.new_page()
    page.goto(f"{U}/lang/?lang=ru&next=/ueber-uns/")
    page.goto(f"{U}/ueber-uns/?preview=1&aufbau=text")
    page.wait_for_load_state()
    pdesc = re.search(r'<meta name="description" content="([^"]*)"', page.content())
    rep.check(
        bool(pdesc) and pdesc.group(1) == RU_DESC,
        f"{tag}: «Vorschau» ru — описание из черновика ({pdesc.group(1)[:30] if pdesc else ''})",
    )
    _t, live_desc, _og = head(page, "/ueber-uns/", "ru")
    rep.check(live_desc != RU_DESC, f"{tag}: сайт до «Speichern» — без нового перевода")
    page.close()
    pg.goto(WINDOW + "&sprache=ru")
    sl.settle(pg, js)
    sc = scope_of(js)
    submit(pg, js, f"{sc} #schema-tab-lang-seo-en")
    focus = pg.evaluate("document.activeElement && document.activeElement.id")
    rep.check(
        pg.url.endswith("#schema-tab-lang-seo-en") or focus == "schema-tab-lang-seo-en",
        f"{tag}: после кнопки языка — её якорь/фокус ({focus!r})",
    )
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    with pg.expect_navigation():
        pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    for lang, want in (("ru", (RU_TITLE, RU_DESC)), ("de", (DE_TITLE, DE_DESC))):
        title, desc, og = head(pg, "/ueber-uns/", lang)
        rep.check((title, desc) == want, f"{tag}: витрина {lang} — <title>/description ({title})")
        rep.check(og is None or og == title, f"{tag}: витрина {lang} — og:title = <title> ({og})")
        sl.shot(pg, OUT, f"t1b_store_{lang}_{tag.replace(' ', '_')}")
    title, desc, _og = head(pg, "/ueber-uns/", "en")
    rep.check((title, desc) == (DE_TITLE, DE_DESC), f"{tag}: негативный контроль — en без перевода")


with sl.launch() as browser:
    combos = list(sl.matrix()) + [(320, 640, "de", True)]
    for w, h, lang, js in combos:
        if not setup():
            rep.check(False, "setup")
            break
        pg = sl.open_page(browser, w, h, js=js, lang=lang, url=U)
        tag = f"{w} {lang} {'js' if js else 'nojs'}"
        if rep.check(sl.login(pg, U, EMAIL, PASSWORD), f"{tag}: вход"):
            flow(pg, tag, js, w)
            rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
        pg.context.close()
rep.finish("T1b SEO")
