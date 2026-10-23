"""Общие фикстуры всех тестов."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_ai_config_cache():
    """AI-CFG: кэш настроек ИИ живёт в процессе и пережил бы откат БД между тестами."""
    from apps.ai import config

    config.reset_cache()
    yield
    config.reset_cache()
