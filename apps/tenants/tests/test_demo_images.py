"""PR-IMG: локальные самодостаточные демо-фото (SVG-генератор).

Внешние фото-сервисы недоступны/внешние (GDPR) → демо-картинки рендерим локально.
Детерминированы по keyword+lock; отдаёт storefront-вьюха demo-image.
"""

from django.test import RequestFactory

from apps.tenants import demo_images
from apps.tenants.demo_kits import demo_image


def test_svg_is_wellformed_and_themed():
    svg = demo_images.svg_for("vegan,burger", w=800, h=600, lock=1)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert 'width="800"' in svg and 'height="600"' in svg
    assert "🍔" in svg  # эмодзи бургера
    assert "Vegan" in svg  # подпись (первое слово ключа)


def test_svg_deterministic_by_keyword_and_lock():
    a = demo_images.svg_for("vegan,pizza", lock=3)
    b = demo_images.svg_for("vegan,pizza", lock=3)
    c = demo_images.svg_for("vegan,pizza", lock=4)
    assert a == b  # тот же ключ+lock → та же картинка
    assert a != c  # другой lock → другой градиент


def test_emoji_fallbacks():
    assert "🌿" in demo_images.svg_for("vegan,unknownthing")  # веган-фолбэк
    assert "🍽️" in demo_images.svg_for("etwas,anderes")  # общий фолбэк


def test_small_image_has_no_caption():
    # Аватарки/иконки (<200px) — без подписи, только эмодзи.
    svg = demo_images.svg_for("portrait,woman", w=120, h=120, lock=5)
    assert "<text" in svg  # эмодзи есть
    assert "Portrait" not in svg  # подписи нет


def test_caption_is_xml_escaped():
    # Спецсимволы ключа не ломают XML (санитайз + экранирование).
    svg = demo_images.svg_for("<script>,x", w=400, h=300)
    assert "<script>" not in svg


def test_clamps_out_of_range_size():
    svg = demo_images.svg_for("burger", w=999999, h=-5)
    assert 'width="2400"' in svg and 'height="16"' in svg  # клампы к границам (hi/lo)


def test_demo_image_url_is_local():
    # есть реальное фото → static-файл; нет → SVG-вьюха. В обоих случаях локально.
    url = demo_image("vegan, burger", w=400, h=300, lock=2)
    assert url.startswith(("/static/demo/photos/", "/medien/demo.svg?"))
    assert "loremflickr" not in url
    url_svg = demo_image("unfotografiertes-motiv", w=400, h=300, lock=2)
    assert url_svg.startswith("/medien/demo.svg?")
    assert "kw=unfotografiertes-motiv" in url_svg and "lock=2" in url_svg


def test_view_returns_svg_response():
    request = RequestFactory().get("/medien/demo.svg", {"kw": "vegan,bowl", "w": "400", "h": "300"})
    resp = demo_images.demo_image_view(request)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/svg+xml"
    assert b"<svg" in resp.content
    assert "max-age" in resp["Cache-Control"]


# --- Реальные фото из static/demo/photos/ (решение владельца 2026-07-10) -----
def test_photo_resolver_fallbacks(tmp_path, settings):
    """Резолв: точный slug → токен-фолбэк → lock-вариант; нет файла → None (SVG)."""
    photos = tmp_path / "demo" / "photos"
    photos.mkdir(parents=True)
    (photos / "bread-bakery.webp").write_bytes(b"x")  # точный ключ
    (photos / "cake.jpg").write_bytes(b"x")  # токен-фолбэк
    (photos / "shop-front-2.webp").write_bytes(b"x")  # lock-вариант
    settings.STATICFILES_DIRS = [str(tmp_path)]

    assert demo_images.photo_static_name("bread,bakery") == "bread-bakery.webp"
    assert demo_images.photo_static_name("strawberry,cake") == "cake.jpg"  # по токену
    assert demo_images.photo_static_name("shop,front", lock=2) == "shop-front-2.webp"
    assert demo_images.photo_static_name("shop,front", lock=5) is None  # нет ни варианта,
    # ни базового shop-front.* → SVG


def test_demo_image_url_prefers_photo_over_svg(tmp_path, settings):
    """Есть файл → static-URL фото; нет → прежний SVG-плейсхолдер (фолбэк цел)."""
    photos = tmp_path / "demo" / "photos"
    photos.mkdir(parents=True)
    (photos / "pretzel.webp").write_bytes(b"x")
    settings.STATICFILES_DIRS = [str(tmp_path)]

    assert demo_image("pretzel") == "/static/demo/photos/pretzel.webp"
    assert demo_image("unfotografiert").startswith("/medien/demo.svg?")
