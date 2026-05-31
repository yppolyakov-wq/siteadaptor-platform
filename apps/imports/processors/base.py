"""Базовый процессор импорта.

Каждый процессор реализует validate() (dry-run, без записи) и
create_or_update() (запись). Реестр по resource_type — в processors/__init__.py.
"""


class BaseProcessor:
    model = None

    def validate(self, data: dict) -> list[str]:
        """Вернуть список ошибок для строки. Пустой список — строка валидна."""
        raise NotImplementedError

    def create_or_update(self, data: dict, *, update_existing: bool, match_field: str = "sku"):
        """Создать или обновить объект по данным строки. Вернуть объект.

        match_field — по какому полю искать существующий объект при
        update_existing (поле синхронизации).
        """
        raise NotImplementedError
