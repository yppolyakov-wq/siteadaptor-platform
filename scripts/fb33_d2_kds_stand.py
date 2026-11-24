"""FB-33 D2: стенд кухонной доски (KDS) при переполнении — 1440×900 и 390×844, de и ru, с JS
и без.

План — `docs/fb33-stack13-plan-2026-11-24.md` §5 «Стенды» (D2) и правка ревью §10.1 M6. Кит
`restaurant-demo` получает в `--setup` не меньше `KDS_MAX_ORDERS + 2` активных заказов (ORM,
только стенд-БД). Проверки на каждой странице доски:
- на доске ровно `KDS_MAX_ORDERS` карточек (формы действий в `#kds-board`);
- строка переполнения `[data-kds-more]` — обычный абзац (без `role="status"`/`aria-live`: доска
  пересоздаётся поллингом, ревью §10.4) внутри `#kds-board`, видна, с числом скрытых заказов
  текстом и обычной ссылкой `#kds-more-link` «Bestellliste öffnen» на «Verkäufe» (вкладка
  заказов списком; имя = видимый текст, число — не в ссылке);
- ссылка ≥ 44 px по высоте, нет горизонтальной прокрутки (390 — главное);
- ru — без немецкой строки; без ошибок JS; `a11y_check` (кабинет — 44);
- с JS: поллинг HTMX (каждые 8 с) заменяет доску целиком — после замены строка и ссылка на
  месте (узел новый: метка старого узла пропала); фокус на ссылке и на кнопке действия
  (`kds-act-<pk>`) переживает замену (htmx возвращает его по `id`); переход по ссылке — список;
- негативный контроль: на главной кабинета (200) строки нет, и проверка строки отвечает «нет».

`a11y_check` с ✗ — по строке переполнения (`[data-kds-more]`, новое в D2); по всей доске —
наблюдениями (контраст и высота кнопок карточек — прежний долг, не этого среза).

Запуск (стенд-БД — копия `platform_m39_stand`; вход `restaurant-demo@example.com`):
    DB_NAME=<стенд-БД> uv run python scripts/fb33_d2_kds_stand.py --setup
    REDIS_CACHE_URL=redis://localhost:6379/13 DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 \\
        uv run python manage.py runserver 0.0.0.0:8063 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8063 \\
        uv run --with playwright==1.55.0 python scripts/fb33_d2_kds_stand.py <папка>
Обход только читает (кнопки доски не нажимает). Итог: «N ✓, M ✗». Не входит в CI.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from urllib.parse import urlparse

import standlib as sl

KIT = "restaurant-demo"
EMAIL = f"{KIT}@example.com"
DEMO_PASSWORD = "demo-12345678"
PORT = urlparse(sl.BASE_URL).port or 80
BASE = f"http://{KIT}.{sl.BASE_DOMAIN}:{PORT}"
BOARD = "/dashboard/orders/kitchen/"
CONTROL = "/dashboard/"
LIMIT = 48  # apps.orders.views.KDS_MAX_ORDERS
#: сколько активных заказов ставит `--setup` (переполнение на два)
WANT = LIMIT + 2
#: поллинг доски — каждые 8 с (`templates/orders/kitchen.html`); ждём с запасом
POLL_WAIT_MS = 10_000
SALES_LIST = "/dashboard/verkaeufe/?tab=order&view=liste"
LINK_NAME = {"de": "Bestellliste öffnen", "ru": "Открыть список заказов"}
GERMAN_IN_RU = ("weitere offene", "Bestellliste", "nicht angezeigt", "davon")

SETUP = f"""
from django.utils import timezone
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant

tenant = Tenant.objects.get(slug={KIT!r})
tenant.enabled_locales = sorted(set(tenant.enabled_locales or []) | {{"de", "ru"}})
tenant.save(update_fields=["enabled_locales"])
with schema_context(tenant.schema_name):
    from apps.catalog.models import Product
    from apps.orders import services
    from apps.orders.models import Order

    active = Order.objects.filter(status__in=(Order.STATUS_NEW, Order.STATUS_CONFIRMED))
    product = Product.objects.filter(is_active=True).first()
    made = 0
    while active.count() < {WANT}:
        services.create_order(items=[(product, 1)], name=f"D2 Stand {{made + 1}}")
        made += 1
    print("READY", tenant.slug, "active", active.count(), "made", made)
"""


def setup() -> None:
    if not os.environ.get("DB_NAME", "").endswith("_stand"):
        sys.exit("--setup пишет в БД: только стенд-БД (DB_NAME=…_stand)")
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
        capture_output=True,
        text=True,
        check=False,
    )
    print((out.stdout + out.stderr)[-1500:])
    if out.returncode or "READY" not in out.stdout:
        sys.exit(1)


STATE_JS = """() => {
  const board = document.querySelector('#kds-board');
  const more = board && board.querySelector('[data-kds-more]');
  const link = more && more.querySelector('a[href]');
  const box = link && link.getBoundingClientRect();
  return {
    board: !!board,
    cards: board ? board.querySelectorAll('form').length : 0,
    more: !!more,
    role: more ? more.getAttribute('role') : null,
    live: board ? board.querySelectorAll('[aria-live], [role=status], [role=alert]').length : 0,
    linkId: link ? link.id : '',
    focused: document.activeElement ? document.activeElement.id : '',
    visible: !!(more && more.offsetParent !== null),
    text: more ? more.innerText.trim() : '',
    href: link ? link.getAttribute('href') : null,
    linkText: link ? link.innerText.trim() : '',
    ariaLabel: link ? link.getAttribute('aria-label') : null,
    linkHeight: box ? Math.round(box.height) : 0,
    marked: !!(more && more.__d2mark),
  };
}"""


def board_state(page) -> dict:
    return page.evaluate(STATE_JS)


def status_ok(state: dict) -> bool:
    """Строка переполнения на месте: внутри доски, обычный абзац (без live region), видна,
    со ссылкой `#kds-more-link`."""
    return bool(
        state["more"]
        and state["role"] is None
        and not state["live"]
        and state["visible"]
        and state["href"]
        and state["linkId"] == "kds-more-link"
    )


def check_board(rep, page, tag, lang) -> dict:
    state = board_state(page)
    rep.check(state["board"], f"{tag}: доска #kds-board есть", code="board")
    rep.check(state["cards"] == LIMIT, f"{tag}: карточек {state['cards']} = {LIMIT}", code="limit")
    rep.check(status_ok(state), f"{tag}: строка переполнения со ссылкой ({state})", code="more")
    rep.check(state["href"] == SALES_LIST, f"{tag}: ссылка на Verkäufe ({state['href']})")
    rep.check(
        state["linkText"] and state["ariaLabel"] is None and state["linkText"] in state["text"],
        f"{tag}: имя ссылки = видимый текст ({state['linkText']!r})",
        code="name",
    )
    rep.check(
        state["linkText"] == LINK_NAME[lang], f"{tag}: имя ссылки «{LINK_NAME[lang]}»", code="name"
    )
    before = state["text"].split(state["linkText"])[0] if state["linkText"] else state["text"]
    rep.check(
        any(ch.isdigit() for ch in before) and not any(ch.isdigit() for ch in state["linkText"]),
        f"{tag}: число скрытых — текстом перед ссылкой ({state['text']!r})",
        code="count",
    )
    rep.check(state["linkHeight"] >= 44, f"{tag}: ссылка {state['linkHeight']}px ≥ 44", code="tgt")
    over = sl.overflow(page)
    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
    if lang == "ru":
        german = [g for g in GERMAN_IN_RU if g in state["text"]]
        rep.check(not german, f"{tag}: ru без немецкого ({german})", code="german")
    return state


def walk(out_dir) -> None:
    rep = sl.Report()
    with sl.launch() as browser:
        # прогрев сервера: первые запросы свежего runserver дают ложные 400 входа
        warm = sl.open_page(browser, *sl.SIZES[0], js=False, lang="de")
        sl.login(warm, BASE, EMAIL, DEMO_PASSWORD)
        warm.context.close()
        for w, h, lang, js in sl.matrix():
            page = sl.open_page(browser, w, h, js=js, lang=lang)
            tag = f"{w} {lang} {'js' if js else 'nojs'}"
            try:
                if not rep.check(sl.login(page, BASE, EMAIL, DEMO_PASSWORD), f"{tag}: вход"):
                    continue
                resp = page.goto(BASE + BOARD)
                sl.settle(page, js, rep)
                rep.check(resp.status == 200, f"{tag}: доска {resp.status}", code="status")
                check_board(rep, page, tag, lang)
                rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
                sl.a11y_check(rep, page, tag, scope="[data-kds-more]", minimum=44)
                board_a11y = sl.Report(quiet=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sl.a11y_check(board_a11y, page, tag, scope="#kds-board", minimum=44)
                for sig in board_a11y.sigs:
                    rep.note(f"доска (прежнее): {sig}")
                sl.shot(page, out_dir, f"kds_{w}_{lang}_{'js' if js else 'nojs'}")
                if js:
                    page.evaluate(
                        "() => { document.querySelector('[data-kds-more]').__d2mark = 1; }"
                    )
                    page.wait_for_timeout(POLL_WAIT_MS)
                    after = board_state(page)
                    rep.check(not after["marked"], f"{tag}: поллинг заменил доску", code="poll")
                    rep.check(
                        status_ok(after) and after["cards"] == LIMIT,
                        f"{tag}: после поллинга строка и ссылка на месте ({after})",
                        code="poll-keep",
                    )
                    rep.check(not page.js_errors, f"{tag}: без ошибок JS после поллинга")
                    for target in ("#kds-more-link", "[id^=kds-act-]"):
                        page.focus(target)
                        want = page.evaluate("() => document.activeElement.id")
                        page.evaluate(
                            "() => { document.querySelector('#kds-board').__d2mark = 1; }"
                        )
                        page.wait_for_timeout(POLL_WAIT_MS)
                        after = board_state(page)
                        replaced = page.evaluate(
                            "() => !document.querySelector('#kds-board').__d2mark"
                        )
                        rep.check(
                            replaced and want and after["focused"] == want,
                            f"{tag}: фокус на {want} пережил поллинг ({after['focused']!r})",
                            code="focus",
                        )
                    if w == sl.SIZES[0][0] and lang == "de":
                        page.click("[data-kds-more] a[href]")
                        page.wait_for_load_state("load")
                        rep.check(
                            "/dashboard/verkaeufe" in page.url,
                            f"{tag}: ссылка ведёт в список ({page.url})",
                            code="nav",
                        )
                # негативный контроль: на главной кабинета строки нет — проверка отвечает «нет»
                resp = page.goto(BASE + CONTROL)
                rep.check(
                    resp.status == 200 and not status_ok(board_state(page)),
                    f"{tag}: контроль — на главной ({resp.status}) строки нет",
                    code="control",
                )
            finally:
                page.context.close()
    rep.finish()


def main() -> None:
    argv = sys.argv[1:]
    if "--setup" in argv:
        setup()
    elif argv:
        walk(argv[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
