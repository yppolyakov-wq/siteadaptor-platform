"""Нормализованные ошибки ИИ-слоя: потребитель ловит `AIError` и показывает ручную
форму. Сообщения короткие и без данных запроса/ответа/ключей — их можно логировать."""


class AIError(Exception):
    code = "error"

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


class AIDisabled(AIError):
    """Слой выключен (`AI_ENABLED=False`)."""

    code = "disabled"


class AIUnavailable(AIError):
    """Провайдер недоступен (сеть, таймаут, 5xx) или нет подходящего маршрута."""

    code = "unavailable"


class AIRateLimited(AIUnavailable):
    """Провайдер ответил 429 / Throttling — повтор и затем резерв."""

    code = "rate_limited"


class AIQuotaExceeded(AIError):
    """Исчерпан наш дневной лимит (бизнеса или платформы)."""

    code = "quota"


class AISchemaError(AIError):
    """Модель дважды вернула ответ, не прошедший схему."""

    code = "schema"


class AIConfigError(AIError):
    """Неверная конфигурация: нет ключа/модели, неизвестная задача, 4xx от провайдера."""

    code = "config"


class AIRefused(AIError):
    """Модель или фильтр провайдера отказались отвечать."""

    code = "refused"


# Ошибки, при которых пробуем ещё раз и затем следующий маршрут.
RETRIABLE = (AIUnavailable,)
