"""FB-33 M5d-0: инвентаризация «у какого блока есть окно» — тип бизнеса × код страницы × ref.

Источник истины — то, что видит владелец: для каждой строки экрана «Seitenaufbau» скрипт
открывает ту же вьюху (`site-schema`, `?seite=<код>&block=<ref>`) через `django.test.Client`
под владельцем бизнеса и читает окно из разметки панели `[data-schema-panel]`:

- **окно есть** — в панели есть кнопка `window_done` («Fertig» окна). Это тот же признак, по
  которому `static/js/aufbau.js` (`aufbauWindowWanted`) открывает `<dialog>`, а стенд владельца
  (`scripts/fb33_m3_9_owner_stand.py`, `_WANTS_WINDOW`) ставит заметку «блок без вкладок —
  панель колонкой, без <dialog>»; `window_done` рисуется только при непустом
  `block_window.tabs(...)` (`templates/tenant/_block_window.html`);
- **вкладки окна** — ключи разделов `section[data-window-tab]` панели (у окна с одной вкладкой
  ссылок `data-window-tab-link` нет, раздел есть всегда).

Считать по `blocks_for` + `block_window.tabs` без вьюхи нельзя: вкладки зависят от декораторов
вьюхи (`apps/core/site_schema_views.py`: `page_window`, `window_parts`, `block_views`, …) —
так окна FAQ объекта и плашек выпали бы (план стопки 10, §8.1 A-H4). Своего списка видов блоков
скрипт не держит (замок `apps/core/tests/test_fb33_m5d_inventory.py`).

Перечень страниц и строк — как у стенда владельца: `site_schema.type_groups`, первый объект
каждого `OBJECT_KINDS` (строка «Nur diese Seite»), строки `blocks_for` без общих блоков схемы
объекта (`shared`: пунктиром, окна нет) и строка «Einstellungen der Seite», где её ставит
`site_schema.page_row_ref`. Совпадение с `DUMP` стенда — тоже замок.

Страница или окно, которые не построились (исключение, `SchemaError`, ответ не 200, панель
без выбранного блока), — строкой «пропущено: причина», не молча.

Группы плана M5d (по хосту страницы; модуль разделов —
`detail_parts.module_of(detail_parts.shared_host(host))`, проверка сверху вниз):

- **G4** — оформление и подтверждение: модуль `cart` или `confirmation`;
- **G3** — текстовые страницы («Über uns», «Versand», своя «Seite»): тип страницы
  `site_schema.TEXT`;
- **G2** — страницы-формы одной строкой: у модуля ровно один раздел в
  `detail_sections.DETAIL_SECTIONS` (message, anfrage, gift, loyalty, finder, teachers,
  event_calendar, passes, booking_slots; у `anfrage` окно есть — строка «с окном»);
- **G1** — детали объектов: любой другой модуль разделов (товар, услуга, номер, событие или
  тур, набор, акция, запись блога; и хост одного объекта — через общий хост);
- **—** — остальное (главная, листинги, категории, группы акций): не входит в M5d.

Скрипт только читает. Вход — сессией в кэше (Redis, `SESSION_ENGINE` cache) без
`force_login`: сигнал входа писал бы `last_login` и строку аудита. Каждый SQL-запрос на запись
(INSERT/UPDATE/DELETE/…) во время прогона отбивается (`connection.execute_wrapper`) — строка
становится «пропущено: запись в БД».

    DB_NAME=platform_m5d_stand uv run python scripts/fb33_m5d_inventory.py \\
        [--only shop,hotel] [--json out.json]

`--only` — поддомены китов (shop, restaurant-demo, friseur, hotel, retreat); по умолчанию — пять
китов стенда владельца. В stdout — markdown: таблица по виду блока (`key`) и итог
«N видов без окна / M с окном», группы G1–G4, пропуски; `--json` — полная таблица строк.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUFBAU = "/dashboard/site/aufbau/"
#: поддомены пяти китов стенда владельца (`fb33_m3_9_owner_stand.KITS` → `kit_slugs`)
DEFAULT_SLUGS = ("shop", "restaurant-demo", "friseur", "hotel", "retreat")
#: модули разделов группы G4 (имена реестра `detail_sections.DETAIL_SECTIONS`, не ключи блоков)
CHECKOUT_MODULES = frozenset({"cart", "confirmation"})
NO_GROUP = "—"
GROUP_NAMES = {
    "G1": "детали объектов",
    "G2": "страницы-формы одной строкой",
    "G3": "текстовые страницы",
    "G4": "корзина и подтверждение",
    NO_GROUP: "главная, листинги, категории (вне M5d)",
}

_PANEL = re.compile(r"<aside\b[^>]*\bdata-schema-panel\b.*?</aside>", re.S)
_TAB = re.compile(r"<section\b[^>]*\bdata-window-tab=\"([^\"]+)\"")
_WINDOW_DONE = 'value="window_done"'
_SELECTED = "data-schema-done"  # «Fertig» панели — только при выбранном блоке
#: id объекта в коде строки — как `_num_free` стенда владельца
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}|[0-9a-f]{32}")
_WRITE_SQL = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP)\b", re.I)


class SkipError(Exception):
    """Страница или окно не построились — строка «пропущено: причина»."""


# --- что видит владелец -------------------------------------------------------------------


def window_tabs(html: str) -> list[str] | None:
    """Окно блока по разметке экрана: ключи вкладок или None — окна нет (панель колонкой).

    Бросает SkipError, если панели нет или в ней не выбран блок (тогда «нет окна» было бы
    ложью)."""
    m = _PANEL.search(html)
    if m is None:
        raise SkipError("в ответе нет панели [data-schema-panel]")
    panel = m.group(0)
    if _SELECTED not in panel:
        raise SkipError("панель без выбранного блока (ref не найден)")
    if _WINDOW_DONE not in panel:
        return None
    return _TAB.findall(panel)


def schema_pages(tenant, saved) -> list:
    """Строки выбора «Seitentyp» и по первому объекту каждого вида — как стенд владельца."""
    from apps.core import site_schema

    rows = [r for _g, items in site_schema.type_groups(tenant, saved) for r in items]
    seen = {r.code for r in rows}
    for kind in site_schema.OBJECT_KINDS:  # «Nur diese Seite»: первый объект каждого вида
        try:
            obj = site_schema.object_model(kind).objects.order_by("pk").first()
        except Exception:  # noqa: BLE001 — модель вида недоступна у бизнеса: строки нет
            obj = None
        if obj is None:
            continue
        row = site_schema.object_row(saved, f"{kind}@{kind}:{obj.pk.hex}")
        if row is not None and row.code not in seen and site_schema.host_for(row.code):
            try:
                site_schema.resolve(tenant, row.code)
            except Exception:  # noqa: BLE001 — как стенд владельца: страницы нет
                continue
            rows.append(row)
    return rows


def page_blocks(tenant, saved, row) -> list[dict]:
    """Строки экрана страницы: [{ref, key, label}] — `blocks_for` без общих блоков схемы
    объекта и строка «Einstellungen der Seite» (`page_row_ref`), как стенд владельца."""
    from apps.core import site_schema

    blocks = site_schema.blocks_for(saved, row.code, host=row.host or None)  # как экран
    out = [
        {"ref": b["ref"], "key": b["key"], "label": str(b.get("label", ""))}
        for b in blocks
        if not b.get("shared")
    ]
    if site_schema.page_row_ref(tenant, row.code, blocks) == site_schema.PAGE_REF:
        out.append({"ref": site_schema.PAGE_REF, "key": site_schema.PAGE_REF, "label": ""})
    return out


def group_of(code: str, host: str) -> str:
    """Группа плана M5d по коду и хосту страницы (правило — в докстринге модуля)."""
    from apps.core import detail_parts, detail_sections, site_schema

    module = detail_parts.module_of(detail_parts.shared_host(host or ""))
    if module in CHECKOUT_MODULES:
        return "G4"
    if code.split("@", 1)[0] == site_schema.TEXT:
        return "G3"
    if module and len(detail_sections.sections_for(module)) == 1:
        return "G2"
    if module:
        return "G1"
    return NO_GROUP


# --- прогон по бизнесу ----------------------------------------------------------------------


def _block_writes(execute, sql, params, many, context):
    if _WRITE_SQL.match(sql or ""):
        raise SkipError(f"запись в БД: {sql.split()[0].upper()} {(sql or '')[:60]!r}")
    return execute(sql, params, many, context)


def owner_client(tenant, host: str):
    """Client владельца бизнеса: сессия в кэше, без сигнала входа (ни `last_login`, ни аудита).

    Вызывать при `connection.set_tenant(tenant)`: владелец живёт в схеме бизнеса."""
    from django.conf import settings
    from django.contrib.auth import (
        BACKEND_SESSION_KEY,
        HASH_SESSION_KEY,
        SESSION_KEY,
        get_user_model,
    )
    from django.db import connection
    from django.test import Client

    from apps.core.session_schema import SESSION_SCHEMA_KEY

    user = get_user_model().objects.get(email=f"{tenant.slug}@example.com")
    client = Client(HTTP_HOST=host)
    session = client.session
    session[SESSION_KEY] = user._meta.pk.value_to_string(user)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session[SESSION_SCHEMA_KEY] = connection.schema_name
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


def client_fetch(client):
    """fetch(code, ref) → (код ответа, html) через вьюху экрана (`site-schema`)."""

    def fetch(code: str, ref: str = "") -> tuple[int, str]:
        query = {"seite": code, **({"block": ref} if ref else {})}
        resp = client.get(AUFBAU, query)
        return resp.status_code, resp.content.decode("utf-8", "replace")

    return fetch


def inventory(tenant, fetch, kit: str = "", codes=None) -> list[dict]:
    """Строки таблицы бизнеса: по одной на (страница, ref) или «пропущено» на страницу.

    `fetch(code, ref)` — ответ вьюхи экрана (в скрипте — Client, в замке — RequestFactory);
    `codes` — только эти коды страниц (замок), None — все."""
    from apps.core import site_schema
    from apps.tenants import siteconfig

    saved = siteconfig.normalize(tenant.site_config)
    base = {"kit": kit or tenant.slug, "btype": tenant.business_type}
    out = []
    for row in schema_pages(tenant, saved):
        if codes is not None and row.code not in codes:
            continue
        page = {**base, "code": row.code, "host": row.host or "", "page": str(row.label)}
        # тип страницы без id объекта — так считает виды стенд владельца (§8.5: 51 вид)
        page["type"] = (
            row.code.split("@", 1)[0] if site_schema.is_object_code(row.code) else row.code
        )
        page["group"] = group_of(row.code, row.host or "")
        try:
            blocks = page_blocks(tenant, saved, row)
            status, _html = fetch(row.code)
            if status != 200:
                raise SkipError(f"экран страницы: ответ {status}")
        except (SkipError, site_schema.SchemaError) as exc:
            out.append({**page, "ref": "", "key": "", "skipped": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — сбой одной страницы виден строкой
            out.append({**page, "ref": "", "key": "", "skipped": f"{type(exc).__name__}: {exc}"})
            continue
        for b in blocks:
            line = {**page, "ref": b["ref"], "key": b["key"], "label": b["label"]}
            try:
                status, html = fetch(row.code, b["ref"])
                if status != 200:
                    raise SkipError(f"окно: ответ {status}")
                tabs = window_tabs(html)
            except Exception as exc:  # noqa: BLE001 — SkipError, SchemaError и сбой вьюхи
                line["skipped"] = (
                    str(exc) if isinstance(exc, SkipError) else f"{type(exc).__name__}: {exc}"
                )
            else:
                line["window"] = tabs is not None
                line["tabs"] = tabs or []
            out.append(line)
    return out


def run(slugs) -> list[dict]:
    """Прогон по поддоменам китов на текущей БД (Django уже поднят)."""
    from django.db import connection

    from apps.tenants.models import Domain, Tenant

    lines = []
    for slug in slugs:
        connection.set_schema_to_public()
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            lines.append({"kit": slug, "code": "", "ref": "", "skipped": "нет бизнеса"})
            continue
        host = (
            Domain.objects.filter(tenant=tenant, is_primary=True)
            .values_list("domain", flat=True)
            .first()
        )
        connection.set_tenant(tenant)
        client = None
        try:
            with connection.execute_wrapper(_block_writes):
                client = owner_client(tenant, host)
                lines.extend(inventory(tenant, client_fetch(client), kit=slug))
        except Exception as exc:  # noqa: BLE001 — бизнес не прошёл целиком: видно строкой
            lines.append(
                {"kit": slug, "code": "", "ref": "", "skipped": f"{type(exc).__name__}: {exc}"}
            )
        finally:
            if client is not None:  # ревью: сессия владельца не остаётся в кэше на срок жизни
                client.session.delete()
            connection.set_schema_to_public()
    return lines


# --- сводка ---------------------------------------------------------------------------------


def summarize(lines: list[dict]) -> dict:
    """По виду блока (`key`): страниц, китов, с окном / без окна; итог и группы G1–G4."""
    kinds: dict[str, dict] = {}
    for ln in lines:
        if ln.get("skipped") or not ln.get("key"):
            continue
        k = kinds.setdefault(
            ln["key"],
            {"key": ln["key"], "with": 0, "without": 0, "pages": set(), "kits": set()},
        )
        k["with" if ln["window"] else "without"] += 1
        k["pages"].add(f"{ln['kit']}:{ln['code']}")
        k["kits"].add(ln["kit"])
        k.setdefault("in_groups", set()).add(ln["group"])
        k.setdefault("tabs", set()).update(ln["tabs"])
        k.setdefault("labels", set()).add(ln.get("label", ""))
    rows = []
    for k in sorted(kinds.values(), key=lambda v: (v["with"] > 0, v["key"])):
        rows.append(
            {
                "key": k["key"],
                "with": k["with"],
                "without": k["without"],
                "pages": len(k["pages"]),
                "kits": sorted(k["kits"]),
                "in_groups": sorted(k["in_groups"]),
                "tabs": sorted(k["tabs"]),
                "labels": sorted(x for x in k["labels"] if x)[:3],
            }
        )
    groups: dict[str, dict] = defaultdict(
        lambda: {"rows_with": 0, "rows_without": 0, "kinds_with": set(), "kinds_without": set()}
    )
    for ln in lines:
        if ln.get("skipped") or not ln.get("key"):
            continue
        g = groups[ln["group"]]
        if ln["window"]:
            g["rows_with"] += 1
            g["kinds_with"].add(ln["key"])
        else:
            g["rows_without"] += 1
            g["kinds_without"].add(ln["key"])
    # места без окна: (кит, хост, ref); виды стенда владельца — (тип страницы, ref) без id объекта
    bare = [ln for ln in lines if not ln.get("skipped") and ln.get("key") and not ln["window"]]
    places = {(ln["kit"], ln["host"], ln["ref"]) for ln in bare}
    return {
        "kinds": rows,
        "total": {
            "kinds_without": sum(1 for r in rows if r["without"]),
            "kinds_with": sum(1 for r in rows if r["with"]),
            "kinds_only_without": sum(1 for r in rows if r["without"] and not r["with"]),
            "kinds_mixed": sum(1 for r in rows if r["without"] and r["with"]),
            "rows_without": sum(r["without"] for r in rows),
            "rows_with": sum(r["with"] for r in rows),
            "places_without": len(places),
            "code_refs_without": len({(_ID.sub("<id>", ln["code"]), ln["ref"]) for ln in bare}),
            "type_refs_without": len({(ln["type"], ln["ref"]) for ln in bare}),
            "skipped": sum(1 for ln in lines if ln.get("skipped")),
        },
        "by_group": {
            name: {
                "rows_with": g["rows_with"],
                "rows_without": g["rows_without"],
                "kinds_with": sorted(g["kinds_with"]),
                "kinds_without": sorted(g["kinds_without"]),
            }
            for name, g in sorted(groups.items())
        },
        "skipped": [ln for ln in lines if ln.get("skipped")],
    }


def markdown(summary: dict) -> str:
    t = summary["total"]
    out = [
        "# FB-33 M5d-0: блоки без окна",
        "",
        f"**Итог: {t['kinds_without']} видов без окна / {t['kinds_with']} с окном** "
        f"(только без окна — {t['kinds_only_without']}, смешанных — {t['kinds_mixed']}); "
        f"строк: без окна {t['rows_without']}, с окном {t['rows_with']}; "
        f"мест (кит, хост, ref) без окна — {t['places_without']}, разных (код без id, ref) — "
        f"{t['code_refs_without']}, разных (тип страницы, ref) — {t['type_refs_without']} "
        f"(так считает стенд владельца); пропущено {t['skipped']}.",
        "",
        "## По виду блока",
        "",
        "| key | без окна | с окном | страниц | киты | группы | вкладки | подпись |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for r in summary["kinds"]:
        out.append(
            f"| `{r['key']}` | {r['without']} | {r['with']} | {r['pages']} | "
            f"{', '.join(r['kits'])} | {', '.join(r['in_groups'])} | {', '.join(r['tabs'])} | "
            f"{' / '.join(r['labels'])} |"
        )
    out += ["", "## Группы плана M5d", ""]
    out += ["| группа | строк без окна | строк с окном | виды без окна | виды с окном |"]
    out += ["|---|---:|---:|---|---|"]
    for name, g in summary["by_group"].items():
        out.append(
            f"| {name} ({GROUP_NAMES.get(name, '')}) | {g['rows_without']} | {g['rows_with']} | "
            f"{', '.join(g['kinds_without'])} | {', '.join(g['kinds_with'])} |"
        )
    out += ["", "## Пропущено", ""]
    if not summary["skipped"]:
        out.append("нет")
    for ln in summary["skipped"]:
        out.append(
            f"- {ln.get('kit')} «{ln.get('code')}» {ln.get('ref') or '(страница)'}: "
            f"пропущено: {ln['skipped']}"
        )
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="", help="поддомены китов через запятую")
    ap.add_argument("--json", default="", help="куда записать полную таблицу (JSON)")
    args = ap.parse_args(argv)
    slugs = [s for s in args.only.split(",") if s] or list(DEFAULT_SLUGS)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.stand")
    if os.environ["DJANGO_SETTINGS_MODULE"] != "config.settings.stand":
        sys.exit("инвентаризация — только на настройках стенда (config.settings.stand)")
    import django

    django.setup()
    lines = run(slugs)
    summary = summarize(lines)
    if args.json:
        Path(args.json).write_text(
            json.dumps({"lines": lines, "overview": summary}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
