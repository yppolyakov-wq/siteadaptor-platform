"""AI-0: единая точка вызова ИИ.

`generate(task, prompt, …)` → `AIResult` или исключение из `apps.ai.errors`. Вызов
СИНХРОННЫЙ (до timeout задачи): тяжёлые задачи потребитель ставит в Celery
(`idempotent_task`), а не держит веб-воркер. Вызывать ВНЕ `transaction.atomic`: иначе
секунды HTTP держат транзакцию вызывающего кода, а её откат унесёт и строки учёта
(платные вызовы пропадут из бюджета). Задачу потребитель регистрирует в `ready()` своего
приложения (`registry.register`) — так её видят и веб, и Celery-воркеры. Порядок: выключатель → реестр задачи →
картинки → лимит → маршруты (правило ЕС) → чистка ПД → провайдер (повтор, резерв) →
схема (один повтор) → учёт. Текст запроса/ответа не логируется и в учёт не пишется."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import connection
from django.utils.translation import gettext_lazy as _

from apps.core.pii import scrub

from . import budget, pricing, registry, routing, usage
from . import images as images_mod
from . import schema as schema_mod
from .errors import AIConfigError, AIDisabled, AIError, AISchemaError, AIUnavailable
from .providers.base import ProviderRequest

logger = logging.getLogger(__name__)

# Пометка для каждого сгенерированного черновика (AI Act ст. 50): потребитель показывает её
# рядом с текстом до подтверждения человеком.
AI_LABEL = _("KI-generiert, bitte prüfen")

ATTEMPTS_PER_ROUTE = 2  # один повтор при 429/5xx/таймауте, затем следующий маршрут
# Потолок всей цепочки (повторы × маршруты × повтор схемы) в долях таймаута задачи:
# timeout у requests — пауза между байтами, а не общее время.
DEADLINE_FACTOR = 3


@dataclass(frozen=True)
class AIResult:
    text: str
    data: object
    provider: str
    model: str
    route: str
    tokens_in: int
    tokens_out: int
    cost_cents: Decimal
    duration_ms: int
    fallback_used: bool
    ai_generated: bool = True


def is_enabled() -> bool:
    return bool(getattr(settings, "AI_ENABLED", False))


def _sleep(attempt: int) -> None:
    time.sleep(min(4.0, 0.5 * 2**attempt) + random.uniform(0, 0.25))


def _tenant(tenant) -> tuple[str, bool]:
    if tenant is None:
        schema = getattr(connection, "schema_name", "") or ""
        tenant = getattr(connection, "tenant", None)
    elif isinstance(tenant, str):
        schema, tenant = tenant, None
    else:
        schema = getattr(tenant, "schema_name", "") or ""
    if schema == "public":
        schema = ""
    return schema, bool(getattr(tenant, "is_demo", False))


def generate(
    task: str,
    prompt: str,
    *,
    schema: dict | None = None,
    images=(),
    system: str = "",
    tenant=None,
) -> AIResult:
    if not is_enabled():
        raise AIDisabled()
    spec = registry.get(task)
    if images and not spec.allow_images:
        raise AIConfigError("images not allowed for task")
    limit = spec.max_input_chars or settings.AI_MAX_PROMPT_CHARS
    if len(prompt or "") + len(system or "") > limit:
        raise AIConfigError("prompt too large")  # до scrub: регулярки на огромном тексте
    imgs = images_mod.prepare(images)
    tenant_schema, is_demo = _tenant(tenant)
    budget.check(tenant_schema)
    routes = routing.routes_for(spec.tier)
    if spec.pii_scrub:
        prompt, system = scrub(prompt), scrub(system)
    if schema is not None:
        system = (system + "\n\n" if system else "") + schema_mod.instruction(schema)

    deadline = time.monotonic() + spec.timeout_s * DEADLINE_FACTOR

    def _call(route, text_prompt, fallback_used):
        if time.monotonic() > deadline:
            raise AIUnavailable("deadline")
        req = ProviderRequest(
            model=route.model,
            prompt=text_prompt,
            system=system,
            images=imgs,
            max_tokens=spec.max_tokens,
            temperature=spec.temperature,
            timeout_s=spec.timeout_s,
            json_mode=schema is not None,
            schema=schema,
            task=task,
        )
        started = time.monotonic()
        meta = dict(
            tenant_schema=tenant_schema,
            is_demo=is_demo,
            task=task,
            route=route.name,
            model=route.model,
            images=len(imgs),
            fallback_used=fallback_used,
        )
        try:
            resp = route.provider.call(req)
        except Exception as raw:
            # Неожиданный сбой адаптера (странный JSON и т.п.) нормализуем БЕЗ цепочки:
            # исходное исключение и его кадры несут промпт и заголовки с ключом.
            exc = raw if isinstance(raw, AIError) else None
            ms = int((time.monotonic() - started) * 1000)
            code = exc.code if exc else "provider_error"
            usage.record(**meta, duration_ms=ms, ok=False, error_code=code)
            logger.info("ai task=%s route=%s ok=0 code=%s ms=%s", task, route.name, code, ms)
            if exc is None:
                logger.warning("ai route=%s unexpected %s", route.name, type(raw).__name__)
                raise AIUnavailable(f"provider error {type(raw).__name__}") from None
            raise
        ms = int((time.monotonic() - started) * 1000)
        model = resp.model or route.model
        cost = pricing.cost_cents(route.model or model, resp.tokens_in, resp.tokens_out)
        usage.record(
            **{**meta, "model": model},
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_cents=cost,
            duration_ms=ms,
        )
        logger.info(
            "ai task=%s route=%s model=%s ok=1 in=%s out=%s ms=%s",
            task,
            route.name,
            model,
            resp.tokens_in,
            resp.tokens_out,
            ms,
        )
        return resp, model, cost, ms

    def _on_route(route, text_prompt, fallback_used):
        """Один логический вызов на маршруте: повтор при 429/5xx/таймауте."""
        for attempt in range(ATTEMPTS_PER_ROUTE):
            try:
                return _call(route, text_prompt, fallback_used)
            except AIUnavailable:  # сюда же AIRateLimited
                if attempt + 1 >= ATTEMPTS_PER_ROUTE:
                    raise
                _sleep(attempt)

    last_exc: AIError = AIUnavailable("no route")
    for index, route in enumerate(routes):
        fallback_used = index > 0
        try:
            resp, model, cost, ms = _on_route(route, prompt, fallback_used)
            data = None
            if schema is not None:
                try:
                    data = schema_mod.parse(resp.text, schema)
                except schema_mod.Invalid as err:
                    retry = (
                        f"{prompt}\n\nYour previous answer was invalid ({err}). "
                        "Reply again with valid JSON only."
                    )
                    resp2, model, cost2, ms2 = _on_route(route, retry, fallback_used)
                    try:
                        data = schema_mod.parse(resp2.text, schema)
                    except schema_mod.Invalid as err2:
                        # Без резерва: дважды невалидный ответ — проблема промпта/схемы задачи.
                        raise AISchemaError(str(err2)) from None
                    resp = type(resp)(
                        text=resp2.text,
                        tokens_in=resp.tokens_in + resp2.tokens_in,
                        tokens_out=resp.tokens_out + resp2.tokens_out,
                        model=model,
                    )
                    cost, ms = cost + cost2, ms + ms2
        except AIUnavailable as exc:
            last_exc = exc
            continue  # маршрут исчерпан → резерв
        except AIConfigError as exc:
            # Сломан ключ/модель ЭТОГО маршрута (401, «key missing») — громко в лог и в
            # резерв: исправный второй маршрут не должен падать из-за первого.
            logger.warning("ai route=%s config error %s — next route", route.name, exc.detail)
            last_exc = exc
            continue
        return AIResult(
            text=resp.text,
            data=data,
            provider=route.name,
            model=model,
            route=route.name,
            tokens_in=resp.tokens_in,
            tokens_out=resp.tokens_out,
            cost_cents=cost,
            duration_ms=ms,
            fallback_used=fallback_used,
        )
    raise last_exc
