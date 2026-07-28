"""S3-обложка архетипа. Фидбэк владельца 2026-07-28: вместо трёх блоков
(баннер → абзац → snap-галерея) — ОДИН узкий слайдер с пагинацией, текстом
и кнопкой на нём. Слайды собирает контекст-процессор (hero + галерея)."""

from django.template.loader import render_to_string


def _render(cover):
    return render_to_string("storefront/_archetype_cover.html", {"archetype_cover": cover})


def test_cover_is_single_slider_with_text_button_and_dots():
    out = _render(
        {
            "intro": "Unsere Retreats",
            "slides": ["/hero.svg", "/a.svg", "/b.svg"],
            "button_label": "",
            "button_url": "",
        }
    )
    assert out.count("<section") == 1  # один блок, не баннер+текст+галерея
    # атрибуты считаем по закрывающей скобке/пробелу — JS-селекторы не мешают
    assert "data-cover-hero" in out and out.count("data-cover-slide>") == 3
    assert out.count("data-cover-dot ") == 3  # пагинация
    assert "Unsere Retreats" in out  # текст НА слайдере
    assert 'href="#cover-ende"' in out  # дефолтная кнопка — якорь вниз
    assert "snap-x" not in out  # старой отдельной галереи больше нет


def test_cover_custom_button_and_single_slide_without_dots():
    out = _render(
        {
            "intro": "",
            "slides": ["/hero.svg"],
            "button_label": "Zimmer ansehen",
            "button_url": "/unterkunft/",
        }
    )
    assert 'href="/unterkunft/"' in out and "Zimmer ansehen" in out
    assert "data-cover-dot" not in out  # один слайд — без пагинации/JS
    assert "<script" not in out


def test_cover_text_only_keeps_plain_paragraph():
    out = _render({"intro": "Nur Text", "slides": []})
    assert "data-cover-hero" not in out
    assert "Nur Text" in out


def test_cover_empty_renders_nothing_meaningful():
    out = _render({})
    assert "data-cover-hero" not in out
    assert "<section" not in out
