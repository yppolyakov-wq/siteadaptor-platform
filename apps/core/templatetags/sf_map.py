"""В3: `{% sf_map_loader %}` — общий загрузчик подложки карт (Leaflet + MapLibre GL +
плагин maplibre-gl-leaflet, векторный стиль из settings.MAP_STYLE_URL).

Тег, а не context processor: карты живут на трёх urlconf (витрина бизнеса, портал
города, /entdecken/), а набор процессоров у них разный. Выводит только статический
конфиг без персональных данных — публичный кэш страниц (P0-1) он не ломает.
"""

from django import template
from django.conf import settings

register = template.Library()

# Точные версии + SRI (sha384 посчитан по скачанным файлам с проверкой HTTP 200; leaflet —
# хеши 1.9.4, опубликованные проектом). Новая версия = новый хеш, иначе браузер файл не
# исполнит. maplibre-gl держим на 5.x: с 6.0 пакет только ES-модули (нет dist/maplibre-gl.js),
# а плагин maplibre-gl-leaflet ждёт глобальный `maplibregl` (UMD-сборку).
MAP_ASSETS = (
    {
        "kind": "css",
        "url": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "integrity": "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=",
    },
    {
        "kind": "js",
        "url": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        "integrity": "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=",
    },
    {
        "kind": "css",
        "url": "https://unpkg.com/maplibre-gl@5.9.0/dist/maplibre-gl.css",
        "integrity": "sha384-gNYNsUmuZqDYiT3gbirWTV5K7rt71RoveS/yXAaU09d4ZUmeDVTD3XoqB6uJAIFR",
    },
    {
        "kind": "js",
        "url": "https://unpkg.com/maplibre-gl@5.9.0/dist/maplibre-gl.js",
        "integrity": "sha384-81ppUWZZO+pveTPk4qU9cZuScEFULHfuOMHVJHFZ7xVBlWQTG1zsPrVIMGAl1WMb",
    },
    {
        "kind": "js",
        "url": "https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js",
        "integrity": "sha384-tXYNKOHx4T02jMP7YYCtBxPIv1B5gaA5mcVPBzqMp6d7VzWzxJgI2aWF/nJLrQdS",
    },
)


def _attribution() -> str:
    """Атрибуция уходит в innerHTML контрола карты — пропускаем только ссылки (ревью В3:
    значение приходит из env, и подменённая переменная не должна давать XSS на всех
    витринах и порталах)."""
    import nh3

    return nh3.clean(
        settings.MAP_ATTRIBUTION or "",
        tags={"a"},
        attributes={"a": {"href", "target"}},
        url_schemes={"https"},
        link_rel="noopener",
    )


@register.inclusion_tag("core/_map_loader.html", takes_context=True)
def sf_map_loader(context):
    """Конфиг — атрибутом скрипта (экранируется шаблоном), а не json_script с id: на
    странице может быть несколько карт, и второй include не должен плодить дубли id."""
    import json

    config = {
        "style": settings.MAP_STYLE_URL,
        "attribution": _attribution(),
        "assets": list(MAP_ASSETS),
    }
    return {"sf_map_config": config, "sf_map_config_json": json.dumps(config)}
