"""T-8.10f: реестр инструментов MCP + проверка входа/выхода по JSON Schema.

Инструмент = имя, описание, схемы входа и выхода, аннотации и обработчик
`handler(arguments, ctx) -> dict` (structuredContent). Ошибка предметной области —
`ToolError` (ответ `isError: true` с понятным текстом), а не исключение протокола.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from django.utils.translation import gettext as _
from jsonschema import Draft202012Validator


class ToolError(Exception):
    """Ошибка предметной области: ассистент получает `isError: true` и этот текст."""


class UnknownTool(LookupError):
    pass


@dataclass(frozen=True)
class Context:
    """Что знает обработчик о запросе: портал (область каталога) и сам запрос."""

    portal: object
    request: object


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Callable[[dict, Context], dict]
    annotations: dict = field(default_factory=dict)
    #: Показывать ли инструмент в `tools/list` сейчас (F-4: действия — только при
    #: настоящей почте). Скрытый инструмент по прямому вызову отвечает своим отказом.
    available: Callable[[], bool] | None = None
    #: Текст отказа для прямого вызова скрытого инструмента (иначе — общий).
    unavailable: Callable[[dict, Context], str] | None = None

    def is_available(self) -> bool:
        return self.available is None or bool(self.available())

    def describe(self) -> dict:
        out = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }
        if self.annotations:
            out["annotations"] = self.annotations
        return out


REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    Draft202012Validator.check_schema(tool.input_schema)
    Draft202012Validator.check_schema(tool.output_schema)
    REGISTRY[tool.name] = tool
    return tool


def list_tools() -> list[dict]:
    return [tool.describe() for tool in REGISTRY.values() if tool.is_available()]


def _first_error(schema: dict, value) -> str | None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda e: [str(p) for p in e.path],
    )
    if not errors:
        return None
    from .protocol import clip

    err = errors[0]
    where = clip(".".join(str(p) for p in err.path))
    message = clip(err.message)
    return f"{where}: {message}" if where else message


def call_tool(name: str, arguments, ctx: Context) -> dict:
    """Результат `tools/call`. Неизвестное имя → UnknownTool (ошибка протокола у вызывающего)."""
    tool = REGISTRY.get(name)
    if tool is None:
        raise UnknownTool(name)
    if arguments is None:
        arguments = {}
    problem = _first_error(tool.input_schema, arguments)
    if problem:
        return error_result(_("Ungültige Eingabe — %(problem)s") % {"problem": problem})
    if not tool.is_available():
        # скрытый инструмент обработчик не исполняет — даже если тот забыл проверку
        text = tool.unavailable(arguments, ctx) if tool.unavailable else ""
        return error_result(text or _("Diese Aktion ist gerade nicht verfügbar."))
    try:
        data = tool.handler(arguments, ctx)
    except ToolError as exc:
        return error_result(str(exc))
    # Выход обязан соответствовать объявленной схеме: нарушение — ошибка нашего кода,
    # ассистенту не отдаём кривые данные.
    problem = _first_error(tool.output_schema, data)
    if problem:
        raise ValueError(f"output of {name} violates its schema: {problem}")
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}],
        "structuredContent": data,
        "isError": False,
    }


def error_result(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}
