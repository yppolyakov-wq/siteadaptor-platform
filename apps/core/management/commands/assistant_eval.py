"""AIS A-6a: точность помощника на эталонных фразах (5 языков × каждый обработчик).

    python manage.py assistant_eval --schema <schema> [--lang de] [--route bulk] [--min 0.9]
    python manage.py assistant_eval --schema <schema> --ai      # + настоящая модель (ключ нужен)

Набор — `apps/core/assistant_phrases.py`. Прогон идёт в схеме бизнеса внутри транзакции,
которая ОТКАТЫВАЕТСЯ: тестовые товары («Käsekuchen», «Apfelstrudel», категория «Kuchen»)
создаются и исчезают; в базе ничего не остаётся, в историю помощника ничего не пишется.
Без `--ai` — только маршрут (правила). С `--ai` для ИИ-фраз зовётся модель задачи
`assistant_actions` и проверяется, что сервер собрал из ответа хоть один пункт. План —
docs/ais-a6-quality-plan-2026-11-06.md §3. Выход 1, если точность ниже `--min`."""

from __future__ import annotations

import secrets
import uuid

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

    member = Membership.objects.filter(role=Membership.ROLE_OWNER).select_related("user").first()
    if member is None:
        raise CommandError("В схеме нет владельца — прогон нужен от его имени.")
    return member.user


def _shop(tenant):
    from apps.catalog import writers

    kuchen = writers.create_category(tenant, {"name_de": "Kuchen"})
    writers.create_product(
        tenant, {"name_de": "Käsekuchen", "base_price": "3,20", "category": str(kuchen.pk)}
    )
    writers.create_product(tenant, {"name_de": "Apfelstrudel", "base_price": "3,00"})


def _ai_items(request, text) -> int:
    """Настоящий вызов модели (без кэша и очереди) → сколько пунктов собрал сервер."""
    from apps.ai.api import generate
    from apps.core import assistant_ai_actions as aa

    ctx = aa.wants(request, text)
    if ctx is None:
        return 0
    marker = secrets.token_hex(6)
    result = generate(
        aa.TASK,
        aa.build_prompt(ctx, text, marker),
        schema=aa.schema_for(ctx),
        system=aa.SYSTEM + f" The DATA is framed by markers containing {marker}.",
        tenant=request.tenant.schema_name,
    )
    data = aa._shape(result.data) or {}
    items, _dropped = aa.check_actions(request.tenant, request.user, text, ctx, data)
    return len(items)


class Command(BaseCommand):
    help = "Точность помощника на эталонных фразах (откатываемый прогон в схеме бизнеса)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--lang", choices=LANGS)
        parser.add_argument("--route")
        parser.add_argument("--ai", action="store_true", help="Звать настоящую модель для ИИ-фраз")
        parser.add_argument("--min", type=float, default=0.0)

    def handle(self, *args, **opts):
        from django.conf import settings

        from apps.ai.api import is_enabled
        from apps.core import assistant_ai_actions
        from apps.tenants.models import Tenant

        if opts["ai"] and not (settings.AI_ENABLED and is_enabled(assistant_ai_actions.TASK)):
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
        rows = []
        with schema_context(tenant.schema_name):
            try:
                with transaction.atomic():
                    rows = self._run(tenant, phrases, opts["ai"])
                    raise _Rollback  # тестовые товары и всё созданное — назад
            except _Rollback:
                pass
        return self._print(rows, opts["min"])

    def _run(self, tenant, phrases, use_ai: bool) -> list[dict]:
        from django.conf import settings
        from django.test import override_settings

        from apps.core import assistant_router

        _shop(tenant)
        user = _owner()
        rows = []
        for p in phrases:
            request = _request(tenant, user)
            if p.mode == "followup":  # прошлый ход — в откатываемой транзакции
                assistant_router.route(_request(tenant, user), PREV)
            if p.mode == "ai" and not use_ai:
                # маршрут ИИ-веток зависит только от тумблера задачи, модель не зовётся
                tasks = [*settings.AI_TASKS_ENABLED, "assistant_actions"]
                with override_settings(AI_ENABLED=True, AI_TASKS_ENABLED=tasks):
                    got = assistant_router.classify(request, p.text)
            else:
                got = assistant_router.classify(request, p.text)
            ok = got == p.route
            note = ""
            if ok and use_ai and p.mode == "ai":
                try:
                    n = _ai_items(request, p.text)
                except Exception as exc:  # noqa: BLE001 — одна фраза не роняет прогон
                    n, note = 0, type(exc).__name__
                ok, note = n > 0, note or f"{n} Punkte"
            rows.append({"phrase": p, "got": got, "ok": ok, "note": note, "id": uuid.uuid4().hex})
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
            raise SystemExit(1)
