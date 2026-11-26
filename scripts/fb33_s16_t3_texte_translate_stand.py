"""FB-33 стопка 16 T3: стенд «🌐 Übersetzen» во вкладке «Texte» окна блока.

Кит `shop` стенд-БД владельца (демо-киты): языки de/ru/en, C-блок «Text» главной (`t3c`), секция
«Über uns» (тексты главной, `home_texts`) и FAQ. Ответ эндпоинта перевода подменён в браузере
(`pg.route` на `dashboard/uebersetzen/`): «перевод» = «RU <текст>». Обход `matrix()` (1440/390,
кабинет de/ru, без JS и с JS) + 320 px и 720×450 (масштаб 200 %), три части «Texte»:

- без JS — кнопка в DOM, но скрыта; у полей перевода `data-i18n-of` на немецкое поле формы;
- с JS — кнопка видна в блоке языков, ≥ 44 px, имя «…Übersetzen (Sprache: Русский)» (видимое —
  начало имени, у названия языка `lang`); заполняются только ПУСТЫЕ поля выбранного языка
  (негативный контроль: поле, заполненное владельцем, и сохранённый перевод FAQ не тронуты, их
  тексты не уходят в запрос; поля en пусты); у заполненного ИИ поля видна пометка «Automatisch
  übersetzt – bitte prüfen», `aria-describedby` поля — на существующий id; шпион
  `MutationObserver`: на одно нажатие текст получает одна живая область (`data-form-status`);
  одно `change` → один POST в черновик; фокус — на кнопке; правка поля снимает пометку;
  «Abbrechen» окна снимает перевод ИИ, витрина ru прежняя; Esc закрывает окно.

Запуск (стенд-БД — копия `platform_m39_stand`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_s16_t3_texte_translate_stand.py --setup
    AI_ENABLED=True AI_TASKS_ENABLED=i18n_translate DB_CONN_MAX_AGE=0 DB_NAME=<стенд-БД> \\
        REDIS_CACHE_URL=redis://localhost:6379/<N> uv run python manage.py runserver \\
        0.0.0.0:<порт> --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> DB_NAME=<стенд-БД> \\
        uv run --no-project --with playwright python scripts/fb33_s16_t3_texte_translate_stand.py <папка>
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
SETUP = """
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="shop")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {})
cfg["sections"] = [s for s in cfg["sections"] if s.get("id") != "t3c"]
cfg["sections"].insert(1, {"key": "text", "id": "t3c", "enabled": True,
    "data": {"title": "Frisch aus dem Ofen", "body": "Jeden Morgen backen wir Brot."}})
for s in cfg["sections"]:
    if s.get("key") in ("about", "faq"):
        s["enabled"] = True
cfg["about_title"] = "Unsere Backstube"
cfg["about_text"] = "Seit 1950 in Solingen."
cfg["faq"] = [{"q": "Habt ihr glutenfrei?", "a": "Ja, jeden Freitag."},
              {"q": "Kann ich vorbestellen?", "a": "Ja, online."}]
i18n = {}
i18n["ru"] = {"faq": [{"q": "Есть без глютена?"}, {}]}
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
#: часть «Texte» → (блок, id формы, поле владельца ru — негативный контроль, исходники ru)
PARTS = {
    "fields": ("t3c", "bw-form-fields", "f_tr_title_ru", {"f_tr_body_ru": "f_body"}),
    "hometext": (
        "about",
        "bw-form-hometext",
        "f_tr_about_title_ru",
        {"f_tr_about_text_ru": "f_about_text"},
    ),
    "faq": (
        "faq",
        "bw-form-faq",
        "",
        {"faq_0_a_ru": "faq_0_a", "faq_1_q_ru": "faq_1_q", "faq_1_a_ru": "faq_1_a"},
    ),
}
SAVED = {"faq": ("faq_0_q_ru", "Есть без глютена?")}  # сохранённый перевод — не трогается
rep = sl.Report()
SENT: list[list[str]] = []
POSTS: list[str] = []


def fake_translate(route):
    """Ответ эндпоинта AIS-5 без модели: тот же контракт JSON (`state: done`, `items`)."""
    body = route.request.post_data or ""
    items = json.loads(re.search(r'name="items"\r\n\r\n(.*?)\r\n--', body, re.S).group(1))
    target = re.search(r'name="target"\r\n\r\n(\w+)\r\n', body).group(1)
    SENT.append([i["text"] for i in items])
    got = {i["id"]: f"{target.upper()} {i['text']}" for i in items}
    data = {"state": "done", "items": got, "skipped": 0}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))


def busy_done(pg):
    pg.wait_for_timeout(400)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def window(pg, ref, js):
    pg.goto(f"{AUFBAU}?seite=home&block={ref}&tab=texte")
    sl.settle(pg, js)


def val(pg, sc, name):
    return pg.locator(f"{sc} [name={name}]").input_value()


def nojs_part(pg, tag, part):
    ref, fid, _own, _src = PARTS[part]
    sc = f"#{fid}"
    window(pg, ref, False)
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
    rep.check(
        pg.locator(f"{sc} [data-ai-mark]").first.is_hidden(), f"{tag} {part}: пометка ИИ скрыта"
    )
    sl.a11y_check(rep, pg, f"{tag} {part}", scope=sc, minimum=44)
    sl.shot(pg, OUT, f"t3_{part}_{tag.replace(' ', '_')}")


SPY = """(sc) => { window.__t3 = {status: [], own: []};
  const watch = (el, key) => el && new MutationObserver(() => {
      if (el.textContent.trim()) window.__t3[key].push(el.textContent.trim()); })
    .observe(el, {childList: true, characterData: true, subtree: true});
  watch(document.querySelector(sc + ' [data-form-status]'), 'status');
  watch(document.querySelector(sc + ' [data-i18n-translate-status]'), 'own'); }"""


def js_part(pg, tag, part, w):
    ref, fid, own, srcs = PARTS[part]
    sc = f"{DLG} #{fid}"
    window(pg, ref, True)
    btn = pg.locator(f"{sc} [data-i18n-translate]")
    rep.check(btn.count() == 1 and btn.is_visible(), f"{tag} {part}: кнопка видна")
    rep.check(btn.get_attribute("data-loc") == "ru", f"{tag} {part}: язык кнопки — ru")
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
        name[1].startswith(name[0]) and name[1] != name[0] and name[2] == "ru",
        f"{tag} {part}: имя кнопки — видимое + язык ({name})",
    )
    sl.a11y_check(rep, pg, f"{tag} {part}", scope=sc, minimum=44)
    if own:
        pg.fill(f"{sc} [name={own}]", "Мой текст")  # заполнено владельцем
        pg.locator(f"{sc} [name={own}]").blur()  # родной change — по уходу фокуса
        busy_done(pg)
    owned = {own: "Мой текст"} if own else {}
    if part in SAVED:
        owned[SAVED[part][0]] = SAVED[part][1]
    pg.evaluate(SPY, sc)
    SENT.clear()
    POSTS.clear()
    btn.click()
    pg.wait_for_function(
        """(sc) => { const s = document.querySelector(sc + ' [data-form-status]');
                     const b = document.querySelector(sc + ' [data-i18n-translate]');
                     return s && s.textContent.trim() && b && !b.hasAttribute('aria-busy'); }""",
        arg=sc,
        timeout=20000,
    )
    busy_done(pg)
    sc = f"{DLG} #{fid}"
    for tr_name, de_name in srcs.items():
        de = val(pg, sc, de_name)
        got = val(pg, sc, tr_name)
        rep.check(got == f"RU {de}", f"{tag} {part}: пустое поле переведено ({tr_name}={got!r})")
    for name_, want in owned.items():
        got = val(pg, sc, name_)
        rep.check(got == want, f"{tag} {part}: заполненное не тронуто ({name_}={got!r})")
    sent = SENT[0] if SENT else []
    rep.check(
        sent and not any("Мой" in s or "глютен" in s for s in sent) and len(sent) == len(srcs),
        f"{tag} {part}: в запрос ушли только пустые поля ({sent})",
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
    note = btn.get_attribute("data-note")
    rep.check(
        note in desc.split() and pg.locator(f"{sc} #{note}").count() == 1,
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
    sl.shot(pg, OUT, f"t3_{part}_{tag.replace(' ', '_')}_done")
    # правка владельцем снимает пометку и ссылку
    loc = pg.locator(f"{sc} [name={first}]")
    loc.click()
    pg.keyboard.press("End")
    pg.keyboard.type("!")
    desc = loc.get_attribute("aria-describedby") or ""
    rep.check(
        note not in desc.split()
        and pg.locator(f"{sc} [data-ai-mark]:visible").count() == len(srcs) - 1,
        f"{tag} {part}: правка поля снимает пометку ({desc!r})",
    )
    busy_done(pg)
    # «Abbrechen» окна — перевод ИИ снят (до перезагрузки: она даёт новый токен открытия окна)
    with pg.expect_navigation():
        pg.click(f"{DLG} [data-window-actions] button[value=revert]")
    pg.wait_for_load_state()
    window(pg, ref, True)
    got = val(pg, sc, first)
    rep.check(got == "", f"{tag} {part}: «Abbrechen» снимает перевод ИИ ({got!r})")
    rep.check(pg.locator(f"{sc} [data-ai-mark]:visible").count() == 0, f"{tag} {part}: пометок нет")
    # снова перевод — он в черновике (переживает перезагрузку), пометки после неё нет
    pg.locator(f"{sc} [data-i18n-translate]").click()
    pg.wait_for_function(
        """(sc) => { const b = document.querySelector(sc + ' [data-i18n-translate]');
                     return b && !b.hasAttribute('aria-busy') &&
                            document.querySelector(sc + ' [data-ai-filled]'); }""",
        arg=sc,
        timeout=20000,
    )
    busy_done(pg)
    pg.reload()
    sl.settle(pg, True)
    got = val(pg, sc, first)
    rep.check(got.startswith("RU "), f"{tag} {part}: перевод в черновике ({got!r})")
    # Esc закрывает окно
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(800)
    shut = pg.evaluate("!document.querySelector('dialog.ui-bwin[open]')")
    rep.check(shut, f"{tag} {part}: Esc закрывает окно")


def storefront(pg, tag):
    pg.goto(f"{U}/lang/?lang=ru&next=/")
    pg.wait_for_load_state()
    html = pg.content()
    rep.check("RU " not in html, f"{tag}: витрина ru без «Speichern» — прежняя")
    rep.check("Есть без глютена?" in html, f"{tag}: витрина ru — сохранённый перевод FAQ")


with sl.launch() as browser:
    combos = list(sl.matrix()) + [(320, 640, "de", True), (720, 450, "ru", True)]
    for w, h, lang, js in combos:
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
                    js_part(pg, tag, part, w)
                else:
                    nojs_part(pg, tag, part)
            storefront(pg, tag)
            rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
        pg.context.close()
rep.finish("T3 Texte Übersetzen")
