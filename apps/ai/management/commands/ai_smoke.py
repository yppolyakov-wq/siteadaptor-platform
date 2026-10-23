"""Живая проверка ключей ИИ: один короткий вызов на каждый настроенный маршрут.

    python manage.py ai_smoke [--tier fast|strong] [--route mistral] [--image photo.jpg]

Печатает маршрут, модель, ok, токены, мс и стоимость — без ключей и без текста ответа.
Уважает AI_REQUIRE_EU: маршрут вне ЕС проверяется только с --allow-non-eu. На сервере
(без DEBUG) — только текстовая проверка: в модель уходит одна неизменная фраза, ни
данных бизнесов, ни картинок (AI-1, 2026-10-23: владелец проверяет ключ на проде).
Учёт пишется как платформенный (task=smoke)."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from apps.ai import api, routing
from apps.ai.errors import AIError

PROMPT = "Reply with the single word OK."


class Command(BaseCommand):
    help = "Проверить ключи и маршруты ИИ коротким вызовом (без вывода ключей)."

    def add_arguments(self, parser):
        parser.add_argument("--tier", choices=("fast", "strong"), default="fast")
        parser.add_argument("--route", default="", help="только этот маршрут")
        parser.add_argument("--image", default="", help="путь к JPEG/PNG/WebP")
        parser.add_argument("--allow-non-eu", action="store_true")

    def handle(self, *args, tier, route, image, allow_non_eu, **opts):
        if allow_non_eu and image and not settings.DEBUG:
            raise CommandError("--allow-non-eu с --image — только при DEBUG=True.")
        names = [route] if route else routing.configured(tier)
        if not names:
            raise CommandError(f"AI_ROUTE_{tier.upper()} пуст.")
        images = [Path(image).read_bytes()] if image else []
        task = "smoke_strong" if tier == "strong" else "smoke"
        failed = 0
        for name in names:
            key = "AI_ROUTE_STRONG" if tier == "strong" else "AI_ROUTE_FAST"
            overrides = {"AI_ENABLED": True, key: [name]}
            if allow_non_eu:
                overrides["AI_REQUIRE_EU"] = False
            with override_settings(**overrides):
                try:
                    r = api.generate(task, PROMPT, images=images, tenant="")
                except AIError as exc:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"{name:10} FAIL {exc.code} {exc.detail}"))
                    continue
            price = "" if r.cost_cents else "  (no price in AI_PRICES)"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{name:10} OK   model={r.model} in={r.tokens_in} out={r.tokens_out} "
                    f"ms={r.duration_ms} cost={r.cost_cents}ct{price}"
                )
            )
        if failed:
            raise CommandError(f"{failed} route(s) failed.")
