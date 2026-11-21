"""T-13.4: общий каркас Playwright-стендов (`scripts/*_stand.py`).

Каждый стенд раньше заново писал запуск Chromium, вход, счётчик ✓/✗ и размеры экранов — и
заново наступал на те же грабли (кабинет по-английски, вечное ожидание бесконечной анимации,
`playwright install`). Здесь это одно место: `Report`, `SIZES`/`LANGS`/`JS_MODES`, `launch`,
`open_page`, `login`, `settle`, `overflow`, `shot`, `matrix`.

Правило: **новые стенды — только через каркас; старые переносим при следующей правке**
(замок — `apps/core/tests/test_standlib.py`, список `LEGACY_STANDS` можно только сокращать).

Запуск стенда (тенант `ptx` ставит `scripts/text_pages_stand.py --setup`, один раз):

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand --noreload
    uv run --no-project --with playwright python scripts/<имя>_stand.py <папка-скриншотов>
    uv run --no-project --with playwright python scripts/standlib.py --selftest

Сервер на другом порту или хосте — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Chromium —
`/opt/pw-browsers/chromium` (`playwright install` не запускать). В CI стенды не входят (там нет
браузера); `--selftest` проверяет сам каркас без сервера и БД — гонять после правки каркаса.

Новый стенд (лежит в `scripts/`, поэтому `import standlib` работает без установки):

    import sys

    import standlib as sl

    rep = sl.Report()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            page = sl.open_page(browser, w, h, js=js, lang=lang)
            tag = f"{w} {lang} {'js' if js else 'nojs'}"
            if rep.check(sl.login(page, sl.BASE_URL, sl.EMAIL, sl.PASSWORD), f"{tag}: вход"):
                resp = page.goto(sl.BASE_URL + "/dashboard/site/aufbau/")
                sl.settle(page, js, rep)
                rep.check(resp.status < 400, f"{tag}: ответ {resp.status}", code="status")
                over = sl.overflow(page)
                rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
                rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
                sl.shot(page, sys.argv[1], f"aufbau_{w}_{lang}_{'js' if js else 'nojs'}")
            page.context.close()
    rep.finish()

Проверки вести по data-атрибутам, а не по тексту; после клика ждать результат
(`wait_for_selector`), а не загрузку. Остальные грабли — скилл `sa-stand`.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from itertools import product

# playwright импортируется лениво, внутри `launch`: замок каркаса (`test_standlib.py`) и CI
# грузят модуль там, где пакета нет.

CHROME = "/opt/pw-browsers/chromium"
BASE_DOMAIN = "siteadaptor.de"
#: адрес тенанта стенда; другой порт/хост — переменной `STAND_URL`
BASE_URL = os.environ.get("STAND_URL", f"http://ptx.{BASE_DOMAIN}:8000").rstrip("/")
#: владелец тенанта `ptx` (`scripts/text_pages_stand.py --setup`)
EMAIL = "owner@ptx.test"
PASSWORD = "Stand-Passwort-123"
#: приёмка вёрстки: компьютер и телефон
SIZES = ((1440, 900), (390, 844))
LANGS = ("de", "ru")
#: сначала без JS (обязательный проход), затем с JS
JS_MODES = (False, True)
LANGUAGE_COOKIE = "django_language"  # settings.LANGUAGE_COOKIE_NAME (умолчание Django)
LOGIN_PATH = "/accounts/login/"


class Report:
    """Счёт ✓/✗. Повтор того же дефекта (подпись `sigs`) печатается один раз, в сводке —
    с числом; `code` — код проверки, давшей ✗ (замки сверяют коды, не текст)."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet  # большой обход: ✓ не печатать
        self.ok = 0
        self.fail: list[str] = []
        self.sigs: dict[str, list] = {}  # подпись дефекта → [число, первый пример]
        self.notes: dict[str, int] = {}
        self.codes: list[str] = []

    def check(self, cond, label, *, sigs=None, code="other", quiet=None) -> bool:
        """`sigs` — подпись дефекта (строка или список); без неё подписью служит `label`."""
        if cond:
            self.ok += 1
            if not (self.quiet if quiet is None else quiet):
                print("  ✓ " + label)
            return True
        self.fail.append(label)
        self.codes.append(code)
        if sigs is None:
            sigs = [label]
        elif isinstance(sigs, str):
            sigs = [sigs]
        new = False
        for sig in sigs:
            seen = self.sigs.setdefault(sig, [0, label])
            seen[0] += 1
            new = new or seen[0] == 1
        if new:
            print("  ✗ " + label)
        return False

    def note(self, sig) -> None:
        """Наблюдение (не ✗): печатается один раз, в сводке — с числом."""
        self.notes[sig] = self.notes.get(sig, 0) + 1
        if self.notes[sig] == 1:
            print("  · " + sig)

    @property
    def exit_code(self) -> int:
        return 1 if self.fail else 0

    def summary(self, title: str = "") -> str:
        """Печатает наблюдения, сводку дефектов и итоговую строку; возвращает итоговую строку."""
        if self.notes:
            print(f"\nнаблюдения ({len(self.notes)}):")
            for sig, n in sorted(self.notes.items(), key=lambda kv: -kv[1]):
                print(f"  ×{n:<4} {sig}")
        if self.sigs:
            print(f"\nсводка дефектов ({len(self.sigs)} разных):")
            for sig, (n, first) in sorted(self.sigs.items(), key=lambda kv: -kv[1][0]):
                print(f"  ×{n:<4} {sig}")
                if first != sig:
                    print(f"         напр.: {first[:220]}")
        line = f"{title + ': ' if title else ''}{self.ok} ✓, {len(self.fail)} ✗"
        print("\n" + line)
        return line

    def finish(self, title: str = "") -> None:
        """Сводка и выход: есть ✗ → код 1."""
        self.summary(title)
        sys.exit(self.exit_code)


def matrix(sizes=SIZES, langs=LANGS, js_modes=JS_MODES):
    """Сочетания обхода `(ширина, высота, язык, js)`: режим JS — внешний цикл (проход)."""
    for js, (w, h), lang in product(js_modes, sizes, langs):
        yield w, h, lang, js


@contextlib.contextmanager
def launch(**kwargs):
    """Chromium стенда: `/opt/pw-browsers/chromium`, если он есть (версия браузера там не
    совпадает с пакетом — путь задаём сами; `playwright install` не запускать). Поддомены
    `*.siteadaptor.de` ведут на 127.0.0.1."""
    from playwright.sync_api import sync_playwright

    if os.path.exists(CHROME):
        kwargs.setdefault("executable_path", CHROME)
    kwargs.setdefault("args", [f"--host-resolver-rules=MAP *.{BASE_DOMAIN} 127.0.0.1"])
    with sync_playwright() as p:
        browser = p.chromium.launch(**kwargs)
        try:
            yield browser
        finally:
            browser.close()


def open_page(browser, width, height, *, js=True, lang="de", url=None):
    """Страница в своём контексте: размер, JS вкл/выкл, язык. Язык — и `locale`, и кука
    `django_language` (кабинет на стенде иначе открывается по-английски). Ошибки страницы
    копятся в `page.js_errors`. Закрывать — `page.context.close()`."""
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        locale=f"{lang}-DE",
        java_script_enabled=js,
        device_scale_factor=1,
    )
    ctx.add_cookies([{"name": LANGUAGE_COOKIE, "value": lang, "url": url or BASE_URL}])
    page = ctx.new_page()
    page.js_errors = []
    page.on("pageerror", lambda e: page.js_errors.append(str(e)[:160]))
    return page


def login(page, url, email, password) -> bool:
    """Вход владельца (allauth); `True` — ушли со страницы входа."""
    page.goto(url.rstrip("/") + LOGIN_PATH)
    page.fill("input[name=login]", email)
    page.fill("input[name=password]", password)
    with page.expect_navigation():  # ответ на POST, а не «загрузка» прежней страницы
        page.click("button[type=submit]")
    page.wait_for_load_state()
    return LOGIN_PATH not in page.url


#: нет идущих КОНЕЧНЫХ анимаций (бесконечные — слайдер, бегущая строка — не ждём)
_NO_FINITE_ANIMATIONS = (
    "!document.getAnimations().filter(a => a.effect && "
    "a.effect.getTiming().iterations !== Infinity && a.playState === 'running').length"
)


def settle(page, js, rep: Report | None = None) -> bool:
    """С JS: страница загружена и закончились конечные анимации (открытие окна — 160 мс).
    Не `networkidle`: кадр предпросмотра держит сеть. Таймаут — не сбой стенда, а наблюдение
    (`rep.note`), замер идёт по текущему состоянию; `False` — не дождались."""
    if not js:
        return True
    try:
        page.wait_for_load_state("load", timeout=10000)
        page.wait_for_function(_NO_FINITE_ANIMATIONS, timeout=5000)
    except Exception:  # noqa: BLE001 — таймаут Playwright; пакет импортируется лениво
        if rep is not None:
            rep.note("settle timeout: страница не успокоилась (load/анимации) — замер как есть")
        return False
    return True


def overflow(page) -> int:
    """Горизонтальный скролл страницы в px (≤ 0 — нет). Работает и без JS на странице."""
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def shot(page, out_dir, name, *, full=False) -> str:
    """Скриншот `<out_dir>/<name>.png`; папка создаётся."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name if name.endswith(".png") else name + ".png")
    page.screenshot(path=path, full_page=full)
    return path


# --- замок каркаса: страницы через set_content, без сервера и БД --------------------------

_HEAD = '<!doctype html><html><meta name=viewport content="width=device-width">'
#: скрипт ставит метку; конечная анимация 300 мс и бесконечная (её settle ждать не должен)
_GOOD = (
    _HEAD + "<style>@keyframes a{from{opacity:.2}to{opacity:1}}"
    "#fin{animation:a .3s linear 1}#inf{animation:a 1s linear infinite}</style>"
    '<body style="margin:0"><main><p id="fin">Конечная</p><p id="inf">Бесконечная</p></main>'
    "<script>document.documentElement.setAttribute('data-js', '1')</script></body></html>"
)
_WIDE = _GOOD.replace("<main>", '<main><div style="width:800px">широкая полоса</div>')
_BOOM = _GOOD.replace("</script>", ";throw new Error('selftest-boom')</script>")
_LOGIN_FORM = (
    _HEAD + '<body><form method="post"><input name="login"><input name="password" '
    'type="password"><button type="submit">Anmelden</button></form></body></html>'
)
_SELF_URL = "http://selftest.local"
_HAS_JS = "document.documentElement.getAttribute('data-js') === '1'"
_FINITE_RUNNING = "document.getAnimations().some(a => a.effect.getTiming().iterations === 1)"


def _fake_login(page, accept: bool) -> dict:
    """Вход без сервера: страницу входа и ответ на POST отдаёт маршрут. Перенаправление из
    маршрута браузер повёл бы в сеть, поэтому «принят/отклонён» задаёт адрес формы."""
    seen = {}
    action = "/dashboard/" if accept else LOGIN_PATH
    form = _LOGIN_FORM.replace('method="post"', f'method="post" action="{action}"')

    def serve(route):
        if route.request.method == "POST":
            seen["post"] = route.request.post_data or ""
            body = _GOOD if accept else form
        else:
            body = form
        route.fulfill(status=200, body=body, content_type="text/html; charset=utf-8")

    page.route(_SELF_URL + "/**", serve)
    return seen


def _selftest_report(lock: Report) -> None:
    """`Report`: счёт, коды, повтор подписи — одна строка, сводка и код выхода."""
    rep = Report()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rep.check(True, "хорошо")
        rep.check(False, "плохо А", sigs="один дефект", code="x")
        rep.check(False, "плохо Б", sigs="один дефект", code="x")
        rep.note("наблюдение")
        rep.note("наблюдение")
        line = rep.summary("проба")
    out = buf.getvalue()
    lock.check((rep.ok, len(rep.fail)) == (1, 2), "Report: счёт 1 ✓ и 2 ✗")
    lock.check(rep.codes == ["x", "x"] and rep.exit_code == 1, "Report: коды ✗ и код выхода 1")
    lock.check(
        out.count("  ✗ ") == 1 and out.count("  · ") == 1,
        "Report: повтор подписи и наблюдения печатается один раз",
    )
    lock.check(
        line == "проба: 1 ✓, 2 ✗" and "×2    один дефект" in out,
        f"Report: сводка с числом повторов и итоговая строка ({line!r})",
    )
    lock.check(Report().exit_code == 0, "Report: без ✗ код выхода 0")


def selftest() -> None:
    """Каркас на заведомо хороших и сломанных страницах; сломанный каркас → ✗ и код 1."""
    lock = Report()
    _selftest_report(lock)
    combos = list(matrix())
    lock.check(
        len(combos) == 8 and len(set(combos)) == 8 and not combos[0][3],
        f"matrix: 2 размера × 2 языка × 2 режима = 8 сочетаний, первым — без JS ({len(combos)})",
    )
    with launch() as browser:
        print("— хорошая страница (390, ru, с JS)")
        good = Report(quiet=True)
        page = open_page(browser, 390, 844, js=True, lang="ru", url=_SELF_URL)
        page.set_content(_GOOD)
        lock.check(page.evaluate(_FINITE_RUNNING), "до settle идёт конечная анимация")
        calm = settle(page, True, good)
        lock.check(
            calm and not good.notes and not page.evaluate(_FINITE_RUNNING),
            "settle: дождался конечной анимации, бесконечную не ждал",
        )
        good.check(overflow(page) <= 0, "без гор. скролла", code="overflow")
        good.check(not page.js_errors, "без ошибок JS", code="jserror")
        lock.check(good.ok == 2 and not good.fail, f"хорошая страница: 0 ✗ ({good.fail})")
        lock.check(page.evaluate(_HAS_JS), "с JS скрипт страницы исполнился")
        lock.check(
            page.evaluate("[window.innerWidth, window.innerHeight]") == [390, 844],
            "open_page: размер окна 390×844",
        )
        cookies = {c["name"]: c["value"] for c in page.context.cookies(_SELF_URL)}
        lock.check(
            page.evaluate("navigator.language") == "ru-DE" and cookies == {LANGUAGE_COOKIE: "ru"},
            f"open_page: язык ru — locale и кука {LANGUAGE_COOKIE} ({cookies})",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = shot(page, os.path.join(tmp, "новая"), "good")
            lock.check(
                path.endswith("good.png") and os.path.getsize(path) > 500,
                "shot: скриншот записан, папка создана",
            )
        page.context.close()

        print("— переполнение по ширине")
        for w, h in SIZES:
            page = open_page(browser, w, h, url=_SELF_URL)
            page.set_content(_WIDE)
            over = overflow(page)
            want = 800 - w
            lock.check(
                over == want if want > 0 else over <= 0,
                f"overflow: полоса 800px при {w} → {over}px ({'ловится' if want > 0 else 'нет'})",
            )
            page.context.close()

        print("— без JS")
        page = open_page(browser, 390, 844, js=False, url=_SELF_URL)
        page.set_content(_GOOD)
        lock.check(not page.evaluate(_HAS_JS), "без JS скрипт страницы не исполнился")
        lock.check(settle(page, False), "settle: без JS не ждёт")
        page.set_content(_WIDE)
        lock.check(overflow(page) == 410, "overflow меряет и без JS (410px)")
        page.context.close()

        print("— ошибка JS")
        page = open_page(browser, 1440, 900, url=_SELF_URL)
        page.set_content(_BOOM)
        settle(page, True)
        page.wait_for_timeout(100)
        lock.check(
            any("selftest-boom" in e for e in page.js_errors),
            f"open_page: ошибка страницы попала в js_errors ({page.js_errors})",
        )
        page.context.close()

        print("— вход")
        for want in (True, False):
            page = open_page(browser, 1440, 900, url=_SELF_URL)
            seen = _fake_login(page, accept=want)
            got = login(page, _SELF_URL, EMAIL, PASSWORD)
            lock.check(
                got is want and seen.get("post") == f"login=owner%40ptx.test&password={PASSWORD}",
                f"login: вход {'принят' if want else 'отклонён'} → {got} ({page.url})",
            )
            page.context.close()
    lock.finish("standlib selftest")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        selftest()
    else:
        sys.exit(__doc__)
