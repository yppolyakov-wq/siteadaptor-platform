"""AIS A-6a: точность помощника на эталонных фразах (5 языков × каждый обработчик).

    python manage.py assistant_eval --schema <schema> [--lang de] [--route bulk] [--min 0.9]
    python manage.py assistant_eval --schema <schema> --ai      # + настоящая модель (ключ нужен)

Набор — `apps/core/assistant_phrases.py`. Маршрут проверяется в схеме бизнеса внутри
транзакции, которая ОТКАТЫВАЕТСЯ: тестовые товары («Käsekuchen», «Apfelstrudel», категория
«Kuchen») создаются и исчезают (в кэше могут остаться осиротевшие записи задач продолжений —
TTL 30 мин). Если такие названия у бизнеса уже есть — отказ (совпадение дало бы ложные
промахи): запускать на демо- или тестовом бизнесе.

С `--ai` для ИИ-фраз зовётся настоящая модель задачи `assistant_actions` — ВНЕ откатываемой
транзакции (учёт расходов AIUsage и дневной бюджет не теряются); ответ проверяется без базы:
есть пункты, номера в пределах списка, объект назван во фразе. План —
docs/ais-a6-quality-plan-2026-11-06.md §3. Ошибка, если точность ниже `--min`."""

from __future__ import annotations

import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import schema_context

from apps.core.assistant_phrases import LANGS, PHRASES, PREV


class _Rollback(Exception):
    pass


def _request(tenant, user):
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    request = RequestFactory().post("/dashboard/assistent/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _owner():
    from apps.core.models import Membership

    member = (
        Membership.objects.filter(role=Membership.ROLE_OWNER)
        .select_related("user")
        .order_by("pk")
        .first()
    )
    if member is None:
        raise CommandError("В схеме нет владельца — прогон нужен от его имени.")
    return member.user


SHOP_NAMES = ("Käsekuchen", "Apfelstrudel", "Kuchen")


def _check_free(tenant) -> None:
    from apps.catalog.models import Category, Product

    taken = [
        n
        for n in SHOP_NAMES
        if Product.objects.filter(name__de__iexact=n).exists()
        or Category.objects.filter(name__de__iexact=n).exists()
    ]
    if taken:
        raise CommandError(
            f"У бизнеса уже есть {', '.join(taken)} — совпадение дало бы ложные промахи. "
            "Запускайте на демо- или тестовом бизнесе."
        )


def _shop(tenant):
    from apps.catalog import writers

    kuchen = writers.create_category(tenant, {"name_de": "Kuchen"})
    writers.create_product(
        tenant, {"name_de": "Käsekuchen", "base_price": "3,20", "category": str(kuchen.pk)}
    )
    writers.create_product(tenant, {"name_de": "Apfelstrudel", "base_price": "3,00"})


def _ai_job(request, text) -> dict | None:
    """Всё для вызова модели по фразе (внутри откатываемой транзакции, без вызова)."""
    from apps.core import assistant_ai_actions as aa

    ctx = aa.wants(request, text)
    if ctx is None:
        return None
    marker = secrets.token_hex(6)
    return {
        "prompt": aa.build_prompt(ctx, text, marker),
        "schema": aa.schema_for(ctx),
        "system": aa.SYSTEM + f" The DATA is framed by markers containing {marker}.",
        "objects": ctx["objects"],
        "text": text,
    }


def _ai_check(job: dict, schema: str) -> tuple[bool, str]:
    """Настоящий вызов модели ВНЕ транзакции (учёт AIUsage сохраняется) + проверка без базы:
    хоть один пункт с номером из списка, объект которого назван во фразе."""
    from apps.ai.api import generate
    from apps.core import assistant_ai_actions as aa

    result = generate(
        aa.TASK, job["prompt"], schema=job["schema"], system=job["system"], tenant=schema
    )
    data = aa._shape(result.data) or {}
    objects, q_cf = job["objects"], job["text"].casefold()
    good = [
        it
        for it in data.get("items") or []
        if isinstance(it.get("ref"), int)
        and 0 <= it["ref"] < len(objects)
        and aa._named(q_cf, objects[it["ref"]][2])
    ] + [
        it
        for it in data.get("items") or []
        if it.get("action") in aa.CREATE_ACTIONS and it.get("name_text")
    ]
    actions = ", ".join(sorted({it["action"] for it in good}))
    return bool(good), actions or ("not_action" if data.get("not_action") else "0 Punkte")


class Command(BaseCommand):
    help = "Точность помощника на эталонных фразах (откатываемый прогон в схеме бизнеса)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--lang", choices=LANGS)
        parser.add_argument("--route")
        parser.add_argument("--ai", action="store_true", help="Звать настоящую модель для ИИ-фраз")
        parser.add_argument("--min", type=float, default=0.0)

    def handle(self, *args, **opts):
        from apps.ai.api import is_enabled
        from apps.core import assistant_ai_actions
        from apps.tenants.models import Tenant

        if opts["ai"] and not is_enabled(assistant_ai_actions.TASK):
            raise CommandError(
                "--ai: ИИ или задача assistant_actions выключены (KI-Einstellungen)."
            )
        tenant = Tenant.objects.filter(schema_name=opts["schema"]).first()
        if tenant is None:
            raise CommandError(f"Схема {opts['schema']!r} не найдена.")
        phrases = [
            p
            for p in PHRASES
            if (not opts["lang"] or p.lang == opts["lang"])
            and (not opts["route"] or p.route == opts["route"])
        ]
        rows: list[dict] = []
        with schema_context(tenant.schema_name):
            _check_free(tenant)
            try:
                with transaction.atomic():
                    rows = self._run(tenant, phrases, opts["ai"])
                    raise _Rollback  # тестовые товары и всё созданное — назад
            except _Rollback:
                pass
            for row in rows:  # модель — после отката: учёт расходов не теряется
                if row.pop("ai_job", None) is not None and row["ok"]:
                    try:
                        row["ok"], row["note"] = _ai_check(row["job"], tenant.schema_name)
                    except Exception as exc:  # noqa: BLE001 — одна фраза не роняет прогон
                        row["ok"], row["note"] = False, type(exc).__name__
        return self._print(rows, opts["min"])

    def _run(self, tenant, phrases, use_ai: bool) -> list[dict]:
        from apps.ai import config
        from apps.core import assistant_router

        _shop(tenant)
        user = _owner()
        rows = []
        for p in phrases:
            request = _request(tenant, user)
            if p.mode == "followup":  # прошлый ход — в откатываемой транзакции
                assistant_router.route(_request(tenant, user), PREV)
            job = None
            if p.mode == "ai":
                # маршрут ИИ-веток зависит только от тумблера задачи (поверх админки и .env)
                tasks = [*(config.get("AI_TASKS_ENABLED") or ()), "assistant_actions"]
                with config.override(AI_ENABLED=True, AI_TASKS_ENABLED=tasks):
                    got = assistant_router.classify(request, p.text)
                    if use_ai and got == p.route:
                        job = _ai_job(request, p.text)
            else:
                got = assistant_router.classify(request, p.text)
            row = {"phrase": p, "got": got, "ok": got == p.route, "note": ""}
            if job is not None:
                row.update(ai_job=True, job=job)
            rows.append(row)
        return rows

    def _print(self, rows: list[dict], minimum: float):
        by_route: dict[str, list] = {}
        for r in rows:
            by_route.setdefault(r["phrase"].route, []).append(r["ok"])
        self.stdout.write("route         ok/all  precision")
        for route, oks in sorted(by_route.items()):
            self.stdout.write(f"{route:<13} {sum(oks):>2}/{len(oks):<3}  {sum(oks) / len(oks):.0%}")
        misses = [r for r in rows if not r["ok"]]
        if misses:
            self.stdout.write("\nПромахи:")
            for r in misses:
                p = r["phrase"]
                self.stdout.write(
                    f"  [{p.lang}] {p.text!r}: ждали {p.route}, вышло {r['got']} {r['note']}"
                )
        total = sum(r["ok"] for r in rows) / len(rows) if rows else 1.0
        self.stdout.write(f"\nИтого: {total:.0%} ({len(rows)} фраз)")
        if total < minimum:
            raise CommandError(f"Точность {total:.0%} ниже --min {minimum:.0%}.")
