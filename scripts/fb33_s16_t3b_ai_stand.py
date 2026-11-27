"""FB-33 стопка 16 T3b (T3.1): стенд «🌐 Übersetzen» у полосы доверия (USP) и у SEO страницы.

Кит `shop` стенд-БД владельца: языки de/ru/en; полоса доверия главной (два пункта, у первого
сохранён перевод ru заголовка) и «Über uns» (`info`) с немецким SEO и сохранённым переводом ru
заголовка. Ответ эндпоинта перевода подменён в браузере (`pg.route` на
`dashboard/uebersetzen/`): «перевод» = «RU <текст>», у описания SEO — длиннее потолка 200.
Обход `matrix()` (1440/390, кабинет de/ru, без JS и с JS), обе формы:

- без JS — кнопка в DOM, но скрыта; у каждого поля перевода `data-i18n-of` находит поле формы;
- с JS — кнопка видна в блоке языков, ≥ 44 px, имя — видимое «Übersetzen» + язык с `lang`;
  заполняются только ПУСТЫЕ поля ru (негативный контроль: сохранённые переводы не тронуты и не
  уходят в запрос; поля en пусты); в запрос уходит `max` = `maxlength` поля (SEO 70/200, USP
  120/200); пометка ИИ видна у заполненных, `aria-describedby` — на существующий id
  `bwtr-ai-note-<ns>`; живая область — `data-form-status` своего блока (шпион
  `MutationObserver`), одно `change` → один POST в черновик; фокус на кнопке; «Abbrechen»
  окна снимает перевод ИИ; повторный перевод — в черновике после перезагрузки, описание SEO
  обрезано до 200 (как ручной ввод).

Запуск (стенд-БД — копия `platform_m39_stand`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_s16_t3b_ai_stand.py --setup
    AI_ENABLED=True AI_TASKS_ENABLED=i18n_translate DB_CONN_MAX_AGE=0 DB_NAME=<стенд-БД> \\
        REDIS_CACHE_URL=redis://localhost:6379/<N> uv run python manage.py runserver \\
        0.0.0.0:<порт> --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> DB_NAME=<стенд-БД> \\
        uv run --no-project --with playwright python scripts/fb33_s16_t3b_ai_stand.py <папка>
Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import json
import os
import re
import subprocess
import sys

import standlib as sl

EMAIL = "shop@example.com"
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
DE_TITLE, DE_DESC = "Über uns — Laden am Markt", "Seit 1950 in Solingen."
RU_TITLE = "О нас — лавка на рынке"
RU_USP0 = "Свежая выпечка"
SETUP = f"""
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="shop")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {{}})
cfg["usp_bar"] = [
    {{"icon": "bio", "label": "Frisch gebacken", "text": "Jeden Morgen"}},
    {{"icon": "local", "label": "Aus Solingen", "text": "Seit 1950"}},
]
for s in cfg["sections"]:
    if s.get("key") == "usp_bar":
        s["enabled"] = True
cfg["seo"] = {{**(cfg.get("seo") or {{}}), "pages": {{"info": {{
    "title": {DE_TITLE!r}, "description": {DE_DESC!r}}}}}}}
i18n = dict(cfg.get("i18n") or {{}})
for loc in ("ru", "en", "tr", "uk"):
    (i18n.get(loc) or {{}}).pop("usp_bar", None)
    (i18n.get(loc) or {{}}).pop("seo", None)
i18n["ru"] = {{**(i18n.get("ru") or {{}}),
    "usp_bar": [{{"label": {RU_USP0!r}}}, {{}}],
    "seo": {{"pages": {{"info": {{"title": {RU_TITLE!r}}}}}}}}}
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
AUFBAU = U + "/dashboard/site/aufbau/"
DLG = "dialog.ui-bwin"
LONG = 250  # ответ «модели» длиннее потолка описания SEO (200)
#: форма → (адрес окна, id формы, ns, сохранённые переводы ru — негативный контроль,
#: пустые поля ru → немецкое поле-источник, потолки `max` пустых полей)
PARTS = {
    "usp": (
        "?seite=home&block=usp_bar&tab=texte",
        "bw-form-usp",
        "usp",
        {"f_tr_usp_0_label_ru": RU_USP0},
        {
            "f_tr_usp_0_text_ru": "f_usp_0_text",
            "f_tr_usp_1_label_ru": "f_usp_1_label",
            "f_tr_usp_1_text_ru": "f_usp_1_text",
        },
        {120, 200},
    ),
    "seo": (
        "?seite=text&block=__page&tab=texte",
        "bw-form-seo",
        "seo",
        {"f_tr_seo_title_ru": RU_TITLE},
        {"f_tr_seo_description_ru": "f_seo_description"},
        {200},
    ),
}
rep = sl.Report()
SENT: list[list[dict]] = []
POSTS: list[str] = []


def fake_translate(route):
    """Ответ эндпоинта AIS-5 без модели: тот же контракт JSON (`state: done`, `items`)."""
    body = route.request.post_data or ""
    items = json.loads(re.search(r'name="items"\r\n\r\n(.*?)\r\n--', body, re.S).group(1))
    target = re.search(r'name="target"\r\n\r\n(\w+)\r\n', body).group(1)
    SENT.append(items)
    got = {}
    for i in items:
        text = f"{target.upper()} {i['text']}"
        if i["text"] == DE_DESC:
            text = (text + " ") + "x" * LONG  # длиннее потолка — запись обрежет
        got[i["id"]] = text
    data = {"state": "done", "items": got, "skipped": 0}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))


def busy_done(pg):
    pg.wait_for_timeout(400)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def window(pg, query, js):
    pg.goto(AUFBAU + query)
    sl.settle(pg, js)


def val(pg, sc, name):
    return pg.locator(f"{sc} [name={name}]").input_value()


def nojs_part(pg, tag, part):
    query, fid, _ns, _saved, _src, _caps = PARTS[part]
    sc = f"#{fid}"
    window(pg, query, False)
    btn = pg.locator(f"{sc} [data-i18n-translate]")
    rep.check(
        btn.count() == 1 and not btn.is_visible(), f"{tag} {part}: без JS кнопка в DOM, не видна"
    )
    srcs = pg.eval_on_selector_all(
        f"{sc} [data-i18n-loc] input, {sc} [data-i18n-loc] textarea",
        "es => es.map(e => [e.getAttribute('data-i18n-of'), !!(e.form && e.form.elements[e.getAttribute('data-i18n-of')])])",
    )
    rep.check(
        srcs and all(ok for _of, ok in srcs), f"{tag} {part}: источник у каждого поля ({srcs[:3]})"
    )
    sl.a11y_check(rep, pg, f"{tag} {part}", scope=sc, minimum=44)
    sl.shot(pg, OUT, f"t3b_{part}_{tag.replace(' ', '_')}")


SPY = """(sc) => { window.__t3 = {status: [], own: []};
  const watch = (el, key) => el && new MutationObserver(() => {
      if (el.textContent.trim()) window.__t3[key].push(el.textContent.trim()); })
    .observe(el, {childList: true, characterData: true, subtree: true});
  watch(document.querySelector(sc + ' [data-form-status]'), 'status');
  watch(document.querySelector(sc + ' [data-i18n-translate-status]'), 'own'); }"""


def translate(pg, sc):
    pg.locator(f"{sc} [data-i18n-translate]").click()
    pg.wait_for_function(
        """(sc) => { const s = document.querySelector(sc + ' [data-form-status]');
                     const b = document.querySelector(sc + ' [data-i18n-translate]');
                     return s && s.textContent.trim() && b && !b.hasAttribute('aria-busy'); }""",
        arg=sc,
        timeout=20000,
    )
    busy_done(pg)


def js_part(pg, tag, part):
    query, fid, ns, saved, srcs, caps = PARTS[part]
    sc = f"{DLG} #{fid}"
    window(pg, query, True)
    btn = pg.locator(f"{sc} [data-i18n-translate]")
    rep.check(btn.count() == 1 and btn.is_visible(), f"{tag} {part}: кнопка видна")
    rep.check(btn.get_attribute("data-loc") == "ru", f"{tag} {part}: язык кнопки — ru")
    note = btn.get_attribute("data-note")
    rep.check(note == f"bwtr-ai-note-{ns}", f"{tag} {part}: id пометки по ns ({note})")
    h = btn.evaluate("b => b.getBoundingClientRect().height")
    rep.check(h >= 43.5, f"{tag} {part}: кнопка ≥ 44 px ({h})")
    name = btn.evaluate(
        """b => { const c = b.cloneNode(true);
                  c.querySelectorAll('[aria-hidden=true]').forEach(x => x.remove());
                  const v = c.cloneNode(true);
                  v.querySelectorAll('.sr-only').forEach(x => x.remove());
                  const vis = v.textContent.replace(/\\s+/g, ' ').trim();
                  return [vis, c.textContent.replace(/\\s+/g, ' ').trim(),
                          (b.querySelector('.sr-only [lang]') || {}).lang || ''] }"""
    )
    rep.check(
        name[0] and name[1].startswith(name[0]) and name[1] != name[0] and name[2] == "ru",
        f"{tag} {part}: имя кнопки — видимое + язык ({name})",
    )
    sl.a11y_check(rep, pg, f"{tag} {part}", scope=sc, minimum=44)
    pg.evaluate(SPY, sc)
    SENT.clear()
    POSTS.clear()
    translate(pg, sc)
    sc = f"{DLG} #{fid}"
    for tr_name, de_name in srcs.items():
        de = val(pg, sc, de_name)
        got = val(pg, sc, tr_name)
        rep.check(
            got.startswith(f"RU {de}"), f"{tag} {part}: пустое поле переведено ({tr_name}={got!r})"
        )
    for name_, want in saved.items():
        got = val(pg, sc, name_)
        rep.check(got == want, f"{tag} {part}: сохранённое не тронуто ({name_}={got!r})")
    sent = SENT[0] if SENT else []
    texts = [i["text"] for i in sent]
    rep.check(
        len(sent) == len(srcs) and not any(re.search("[а-я]", t) for t in texts),
        f"{tag} {part}: в запрос ушли только пустые поля ({texts})",
    )
    rep.check(
        {i.get("max") for i in sent} == caps,
        f"{tag} {part}: потолки в запросе — maxlength ({[i.get('max') for i in sent]})",
    )
    en = pg.eval_on_selector_all(
        f"{sc} [data-i18n-loc=en] input, {sc} [data-i18n-loc=en] textarea",
        "es => es.map(e => e.value).filter(Boolean)",
    )
    rep.check(not en, f"{tag} {part}: поля en не тронуты ({en})")
    marks = pg.locator(f"{sc} [data-ai-mark]:visible").count()
    rep.check(marks == len(srcs), f"{tag} {part}: пометка ИИ видна у заполненных ({marks})")
    first = next(iter(srcs))
    desc = pg.locator(f"{sc} [name={first}]").get_attribute("aria-describedby") or ""
    rep.check(
        note in desc.split() and pg.locator(f"#{note}").count() == 1,
        f"{tag} {part}: aria-describedby → пометка ({desc!r})",
    )
    spy = pg.evaluate("window.__t3")
    rep.check(
        len(spy["status"]) >= 1 and not spy["own"],
        f"{tag} {part}: одна живая область на событие ({spy})",
    )
    rep.check(
        len([p for p in POSTS if "aufbau" in p]) == 1,
        f"{tag} {part}: один POST в черновик ({POSTS})",
    )
    focus = pg.evaluate(
        "document.activeElement && document.activeElement.hasAttribute('data-i18n-translate')"
    )
    rep.check(focus, f"{tag} {part}: фокус на кнопке")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag} {part}: без гор. прокрутки ({over}px)", code="overflow")
    sl.shot(pg, OUT, f"t3b_{part}_{tag.replace(' ', '_')}_done")
    # «Abbrechen» окна — перевод ИИ снят (до перезагрузки: она даёт новый токен открытия окна)
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-window-actions] button[value=revert]")
    pg.wait_for_load_state()
    window(pg, query, True)
    got = val(pg, sc, first)
    rep.check(got == "", f"{tag} {part}: «Abbrechen» снимает перевод ИИ ({got!r})")
    rep.check(pg.locator(f"{sc} [data-ai-mark]:visible").count() == 0, f"{tag} {part}: пометок нет")
    # снова перевод — он в черновике (переживает перезагрузку); потолок — как у ручного ввода
    translate(pg, sc)
    pg.reload()
    sl.settle(pg, True)
    got = val(pg, sc, first)
    rep.check(got.startswith("RU "), f"{tag} {part}: перевод в черновике ({got[:40]!r})")
    if part == "seo":
        rep.check(len(got) <= 200, f"{tag} {part}: описание обрезано до 200 ({len(got)})")
    for name_, want in saved.items():
        rep.check(val(pg, sc, name_) == want, f"{tag} {part}: сохранённое на месте ({name_})")


def storefront(pg, tag):
    pg.goto(f"{U}/lang/?lang=ru&next=/")
    pg.wait_for_load_state()
    html = pg.content()
    rep.check("RU " not in html, f"{tag}: витрина ru без «Speichern» — прежняя")
    rep.check(RU_USP0 in html, f"{tag}: витрина ru — сохранённый перевод USP")


with sl.launch() as browser:
    for w, h, lang, js in sl.matrix():
        if not setup():
            rep.check(False, "setup")
            break
        pg = sl.open_page(browser, w, h, js=js, lang=lang, url=U)
        pg.context.route("**/dashboard/uebersetzen/", fake_translate)
        pg.on(
            "request",
            lambda r: (
                POSTS.append(r.url) if r.method == "POST" and "uebersetzen" not in r.url else None
            ),
        )
        tag = f"{w} {lang} {'js' if js else 'nojs'}"
        if rep.check(sl.login(pg, U, EMAIL, PASSWORD), f"{tag}: вход"):
            for part in PARTS:
                if js:
                    js_part(pg, tag, part)
                else:
                    nojs_part(pg, tag, part)
            storefront(pg, tag)
            rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
        pg.context.close()
rep.finish("T3b USP/SEO Übersetzen")
