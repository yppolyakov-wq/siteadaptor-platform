"""Ответ модели → JSON по схеме задачи (jsonschema). Ошибка формулируется БЕЗ данных:
путь + правило схемы — её можно вернуть модели для повтора и записать в лог."""

from __future__ import annotations

import json
import re

import jsonschema

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class Invalid(ValueError):
    pass


def parse(text: str, schema: dict):
    m = _FENCE.match(text or "")
    raw = m.group(1) if m else (text or "").strip()
    try:
        data = json.loads(raw)
    except ValueError:
        raise Invalid("response is not valid JSON") from None
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(data), key=str)
    if errors:
        err = errors[0]
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        raise Invalid(f"{path}: violates '{err.validator}' = {json.dumps(err.validator_value)}")
    return data


def instruction(schema: dict) -> str:
    return (
        "Reply with a single valid JSON object only (no Markdown, no explanation) that "
        "matches this JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
    )
