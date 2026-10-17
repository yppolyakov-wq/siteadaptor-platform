"""AI-0: общий ИИ-слой платформы (план docs/ai0-layer-plan-2026-10-17.md).

Публичный API — `apps.ai.api`: `generate()`, `is_enabled()`, `AIResult`; ошибки —
`apps.ai.errors`. Провайдер выбирается настройкой (`AI_ROUTE_FAST`/`AI_ROUTE_STRONG`),
не кодом; при `AI_REQUIRE_EU` маршруты вне ЕС не вызываются никогда."""
