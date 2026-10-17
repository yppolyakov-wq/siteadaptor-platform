"""Реестр задач ИИ: каждая задача объявлена здесь (класс модели, схема, лимиты).
Вызова в обход реестра нет — потребитель регистрирует свою задачу через `register`
в `AppConfig.ready()` своего приложения: регистрация при импорте вьюхи/сервиса не
дойдёт до Celery-воркера, который этот модуль не импортировал."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AIConfigError

TIERS = ("fast", "strong")


@dataclass(frozen=True)
class TaskSpec:
    tier: str = "fast"
    max_tokens: int = 1024
    temperature: float | None = None  # None = дефолт провайдера (у части моделей параметра нет)
    timeout_s: int = 30
    allow_images: bool = False
    pii_scrub: bool = True
    max_input_chars: int | None = None  # None = общий AI_MAX_PROMPT_CHARS

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}")


TASKS: dict[str, TaskSpec] = {
    # Живая проверка ключей (`manage.py ai_smoke`): короткий ответ, без данных бизнеса.
    "smoke": TaskSpec(tier="fast", max_tokens=64, allow_images=True, timeout_s=60),
    "smoke_strong": TaskSpec(tier="strong", max_tokens=64, allow_images=True, timeout_s=60),
}


def register(name: str, spec: TaskSpec) -> None:
    """Задача потребителя (T-8.10a, Г1 …). Повторная регистрация того же имени — ошибка
    кода: две разные спецификации под одним именем разъехались бы в учёте."""
    if name in TASKS and TASKS[name] != spec:
        raise ValueError(f"AI task {name!r} already registered differently")
    TASKS[name] = spec


def get(name: str) -> TaskSpec:
    try:
        return TASKS[name]
    except KeyError:
        raise AIConfigError(f"unknown task {name}") from None
