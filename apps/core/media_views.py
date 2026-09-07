"""P0-2 (аудит 2026-09-03 §9.3): раздача /media/ с deny-list'ом приватных префиксов.

Один MEDIA_ROOT на всех бизнесов, без префикса схемы; в проде без S3 файлы
отдаёт сам Django (`SERVE_MEDIA=True`), Caddy лишь проксирует. Голый
`django.views.static.serve` стоял в трёх urlconf (tenant/public/portal) и
отдавал с ЛЮБОГО хоста всё подряд — в том числе загрузки мастера импорта
(прайсы клиентов, путь раньше совпадал с исходным именем файла) и шифротексты
документов участников.

Это минимальный гейт, не изоляция: публичные префиксы (фото товаров/номеров/
логотипы — uuid-имена) остаются доступны как были. Настоящая изоляция (префикс
схемы в путях + проверка «файл принадлежит хосту») — отдельная волна.
"""

import posixpath

from django.conf import settings
from django.http import Http404
from django.views.static import serve as static_serve

#: Что НЕ отдаём напрямую: загрузки импорта и документы (у документов есть
#: своя proxy-вьюха в apps.documents — с проверкой доступа и расшифровкой).
PRIVATE_PREFIXES = ("imports/", "documents/")


def serve_media(request, path, document_root=None):
    # Нормализуем ДО проверки — ровно так же, как это делает static.serve:
    # иначе `./imports/x`, `products/../imports/x` и `/imports/x` обошли бы
    # префикс, а до файла всё равно бы дошли.
    normalized = posixpath.normpath(path).lstrip("/")
    if normalized.startswith(PRIVATE_PREFIXES) or normalized in ("imports", "documents"):
        raise Http404
    return static_serve(request, normalized, document_root=document_root or settings.MEDIA_ROOT)
