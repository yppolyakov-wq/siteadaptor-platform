"""P0-2 (аудит 2026-09-03 §9.3): раздача /media/ с deny-list'ом приватных префиксов.

Один MEDIA_ROOT на всех бизнесов, без префикса схемы; в проде без S3 файлы
отдаёт сам Django (`SERVE_MEDIA=True`), Caddy лишь проксирует. Голый
`django.views.static.serve` стоял в трёх urlconf (tenant/public/portal) и
отдавал с ЛЮБОГО хоста всё подряд — в том числе загрузки мастера импорта
(прайсы клиентов, путь раньше совпадал с исходным именем файла) и шифротексты
документов участников.

Это минимальный гейт, не изоляция: публичные префиксы (фото товаров/номеров/
логотипы — uuid-имена) остаются доступны как были. Настоящая изоляция (префикс
схемы в путях + проверка «файл принадлежит хосту») — отдельная волна. Режим S3
(`SERVE_MEDIA=False`) этой вьюхи не касается: там раздаёт бакет, и приватность
префиксов — вопрос его политики (в бэклоге той же волны).
"""

import os

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.utils._os import safe_join
from django.views.static import serve as static_serve

#: Первый сегмент пути, который НЕ отдаём напрямую: загрузки импорта и документы
#: (у документов есть своя proxy-вьюха в apps.documents — с проверкой доступа и
#: расшифровкой).
PRIVATE_PREFIXES = frozenset({"imports", "documents"})

#: Инвентарь папок, которые отдаём напрямую. Для большинства это безопасно —
#: витринные фото и логотипы и так публичны. Две папки помечены отдельно: они
#: принадлежат закрытым поверхностям и остаются публичными по ссылке осознанно,
#: до отдельной волны с proxy-вьюхами (см. комментарии ниже).
#: Замок `test_every_upload_folder_is_classified` сверяет литералы `folder=`/
#: `upload_to=` в коде с объединением обоих множеств: новая папка обязана быть
#: осознанно отнесена к публичным или приватным, иначе тест красный.
PUBLIC_PREFIXES = frozenset(
    {
        "products",
        "variants",
        "categories",
        "combos",
        "collections",
        # ⚠️ Лента заезда (MT-3) закрыта: гид | владелец билета | приглашённый
        # (apps/community/access.py::role_of). Фото участников здесь ПУБЛИЧНЫ по
        # ссылке — как job_photos: имя uuid, но авторизации нет. Не приватим
        # сейчас осознанно: без proxy-вьюхи 404 сломал бы показ и законным
        # участникам (в шаблоне стоит прямой {{ img.url }}). Гейт по role_of —
        # roadmap §Отложено, вместе с гейтом «файл принадлежит хосту».
        "community",
        "services",
        "stays",
        "events",
        "tours",
        "blog",
        "posts",
        "promotions",
        "hero",
        "extras",
        "logo",
        "gallery",
        "cover",
        "cblock",
        # Фото к заявке (/anfrage/): имя — uuid (jobs.services.save_job_photos),
        # кабинет ссылается на файл напрямую; proxy-вьюха — та же отдельная волна.
        "job_photos",
    }
)


def serve_media(request, path, document_root=None):
    """Гейт по пути, РЕШЁННОМУ ОТНОСИТЕЛЬНО КОРНЯ, а не по сырой строке.

    Первая версия проверяла префикс после `posixpath.normpath`, но тот
    сохраняет ведущие `..`: `../media/imports/x.csv` не начинается с `imports/`,
    а `safe_join` в static.serve сворачивал его в `<root>/imports/x.csv` — и
    отдавал (поймано ревью плана). Поэтому сначала `safe_join` (выход за корень
    → 404, а не 400: существование ничего не подтверждаем), затем relpath от
    корня и проверка ПЕРВОГО сегмента.
    """
    root = os.path.abspath(str(document_root or settings.MEDIA_ROOT))
    try:
        full = safe_join(root, path)
    except (SuspiciousFileOperation, ValueError):
        raise Http404 from None
    rel = os.path.relpath(full, root)
    if rel == os.curdir or rel.split(os.sep, 1)[0] in PRIVATE_PREFIXES:
        raise Http404
    return static_serve(request, rel, document_root=root)
