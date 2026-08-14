"""Покрытие переводов ДЕМО-контента: сколько текста витрин-демо реально
переведено на en/ru/uk/tr (аудит 2026-08-13).

Зачем отдельный инструмент. `scripts/i18n_gap.py` гейтит ХРОМ (msgid в коде vs
`.po`), но контент демо-китов живёт не в каталогах gettext, а в словарях
`apps/tenants/demo_i18n_<loc>.json`, и доезжает до витрины через два обхода
(`overlay_config` для site_config и `translate_tenant_content` для моделей).
Строка, которой нет в словаре — или которую обход не берёт, — молча выводится
по-немецки на любой локали. Этот скрипт делает разрыв видимым.

Что считает:
  * ROUTED — строки, у которых путь перевода ЕСТЬ (обход их берёт): для них
    покрытие = наличие записи в словаре локали;
  * GAP — строки БЕЗ пути перевода (модель без i18n-поля, ключ вне обхода):
    запись в словаре им не поможет, нужна доработка (список — в отчёте).

Запуск:  uv run python scripts/demo_i18n_gap.py [--missing ru]
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

from apps.tenants import demo_i18n, demo_kits  # noqa: E402

LOCALES = demo_i18n.DEMO_LOCALES
# Чистые числа/символы (цены, «200+», «4,9 ★») переводить нечего.
NUMERIC = re.compile(r"^[\d\s.,+\-–—%€/x×★]+$")
# Строки, которые переводить НЕЛЬЗЯ: название заведения (оно же hero_title) и
# международные коды размеров. В словарях их нет намеренно — замок проекта
# запрещает identity-записи, поэтому в знаменатель покрытия они не идут.
SIZE_CODE = re.compile(r"^(XS|S|M|L|XL|XXL|\d{2,3})$")


def _text(value) -> str:
    if isinstance(value, dict):  # i18n-дикт кита — база всегда de
        value = value.get("de") or ""
    return value.strip() if isinstance(value, str) else ""


class Collector:
    """Собирает немецкие строки кита, помечая наличие пути перевода."""

    def __init__(self, proper_names: frozenset[str] = frozenset()) -> None:
        self.routed: dict[str, tuple[str, str]] = {}  # строка → (группа, где)
        self.gap: dict[str, tuple[str, str]] = {}
        self.skip: dict[str, tuple[str, str]] = {}  # перевод не требуется
        self.proper_names = proper_names

    def add(self, group: str, value, where: str, *, routed: bool = True) -> None:
        txt = _text(value)
        if not txt or NUMERIC.match(txt):
            return
        if routed and (txt in self.proper_names or SIZE_CODE.match(txt)):
            self.skip.setdefault(txt, (group, where))
            return
        target = self.routed if routed else self.gap
        target.setdefault(txt, (group, where))


def _collect_config(kit, c: Collector, kk: str) -> None:
    """site_config-тексты (обход `overlay_config`)."""
    c.add("hero", kit.hero_title, f"{kk}:hero_title")
    c.add("hero", kit.hero_text, f"{kk}:hero_text")
    c.add("about", kit.about_title, f"{kk}:about_title")
    c.add("about", kit.about_text, f"{kk}:about_text")
    for key, val in (kit.section_titles or {}).items():
        c.add("section_titles", val, f"{kk}:section_titles.{key}")
    for key, val in (kit.cta or {}).items():
        if key in ("title", "text", "button_label", "label"):
            c.add("cta", val, f"{kk}:cta.{key}")
    for i, item in enumerate(kit.faq or []):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("faq", item[0], f"{kk}:faq[{i}].q")
            c.add("faq", item[1], f"{kk}:faq[{i}].a")
    for i, item in enumerate(kit.testimonials or []):  # (имя, текст[, звёзды[, фото]])
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("testimonials", item[1], f"{kk}:testimonials[{i}].text")
    for i, item in enumerate(kit.process or []):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("process", item[0], f"{kk}:process[{i}].title")
            c.add("process", item[1], f"{kk}:process[{i}].text")
    for i, item in enumerate(kit.team or []):  # (имя, роль, фото) — только роль
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("team_roles", item[1], f"{kk}:team[{i}].role")
    for i, item in enumerate(kit.usp or []):  # (иконка, подпись[, текст])
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("usp", item[1], f"{kk}:usp[{i}].label")
            if len(item) > 2:
                c.add("usp", item[2], f"{kk}:usp[{i}].text")
    for mark in (kit.trust or {}).get("marks") or []:
        c.add("trust", mark, f"{kk}:trust.marks")
    for i, hero in enumerate(kit.heroes or []):
        if isinstance(hero, dict):
            for key in ("title", "text", "button_label"):
                c.add("heroes", hero.get(key), f"{kk}:heroes[{i}].{key}")
    for key, cover in (kit.archetype_covers or {}).items():
        if isinstance(cover, dict):
            for field in ("intro", "title"):
                c.add("archetypes", cover.get(field), f"{kk}:archetype_covers.{key}.{field}")
    for i, blk in enumerate(kit.home_blocks or []):  # C-блоки главной
        if not isinstance(blk, dict):
            continue
        data, bkey = blk.get("data") or {}, blk.get("key", "?")
        for field in demo_i18n._CBLOCK_TEXT_FIELDS:
            c.add("cblocks", data.get(field), f"{kk}:home_blocks[{i}].{bkey}.{field}")
        for field, keys in demo_i18n._CBLOCK_LIST_FIELDS.items():
            for row in data.get(field) or []:
                if isinstance(row, dict):
                    for key in keys:
                        c.add("cblocks", row.get(key), f"{kk}:home_blocks[{i}].{bkey}.{field}")
    for et in (kit.anfrage_form or {}).get("event_types") or []:
        c.add("anfrage", et, f"{kk}:anfrage.event_types")
    for i, ba in enumerate(kit.before_after or []):
        if isinstance(ba, (tuple, list)) and len(ba) >= 3:
            c.add("before_after", ba[2], f"{kk}:before_after[{i}]")


def _collect_models(kit, c: Collector, kk: str) -> None:
    """Модельный контент (обход `translate_tenant_content`)."""

    def products(cats, prefix="categories"):
        for ci, entry in enumerate(cats or []):
            if not isinstance(entry, (tuple, list)) or not entry:
                continue
            c.add("categories", entry[0], f"{kk}:{prefix}[{ci}].name")
            if len(entry) > 4 and isinstance(entry[4], str):
                c.add("category_desc", entry[4], f"{kk}:{prefix}[{ci}].landing")
            if len(entry) > 3 and isinstance(entry[3], list):
                products(entry[3], f"{prefix}[{ci}].children")
            for pi, prod in enumerate(entry[2] if len(entry) > 2 else []):
                if not isinstance(prod, dict):
                    continue
                where = f"{kk}:{prefix}[{ci}].prod[{pi}]"
                c.add("products", prod.get("name"), f"{where}.name")
                c.add("products", prod.get("desc"), f"{where}.desc")
                for field in ("origin", "ingredients", "material", "care"):
                    c.add("product_chars", prod.get(field), f"{where}.{field}")
                for vi, var in enumerate(prod.get("variants") or []):
                    if isinstance(var, (tuple, list)) and var:
                        c.add("variants", var[0], f"{where}.var[{vi}]")
                    elif isinstance(var, dict):
                        for field in ("label", "size", "color"):
                            c.add("variants", var.get(field), f"{where}.var[{vi}].{field}")
                for mi, grp in enumerate(prod.get("modifiers") or []):
                    if not isinstance(grp, dict):
                        continue
                    c.add("modifiers", grp.get("name"), f"{where}.mod[{mi}]")
                    for oi, opt in enumerate(grp.get("options") or []):
                        label = opt[0] if isinstance(opt, (tuple, list)) and opt else None
                        if isinstance(opt, dict):
                            label = opt.get("label")
                        c.add("modifiers", label, f"{where}.mod[{mi}].opt[{oi}]")

    products(kit.categories)
    for table in (kit.size_tables or {}).values():
        c.add("size_tables", table, f"{kk}:size_tables")
    for i, svc in enumerate(kit.services or []):
        if isinstance(svc, (tuple, list)) and svc:
            c.add("services", svc[0], f"{kk}:services[{i}].name")
        elif isinstance(svc, dict):
            c.add("services", svc.get("name"), f"{kk}:services[{i}].name")
            c.add("services", svc.get("description"), f"{kk}:services[{i}].description")
            for attr in svc.get("attributes") or []:
                c.add("service_rich", attr, f"{kk}:services[{i}].attributes")
            for faq in svc.get("faq") or []:
                if isinstance(faq, dict):
                    c.add("service_rich", faq.get("q"), f"{kk}:services[{i}].faq.q")
                    c.add("service_rich", faq.get("a"), f"{kk}:services[{i}].faq.a")
    for i, unit in enumerate(kit.stay_units or []):
        if isinstance(unit, (tuple, list)) and unit:
            c.add("stay_units", unit[0], f"{kk}:stay_units[{i}]")
        elif isinstance(unit, dict):
            c.add("stay_units", unit.get("name"), f"{kk}:stay_units[{i}].name")
            c.add("stay_units", unit.get("description"), f"{kk}:stay_units[{i}].description")
    for i, plan in enumerate(kit.rate_plans or []):
        if isinstance(plan, dict):
            c.add("rate_plans", plan.get("name"), f"{kk}:rate_plans[{i}].name")
            c.add("rate_plans", plan.get("description"), f"{kk}:rate_plans[{i}].description")
    c.add("house_rules", kit.house_rules, f"{kk}:house_rules")
    for i, ev in enumerate(kit.events or []):
        if isinstance(ev, (tuple, list)) and ev:
            c.add("events", ev[0], f"{kk}:events[{i}]")
        elif isinstance(ev, dict):
            c.add("events", ev.get("title"), f"{kk}:events[{i}].title")
            c.add("events", ev.get("description"), f"{kk}:events[{i}].description")
    for i, promo in enumerate(kit.promotions_spec or []):
        if isinstance(promo, dict):
            c.add("promotions", promo.get("title"), f"{kk}:promotions[{i}].title")
            c.add("promotions", promo.get("desc"), f"{kk}:promotions[{i}].desc")
            c.add("promotions", promo.get("group"), f"{kk}:promotions[{i}].group")
    for i, combo in enumerate(kit.combos or []):
        if isinstance(combo, dict):
            c.add("combos", combo.get("name"), f"{kk}:combos[{i}].name")
            c.add("combos", combo.get("description"), f"{kk}:combos[{i}].description")
    for i, coll in enumerate(kit.collections or []):
        if isinstance(coll, (tuple, list)) and coll:
            c.add("collections", coll[0], f"{kk}:collections[{i}]")


def _collect_gaps(kit, c: Collector, kk: str) -> None:
    """Контент, дошедший до обхода поздно (I18N-12) или не имеющий пути до сих пор.

    После I18N-12 (миграции `*_i18n` у Event.details/Teacher/BlogPost/Resource/
    PassPlan/Extra/LoyaltyProgram/Voucher/ComboGroup/Review/Job/Tenant) почти всё
    отсюда переехало в ROUTED — здесь остаётся только то, что переводить не нужно
    либо путь ещё не заведён."""
    for i, ev in enumerate(kit.events or []):
        if not isinstance(ev, dict):
            continue
        details = ev.get("details")
        if isinstance(details, dict):  # ретрит-лендинг (Event.details, JSON без i18n)
            for field, val in details.items():
                for row in val if isinstance(val, list) else [val]:
                    if isinstance(row, str):
                        c.add("event_details", row, f"{kk}:events[{i}].details.{field}")
                    elif isinstance(row, dict):
                        for key, sub in row.items():
                            if key not in ("photo", "image", "url", "rating"):
                                c.add(
                                    "event_details",
                                    sub,
                                    f"{kk}:events[{i}].details.{field}",
                                )
        for q in ev.get("questions") or []:
            if isinstance(q, dict):
                c.add("event_questions", q.get("label"), f"{kk}:events[{i}].questions")
        for step in ev.get("program") or []:
            if isinstance(step, dict):
                for field in ("title", "text"):
                    c.add("event_program", step.get(field), f"{kk}:events[{i}].program")
    for i, post in enumerate(kit.blog_posts or []):
        for part in post[:3] if isinstance(post, (tuple, list)) else []:
            c.add("blog_posts", part, f"{kk}:blog_posts[{i}]")
    for i, job in enumerate(kit.job_samples or []):
        if isinstance(job, dict):
            for field in ("title", "description"):
                c.add("job_samples", job.get(field), f"{kk}:job_samples[{i}].{field}")
            for line in job.get("lines") or []:
                if isinstance(line, dict):
                    c.add(
                        "job_samples",
                        line.get("text"),
                        f"{kk}:job_samples[{i}].lines",
                    )
    # MT-D6: тур-продукт (events.Tour). До этой правки контент туров не попадал
    # в замер ВООБЩЕ — отчёт по киту `moto` был занижен в разы. Операционные
    # данные (`tour_operations`: лента группы, закупки, чек-лист) сюда НЕ идут:
    # они живут в кабинете и в закрытом пространстве участников, а скрипт меряет
    # ВИТРИНУ.
    for i, tour in enumerate(kit.tours or []):
        if not isinstance(tour, dict):
            continue
        where = f"{kk}:tours[{i}]"
        for field in ("title", "summary", "description", "region", "country"):
            c.add("tours", tour.get(field), f"{where}.{field}")
        for field, val in (tour.get("details") or {}).items():
            for row in val if isinstance(val, list) else [val]:
                if isinstance(row, str):
                    c.add("tour_details", row, f"{where}.details.{field}")
                elif isinstance(row, (tuple, list)):  # («вопрос», «ответ»)
                    for part in row:
                        c.add("tour_details", part, f"{where}.details.{field}")
                elif isinstance(row, dict):
                    for key, sub in row.items():
                        if key not in ("photo", "image", "url", "rating"):
                            c.add("tour_details", sub, f"{where}.details.{field}")
        for stop in tour.get("itinerary") or []:
            if isinstance(stop, dict):
                for key in ("title", "text", "overnight"):
                    c.add("tour_route", stop.get(key), f"{where}.itinerary.{key}")
    for i, teacher in enumerate(kit.teachers or []):
        if isinstance(teacher, (tuple, list)) and len(teacher) >= 2:
            c.add("teachers", teacher[1], f"{kk}:teachers[{i}].title")
            if len(teacher) >= 4:
                c.add("teachers", teacher[3], f"{kk}:teachers[{i}].bio")
    for i, res in enumerate(kit.resources or []):
        if isinstance(res, dict):
            for field in ("name", "title", "bio"):
                c.add("resources", res.get(field), f"{kk}:resources[{i}].{field}")
    for i, extra in enumerate(kit.extras or []):
        label = extra[0] if isinstance(extra, (tuple, list)) and extra else None
        c.add("extras", label, f"{kk}:extras[{i}]")
    for field in ("label", "reward"):
        c.add("loyalty", (kit.loyalty or {}).get(field), f"{kk}:loyalty.{field}")
    for i, voucher in enumerate(kit.vouchers or []):
        if isinstance(voucher, dict):
            c.add("vouchers", voucher.get("label"), f"{kk}:vouchers[{i}]")
    for i, plan in enumerate(kit.pass_plans or []):
        if isinstance(plan, dict):
            c.add("pass_plans", plan.get("label"), f"{kk}:pass_plans[{i}]")
    for i, combo in enumerate(kit.combos or []):
        for grp in (combo.get("groups") or []) if isinstance(combo, dict) else []:
            if isinstance(grp, dict):
                c.add("combo_groups", grp.get("label"), f"{kk}:combos[{i}].groups")
    c.add("opening_hours_text", kit.opening_hours_text, f"{kk}:opening_hours_text")
    c.add("service_area_note", kit.service_area_note, f"{kk}:service_area_note")
    c.add("stay_promo", (kit.stay_promo or {}).get("label"), f"{kk}:stay_promo")
    for kind, defs in (kit.status_defs or {}).items():
        for row in defs or []:
            if isinstance(row, dict):
                c.add("status_defs", row.get("label"), f"{kk}:status_defs.{kind}")
    for i, item in enumerate(kit.reviews_seed or []):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            c.add("reviews", item[1], f"{kk}:reviews_seed[{i}]")
    for name in ("product_reviews", "service_reviews", "stay_reviews", "event_reviews"):
        for i, item in enumerate(getattr(kit, name, None) or []):
            if isinstance(item, (tuple, list)) and len(item) >= 5:
                c.add("reviews", item[4], f"{kk}:{name}[{i}]")


def measure(only: str = ""):
    per_kit, routed_all, gap_all, skip_all = [], {}, {}, {}
    for key, kit in demo_kits.KITS.items():
        if only and key != only:
            continue
        # Имена собственные кита: название заведения (оно же hero_title), имена
        # людей команды и авторов отзывов, имена преподавателей.
        names = {_text(kit.label)} | set(demo_i18n.PROPER_NAMES)
        for item in (kit.team or []) + (kit.testimonials or []) + (kit.teachers or []):
            if isinstance(item, (tuple, list)) and item:
                names.add(_text(item[0]))
        c = Collector(frozenset(n for n in names if n))
        _collect_config(kit, c, key)
        _collect_models(kit, c, key)
        _collect_gaps(kit, c, key)
        routed_all.update(c.routed)
        gap_all.update(c.gap)
        skip_all.update(c.skip)
        row = {"kit": key, "routed": len(c.routed), "gap": len(c.gap), "skip": len(c.skip)}
        for loc in LOCALES:
            row[loc] = sum(1 for txt in c.routed if demo_i18n.t(txt, loc))
        per_kit.append(row)
    # Строка могла попасть в skip у одного кита и в routed у другого — routed главнее.
    for txt in list(skip_all):
        if txt in routed_all:
            skip_all.pop(txt)
    return per_kit, routed_all, gap_all, skip_all


def main() -> int:
    # `--kit <key>` — замер одного кита (иначе список «нет перевода» смешивает
    # все витрины и по нему нельзя доводить конкретный архетип).
    only = sys.argv[sys.argv.index("--kit") + 1] if "--kit" in sys.argv else ""
    per_kit, routed_all, gap_all, skip_all = measure(only)

    print("ПОКРЫТИЕ ПЕРЕВОДА ДЕМО-ВИТРИН (строки с путём перевода)\n")
    header = f"{'демо-кит':<14}{'строк':>7}{'без пути':>10}" + "".join(
        f"{loc:>8}" for loc in LOCALES
    )
    print(header)
    print("-" * len(header))
    for row in sorted(per_kit, key=lambda r: -r["routed"]):
        pct = "".join(f"{100 * row[loc] / max(row['routed'], 1):>7.0f}%" for loc in LOCALES)
        print(f"{row['kit']:<14}{row['routed']:>7}{row['gap']:>10}{pct}")
    print("-" * len(header))

    print(f"\nУникальных строк с путём перевода: {len(routed_all)}")
    for loc in LOCALES:
        have = sum(1 for txt in routed_all if demo_i18n.t(txt, loc))
        print(f"  {loc}: {have}/{len(routed_all)} = {100 * have / max(len(routed_all), 1):.1f}%")
    print(f"Не требуют перевода (имена собственные, коды размеров): {len(skip_all)}")

    groups = defaultdict(list)
    for txt, (group, _where) in routed_all.items():
        groups[group].append(txt)
    print("\nПо группам контента:")
    for group in sorted(groups, key=lambda g: -len(groups[g])):
        txts = groups[group]
        pct = "".join(
            f"{100 * sum(1 for t in txts if demo_i18n.t(t, loc)) / len(txts):>7.0f}%"
            for loc in LOCALES
        )
        print(f"  {group:<18}{len(txts):>5}{pct}")

    if gap_all:
        gap_groups = defaultdict(int)
        for _txt, (group, _where) in gap_all.items():
            gap_groups[group] += 1
        print(f"\nБЕЗ пути перевода — {len(gap_all)} строк (нужна доработка, а не словарь):")
        for group, count in sorted(gap_groups.items(), key=lambda x: -x[1]):
            print(f"  {group:<18}{count:>5}")

    if "--missing" in sys.argv:
        loc = sys.argv[sys.argv.index("--missing") + 1]
        missing = sorted(t for t in routed_all if not demo_i18n.t(t, loc))
        print(f"\nНет перевода на {loc} ({len(missing)}):")
        for txt in missing:
            print(f"  {routed_all[txt][0]:<16} {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
