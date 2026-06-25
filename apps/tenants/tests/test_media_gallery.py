"""M20U-G: переиспользуемая галерея детальной (большое фото + миниатюры, свап).

Чистый рендер партиала — принимает список URL или dict'ов {url}, первая фото —
большая, остальные миниатюры с data-src для свапа на месте.
"""

from django.template.loader import render_to_string


def test_gallery_renders_main_and_thumbs_from_urls():
    html = render_to_string(
        "storefront/_media_gallery.html",
        {"images": ["https://x/a.jpg", "https://x/b.jpg", "https://x/c.jpg"]},
    )
    assert 'src="https://x/a.jpg"' in html  # первая = большая
    assert html.count("data-src=") == 3  # 3 миниатюры (data-src на кнопке)
    assert 'data-src="https://x/b.jpg"' in html  # свап по data-src


def test_gallery_accepts_dict_images():
    html = render_to_string(
        "storefront/_media_gallery.html",
        {"images": [{"url": "https://x/a.jpg"}, {"url": "https://x/b.jpg"}]},
    )
    assert 'src="https://x/a.jpg"' in html
    assert 'data-src="https://x/b.jpg"' in html


def test_gallery_single_image_no_thumb_strip():
    html = render_to_string("storefront/_media_gallery.html", {"images": ["https://x/a.jpg"]})
    assert 'src="https://x/a.jpg"' in html
    assert "data-src=" not in html  # одна фото — без полосы миниатюр


def test_gallery_empty_renders_nothing():
    html = render_to_string("storefront/_media_gallery.html", {"images": []})
    assert "js-media-gallery" not in html.strip()


# A.4 (T-E): полноэкранный лайтбокс


def test_gallery_has_lightbox_and_zoom():
    html = render_to_string(
        "storefront/_media_gallery.html",
        {"images": ["https://x/a.jpg", "https://x/b.jpg"]},
    )
    assert "js-media-zoom" in html and "cursor-zoom-in" in html  # клик по фото → лайтбокс
    assert "js-lb" in html and "js-lb-img" in html
    assert "js-lb-prev" in html and "js-lb-next" in html  # навигация при >1 фото


def test_gallery_single_image_still_has_lightbox():
    html = render_to_string("storefront/_media_gallery.html", {"images": ["https://x/only.jpg"]})
    assert "js-media-zoom" in html and "js-lb-img" in html  # лайтбокс и для одной фото
