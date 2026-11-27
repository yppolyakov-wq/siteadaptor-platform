"""FB-33 стопка 16 D9: кандидаты с испорченной немецкой базой USP, знаков доверия и
«Vorher & nachher» — только чтение.

До D9 «Speichern» Студии главной на языке перевода переносил перевод в немецкую базу
(`usp_bar`, `trust.marks`, `before_after`) и снимал сам перевод. D9 чинит причину; уже
испорченные базы решение владельца (2026-11-26) — не чинить автоматически, а показать списком.

Признаки: текст базы совпадает с переводом любого языка — в текущем `i18n` или в снимках
`history`; или в базе кириллица / турецкие буквы. Печать — только схема/слаг, место (ключ),
язык и число совпадений: тексты бизнеса не выводятся. Транзакция READ ONLY — запись
невозможна.

    python manage.py usp_overlay_check
    # на сервере: docker compose --env-file .env.prod -f docker-compose.prod.yml \
    #   run --rm web python manage.py usp_overlay_check
"""

import re
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import connection, transaction

NON_DE = re.compile(r"[Ѐ-ӿĞğİıŞş]")
KEYS = ("usp_bar", "trust", "before_after")


def _list(value):
    return value if isinstance(value, list) else []


def texts(cfg):
    """(ключ, текст) немецкой базы тех списков, что ломал Save Студии на языке перевода."""
    if not isinstance(cfg, dict):
        return
    for it in _list(cfg.get("usp_bar")):
        if isinstance(it, dict):
            for f in ("label", "text"):
                if isinstance(it.get(f), str) and it[f]:
                    yield f"usp_bar.{f}", it[f]
    trust = cfg.get("trust")
    if isinstance(trust, dict):
        for m in _list(trust.get("marks")):
            if isinstance(m, str) and m:
                yield "trust.marks", m
    for it in _list(cfg.get("before_after")):
        if isinstance(it, dict) and isinstance(it.get("text"), str) and it["text"]:
            yield "before_after.text", it["text"]


def translated(cfg):
    """Переведённые строки этих ключей: {текст: язык}; перевод, равный базе того же
    конфига (имя, «Bio»), не признак."""
    if not isinstance(cfg, dict):
        return {}
    own = {t for _w, t in texts(cfg)}
    out = {}
    i18n = cfg.get("i18n")
    for loc, node in i18n.items() if isinstance(i18n, dict) else ():
        if not isinstance(node, dict):
            continue
        for _w, t in texts({k: node.get(k) for k in KEYS}):
            if t not in own:
                out.setdefault(t, str(loc))
    return out


def scan(cfg):
    """Counter{(ключ, язык или 'не немецкий'): число} — без текстов."""
    cfg = cfg if isinstance(cfg, dict) else {}
    tr = translated(cfg)
    history = cfg.get("history")
    for snap in history if isinstance(history, list) else []:
        if isinstance(snap, dict) and isinstance(snap.get("config"), dict):
            for t, loc in translated(snap["config"]).items():
                tr.setdefault(t, loc + " (history)")
    hits = Counter()
    for where, text in texts(cfg):
        if text in tr:
            hits[(where, tr[text])] += 1
        elif NON_DE.search(text):
            hits[(where, "не немецкий")] += 1
    return hits


class Command(BaseCommand):
    help = "Только чтение: тенанты, у которых немецкая база USP/знаков доверия/«Vorher & nachher» похожа на перевод (FB-33 D9)."

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        found, total = [], 0
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute("SET TRANSACTION READ ONLY")
            qs = Tenant.objects.exclude(schema_name="public").only(
                "pk", "schema_name", "slug", "site_config"
            )
            for tenant in qs.iterator(chunk_size=200):
                total += 1
                hits = scan(tenant.site_config)
                if hits:
                    found.append((tenant.schema_name, tenant.slug, hits))
        for schema, slug, hits in found:
            self.stdout.write(f"{schema} ({slug}):")
            for (where, loc), n in sorted(hits.items()):
                self.stdout.write(f"    {where} — {loc}: {n}")
        self.stdout.write(f"найдено: {len(found)} из {total} тенантов")
