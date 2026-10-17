"""Общий формат запроса/ответа адаптеров: у всех провайдеров один контракт."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Image:
    mime: str  # image/jpeg | image/png | image/webp
    data: bytes

    @property
    def fmt(self) -> str:
        return self.mime.split("/", 1)[1]


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    prompt: str
    system: str = ""
    images: tuple[Image, ...] = ()
    max_tokens: int = 1024
    temperature: float | None = None
    timeout_s: int = 30
    json_mode: bool = False
    task: str = ""  # только для фейка/учёта, наружу не уходит


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    extra: dict = field(default_factory=dict)


class Provider:
    """Адаптер провайдера. `eu_for(model)` — обрабатывает ли маршрут данные в ЕС при этой
    модели/настройке; `call` бросает только ошибки из apps.ai.errors."""

    name = ""

    def eu_for(self, model: str) -> bool:  # pragma: no cover — переопределяется
        return False

    def call(self, req: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise NotImplementedError
