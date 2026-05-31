"""Утилиты чтения CSV и применения маппинга колонок.

Потоковое чтение (csv.reader построчно) — не грузим весь файл в память.
Разделитель: авто-определение (csv.Sniffer) либо явный из options.
"""

import csv
import io

# Поддерживаемые разделители (значение из формы → реальный символ).
DELIMITERS = {
    "auto": None,
    "comma": ",",
    "semicolon": ";",
    "tab": "\t",
    "pipe": "|",
}


def _text(django_file) -> str:
    django_file.open("rb")
    try:
        django_file.seek(0)
    except (OSError, ValueError):
        pass
    raw = django_file.read()
    return raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw


def detect_delimiter(django_file) -> str:
    """Угадать разделитель по первой строке (Sniffer). По умолчанию запятая."""
    text = _text(django_file)
    sample = text.split("\n", 1)[0]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _resolve_delimiter(django_file, delimiter_key: str | None) -> str:
    """Из ключа options → реальный символ. auto/None → авто-определение."""
    if delimiter_key and delimiter_key in DELIMITERS and DELIMITERS[delimiter_key]:
        return DELIMITERS[delimiter_key]
    return detect_delimiter(django_file)


def read_headers(django_file, delimiter_key: str | None = None) -> list[str]:
    """Прочитать только строку заголовков CSV."""
    delim = _resolve_delimiter(django_file, delimiter_key)
    reader = csv.reader(io.StringIO(_text(django_file)), delimiter=delim)
    for row in reader:
        return [h.strip() for h in row]
    return []


def read_rows(django_file, delimiter_key: str | None = None):
    """Стримить строки CSV как dict {header: value} (DictReader)."""
    delim = _resolve_delimiter(django_file, delimiter_key)
    reader = csv.DictReader(io.StringIO(_text(django_file)), delimiter=delim)
    for row in reader:
        yield {(k.strip() if k else k): v for k, v in row.items()}


def apply_mapping(raw: dict, mapping: dict) -> dict:
    """Преобразовать строку файла в логические поля по column_mapping.

    mapping: {csv_column -> logical_field}. Колонки без маппинга или с пустым
    логическим полем игнорируются.
    """
    data: dict = {}
    for csv_column, logical_field in mapping.items():
        if not logical_field:
            continue
        value = raw.get(csv_column)
        if value is not None:
            value = value.strip() if isinstance(value, str) else value
        data[logical_field] = value
    return data
