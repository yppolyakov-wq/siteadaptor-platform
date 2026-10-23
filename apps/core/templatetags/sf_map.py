"""В3: `{% sf_map_loader %}` — общий загрузчик подложки карт (Leaflet + MapLibre GL +
плагин maplibre-gl-leaflet, векторный стиль из settings.MAP_STYLE_URL).

Тег, а не context processor: карты живут на трёх urlconf (витрина бизнеса, портал
города, /entdecken/), а набор процессоров у них разный. Выводит только статический
конфиг без персональных данных — публичный кэш страниц (P0-1) он не ломает.
"""

from django import template
from django.conf import settings

register = template.Library()

# Точные версии + SRI (sha384/sha256 посчитаны по файлам; leaflet — хеши 1.9.4, опубликованные
# проектом). KA-12 E0.1: файлы лежат у нас (`static/vendor/…`), а не на unpkg.com — IP посетителя
# не уходит третьей стороне (DSGVO); SRI оставлен: подмена файла в статике тоже не исполнится.
# Новая версия = новый файл + новый хеш. maplibre-gl держим на 5.x: с 6.0 пакет только ES-модули
# (нет dist/maplibre-gl.js), а плагин maplibre-gl-leaflet ждёт глобальный `maplibregl` (UMD).
MAP_ASSETS = (
    {
        "kind": "css",
        "lib": "leaflet",
        "version": "1.9.4",
        "path": "vendor/leaflet/leaflet.css",
        "integrity": "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=",
    },
    {
        "kind": "js",
        "lib": "leaflet",
        "version": "1.9.4",
        "path": "vendor/leaflet/leaflet.js",
        "integrity": "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=",
    },
    {
        "kind": "css",
        "lib": "maplibre-gl",
        "version": "5.9.0",
        "path": "vendor/maplibre/maplibre-gl.css",
        "integrity": "sha384-gNYNsUmuZqDYiT3gbirWTV5K7rt71RoveS/yXAaU09d4ZUmeDVTD3XoqB6uJAIFR",
    },
    {
        "kind": "js",
        "lib": "maplibre-gl",
        "version": "5.9.0",
        "path": "vendor/maplibre/maplibre-gl.js",
        "integrity": "sha384-81ppUWZZO+pveTPk4qU9cZuScEFULHfuOMHVJHFZ7xVBlWQTG1zsPrVIMGAl1WMb",
    },
    {
        "kind": "js",
        "lib": "maplibre-gl-leaflet",
        "version": "0.1.4",
        "path": "vendor/maplibre/leaflet-maplibre-gl.js",
        "integrity": "sha384-tXYNKOHx4T02jMP7YYCtBxPIv1B5gaA5mcVPBzqMp6d7VzWzxJgI2aWF/nJLrQdS",
    },
)


def _assets() -> list[dict]:
    from django.templatetags.static import static

    return [
        {"kind": a["kind"], "lib": a["lib"], "url": static(a["path"]), "integrity": a["integrity"]}
        for a in MAP_ASSETS
    ]


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
        "assets": _assets(),
    }
    return {"sf_map_config": config, "sf_map_config_json": json.dumps(config)}
