"""SR-3: замки санитайзера rich-text описаний (allowlist тулбара)."""

from apps.core import richtext
from apps.core.templatetags.richtext import rich_text


def test_sanitize_keeps_allowlist_and_drops_danger():
    dirty = (
        "<p>Hallo <b>fett</b> <i>kursiv</i></p>"
        "<script>alert(1)</script>"
        '<ul><li onclick="x()">eins</li></ul>'
        '<img src="x.png"><style>p{}</style>'
    )
    out = richtext.sanitize(dirty)
    assert "<b>fett</b>" in out and "<i>kursiv</i>" in out and "<li>eins</li>" in out
    assert "<script" not in out and "alert(1)" not in out
    assert "onclick" not in out and "<img" not in out and "<style" not in out


def test_sanitize_links_get_rel_and_scheme_filter():
    out = richtext.sanitize('<a href="https://x.de">ok</a><a href="javascript:x()">no</a>')
    assert 'href="https://x.de"' in out and "noopener" in out
    assert "javascript:" not in out


def test_sanitize_empty_and_non_string():
    assert richtext.sanitize("") == ""
    assert richtext.sanitize(None) == ""
    assert richtext.sanitize("   ") == ""


def test_is_rich_detects_markup_only():
    assert richtext.is_rich("<b>x</b>") and richtext.is_rich("<ul><li>a</li></ul>")
    # плоский текст (в т.ч. с «<» как символом сравнения) — не rich
    assert not richtext.is_rich("Brot & Butter\nfrisch")
    assert not richtext.is_rich("Preis < 5 €")
    assert not richtext.is_rich(None)


def test_rich_text_filter_is_safe_and_sanitized():
    out = rich_text("<b>x</b><script>y</script>")
    assert str(out) == "<b>x</b>"
    # mark_safe: рендер без экранирования
    from django.template import Context, Template

    html = Template("{% load richtext %}{{ v|rich_text }}").render(
        Context({"v": "<b>ja</b><script>nein</script>"})
    )
    assert html == "<b>ja</b>"
