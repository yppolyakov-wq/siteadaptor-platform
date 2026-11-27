"""FB-33 стопка 16 T6: стенд переводов шагов, команды и отзывов в окне блока → «Texte».

Кит `shop` стенд-БД владельца: шаги «Wählen | Online», «Abholen | Im Laden» (перевод ru у обоих),
команда «Anna | Chefin», «Anna | Bäckerin» (две «Anna», перевод ru роли у обеих), отзыв
«Eva | Super!» (перевод ru). Обход `matrix()` (1440/390, кабинет de/ru, без JS и с JS) + 320 px:
блок языков со своим ns (`schema-tab-lang-htx-process-ru`), пункт — fieldset, legend «Schritt 1 ·
„Wählen“» с `lang="de"`, подпись поля «Titel – Übersetzung (…)», `maxlength` 120/2000, у нового
пункта полей перевода нет; команда — у имени «Name wird nicht übersetzt.», у второй «Anna» своё
поле роли. На 1440: перестановка шагов (без JS — обменом полей, как владелец) — переводы едут за
шагом; правка немецкого заголовка с вводом перевода в той же форме — введённое остаётся;
«Fertig» + «Speichern» → витрина ru: переводы на своих пунктах; витрина de — немецкое; Студия ↔
окно — перевод окна лежит в том же оверлее `i18n.ru.process`, что читает Студия (`localize`).
Негативный контроль — шаг без перевода на ru показывает немецкий текст.

Запуск (стенд-БД — копия `platform_m39_stand`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_s16_t6_items_stand.py --setup
    DB_CONN_MAX_AGE=0 DB_NAME=<стенд-БД> REDIS_CACHE_URL=redis://localhost:6379/<N> \\
        uv run python manage.py runserver 0.0.0.0:<порт> --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> DB_NAME=<стенд-БД> \\
        uv run --no-project --with playwright python scripts/fb33_s16_t6_items_stand.py <папка>
Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import json
import os
import subprocess
import sys

import standlib as sl

EMAIL = "shop@example.com"
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
SHELL = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand", "-c"]
SETUP = """
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="shop")
t.enabled_locales = ["de", "ru", "en"]
t.default_locale = "de"
cfg = siteconfig.normalize(t.site_config or {})
cfg["process"] = [{"title": "Wählen", "text": "Online"}, {"title": "Abholen", "text": "Im Laden"}]
cfg["team"] = [
    {"name": "Anna", "role": "Chefin", "photo": ""},
    {"name": "Anna", "role": "Bäckerin", "photo": ""},
]
cfg["testimonials"] = [{"name": "Eva", "text": "Super!"}]
for s in cfg["sections"]:
    if s.get("key") in ("process", "team", "testimonials"):
        s["enabled"] = True
i18n = dict(cfg.get("i18n") or {})
i18n["ru"] = {**(i18n.get("ru") or {}),
    "process": [{"title": "Выбор товара", "text": "Онлайн"}, {"title": "Забрать", "text": "В магазине"}],
    "team": [{"role": "Шеф"}, {"role": "Пекарь"}],
    "testimonials": [{"text": "Супер!"}],
}
for loc in ("en", "tr", "uk"):
    for key in ("process", "team", "testimonials"):
        (i18n.get(loc) or {}).pop(key, None)
cfg["i18n"] = i18n
t.site_config = cfg
t.save(update_fields=["enabled_locales", "default_locale", "site_config"])
from django.core.cache import cache
cache.clear()
print("READY")
"""
READ = """
import json
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
cfg = siteconfig.normalize(Tenant.objects.get(schema_name="shop").site_config)
ru = siteconfig.localize(cfg, "ru")
print("JSON" + json.dumps({"de": cfg["process"], "ru": ru["process"],
      "ov": cfg.get("i18n", {}).get("ru", {}).get("process")}, ensure_ascii=False))
"""


def shell(code: str) -> str:
    out = subprocess.run([*SHELL, code], capture_output=True, text=True, check=False)
    if out.returncode:
        print(out.stdout[-400:], out.stderr[-800:])
    return out.stdout


def setup() -> bool:
    return "READY" in shell(SETUP)


if sys.argv[1:] == ["--setup"]:
    sys.exit(0 if setup() else 1)

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://shop.siteadaptor.de:8000").rstrip("/")
WINDOW = U + "/dashboard/site/aufbau/?seite=home&block={key}&tab=texte"
DLG = "dialog.ui-bwin"
rep = sl.Report()


def scope_of(js):
    return f"{DLG} #bw-form-hometext" if js else "[data-site-schema] #bw-form-hometext"


def busy_done(pg):
    pg.wait_for_timeout(400)
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def open_window(pg, js, key):
    pg.goto(WINDOW.format(key=key))
    sl.settle(pg, js)
    return scope_of(js)


def apply(pg, js, sc, values: dict):
    """Правка полей формы «Texte» так, как её делает владелец: без JS — «Übernehmen», с JS —
    каждое поле по `change` (Tab) и перезагрузка окна."""
    for name, value in values.items():
        pg.fill(f"{sc} [name={name}]", value)
        if js:
            pg.keyboard.press("Tab")
            busy_done(pg)
    if js:
        pg.reload()
        sl.settle(pg, js)
    else:
        with pg.expect_navigation():
            pg.click(f"{sc} button.ui-btn-primary[value=update]")
        sl.settle(pg, js)


def val(pg, sc, name):
    loc = pg.locator(f"{sc} [name={name}]")
    return loc.input_value() if loc.count() else None


def view_checks(pg, tag, js, w):
    sc = open_window(pg, js, "process")
    pressed = pg.eval_on_selector_all(
        f"{sc} button[name=f_sprache]", "bs => bs.map(b => [b.id, b.getAttribute('aria-pressed')])"
    )
    rep.check(
        pressed
        == [
            ["schema-tab-lang-htx-process-ru", "true"],
            ["schema-tab-lang-htx-process-en", "false"],
        ],
        f"{tag}: кнопки языка шагов — свой ns, ru выбран ({pressed})",
    )
    legend = pg.locator(f"{sc} fieldset legend").first.inner_html()
    rep.check(
        ' · <span lang="de">„Wählen“</span>' in legend,
        f"{tag}: legend «Schritt 1 · „Wählen“» с lang ({legend[:80]!r})",
    )
    label = pg.locator(f"{sc} label[for='schema-f-htx_process_0_title-ru']").inner_text()
    rep.check(
        " – " in label and "„" not in label and label.endswith("(Русский)"),
        f"{tag}: короткая подпись поля перевода ({label!r})",
    )
    rep.check(
        pg.locator(f"{sc} #schema-f-htx_process_0_title-ru").get_attribute("maxlength") == "120"
        and pg.locator(f"{sc} #schema-f-htx_process_0_text-ru").get_attribute("maxlength")
        == "2000",
        f"{tag}: maxlength 120/2000",
    )
    rep.check(
        val(pg, sc, "f_tr_htx_process_0_title_ru") == "Выбор товара"
        and pg.locator(f"{sc} #schema-f-htx_process_0_title-en").is_hidden(),
        f"{tag}: перевод ru на месте, поле en скрыто",
    )
    rep.check(
        pg.locator(f"{sc} [name^=f_tr_htx_process_2_]").count() == 0,
        f"{tag}: пустой пункт «neu» — без полей перевода",
    )
    ids = pg.evaluate(
        "[...document.querySelectorAll('[id]')].map(e => e.id)"
        ".filter((x, i, a) => a.indexOf(x) !== i)"
    )
    rep.check(not ids, f"{tag}: id в окне уникальны ({ids[:3]})")
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' button[name=f_sprache]')]
           .filter(e => e.offsetParent && e.getBoundingClientRect().height < 43.5).length""",
        sc,
    )
    rep.check(small == 0, f"{tag}: кнопки языка ≥ 44 px")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{tag}: без гор. прокрутки ({over}px)", code="overflow")
    sl.a11y_check(rep, pg, tag, scope=sc, minimum=44)
    sl.shot(pg, OUT, f"t6_process_{tag.replace(' ', '_')}")
    sc = open_window(pg, js, "team")
    rep.check(
        val(pg, sc, "f_tr_htx_team_0_role_ru") == "Шеф"
        and val(pg, sc, "f_tr_htx_team_1_role_ru") == "Пекарь",
        f"{tag}: две «Anna» — у каждой своё поле роли",
    )
    hint = pg.locator(f"{sc} #schema-f-htx_team_0_name-nt")
    rep.check(
        hint.count() == 1
        and hint.inner_text() in ("Name wird nicht übersetzt.", "Имя не переводится.")
        and pg.locator(f"{sc} [name^=f_tr_htx_team_0_name]").count() == 0,
        f"{tag}: имя не переводится, подсказка у поля",
    )
    sl.shot(pg, OUT, f"t6_team_{tag.replace(' ', '_')}")


def edit_flow(pg, tag, js):
    sc = open_window(pg, js, "process")
    if not js:
        # перестановка обменом полей (как владелец без кнопок ↑/↓)
        apply(
            pg,
            js,
            sc,
            {
                "f_htx_process_0_title": "Abholen",
                "f_htx_process_0_text": "Im Laden",
                "f_htx_process_1_title": "Wählen",
                "f_htx_process_1_text": "Online",
            },
        )
        sc = scope_of(js)
        got = [val(pg, sc, f"f_tr_htx_process_{i}_title_ru") for i in (0, 1)]
        rep.check(got == ["Забрать", "Выбор товара"], f"{tag}: переводы едут за шагом ({got})")
        first = 1  # «Wählen» теперь второй
    else:
        first = 0
    apply(
        pg,
        js,
        sc,
        {
            f"f_htx_process_{first}_title": "Aussuchen",
            f"f_tr_htx_process_{first}_title_ru": "Подобрать",
        },
    )
    sc = scope_of(js)
    rep.check(
        val(pg, sc, f"f_tr_htx_process_{first}_title_ru") == "Подобрать",
        f"{tag}: правка немецкого и перевод в одной форме — введённое осталось",
    )
    if js:
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
    with pg.expect_navigation():
        pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    raw = shell(READ)
    data = json.loads(raw.split("JSON", 1)[1]) if "JSON" in raw else {}
    want_de = (
        ["Abholen", "Aussuchen"] if not js else ["Aussuchen", "Abholen"]
    )  # без JS — переставлены
    rep.check(
        [p["title"] for p in data.get("de") or []] == want_de,
        f"{tag}: сохранено по-немецки {[p['title'] for p in data.get('de') or []]}",
    )
    ru = {p["title"]: p.get("text") for p in data.get("ru") or []}
    rep.check(
        ru.get("Подобрать") == "Онлайн" and ru.get("Забрать") == "В магазине",
        f"{tag}: Студия (localize ru) видит переводы окна ({ru})",
    )
    storefront(pg, tag)


def storefront(pg, tag):
    for lang, want, unwanted in (
        ("ru", ["Подобрать", "Забрать", "Шеф", "Супер!"], ["Aussuchen"]),
        ("de", ["Aussuchen", "Abholen", "Chefin"], ["Подобрать"]),
    ):
        pg.goto(f"{U}/lang/?lang={lang}&next=/")
        pg.wait_for_load_state()
        html = pg.content()
        got = [w for w in want if w in html]
        bad = [w for w in unwanted if w in html]
        rep.check(got == want and not bad, f"{tag}: витрина {lang} — {got}, лишнее {bad}")
        sl.shot(pg, OUT, f"t6_store_{lang}_{tag.replace(' ', '_')}", full=True)


def negative(pg, tag):
    """Негативный контроль: перевод шага снят — витрина ru показывает немецкий."""
    shell(
        SETUP.replace(
            '"process": [{"title": "Выбор товара", "text": "Онлайн"}, ',
            '"process": [{}, ',
        )
    )
    pg.goto(f"{U}/lang/?lang=ru&next=/")
    pg.wait_for_load_state()
    html = pg.content()
    rep.check(
        "Wählen" in html and "Выбор товара" not in html and "Забрать" in html,
        f"{tag}: негативный контроль — шаг без перевода на ru по-немецки",
    )
    rep.check(
        'lang="de">Wählen' in html and 'lang="de">Забрать' not in html,
        f'{tag}: витрина ru — у шага без перевода lang="de" (a11y №14), у переведённого нет',
    )


with sl.launch() as browser:
    combos = list(sl.matrix()) + [(320, 640, "de", True)]
    for w, h, lang, js in combos:
        if not setup():
            rep.check(False, "setup")
            break
        pg = sl.open_page(browser, w, h, js=js, lang=lang, url=U)
        tag = f"{w} {lang} {'js' if js else 'nojs'}"
        if rep.check(sl.login(pg, U, EMAIL, PASSWORD), f"{tag}: вход"):
            view_checks(pg, tag, js, w)
            if w >= 1000 and lang == "de":
                edit_flow(pg, tag, js)
                negative(pg, tag)
            rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
        pg.context.close()
rep.finish("T6 Schritte/Team/Stimmen")
