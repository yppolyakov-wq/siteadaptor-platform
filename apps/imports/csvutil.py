"""Утилиты чтения CSV и применения маппинга колонок.

Потоковое чтение (csv.reader построчно) — не грузим весь файл в память.
"""

import csv
import io


def _text_stream(django_file):
    """Открыть Django File как текстовый поток с декодированием utf-8-sig."""
    django_file.open("rb")
    try:
        django_file.seek(0)
    except (OSError, ValueError):
        pass
    raw = django_file.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        text = raw
    return io.StringIO(text)


def read_headers(django_file) -> list[str]:
    """Прочитать только строку заголовков CSV."""
    stream = _text_stream(django_file)
    reader = csv.reader(stream)
    for row in reader:
        return [h.strip() for h in row]
    return []


def read_rows(django_file):
    """Стримить строки CSV как dict {header: value} (DictReader)."""
    stream = _text_stream(django_file)
    reader = csv.DictReader(stream)
    for row in reader:
        # нормализуем ключи (убираем BOM/пробелы по краям)
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
