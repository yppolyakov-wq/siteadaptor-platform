"""T1: разбор video-URL для галереи (GDPR-дружелюбный embed)."""

from apps.tenants import video


def test_youtube_variants_to_nocookie_embed():
    for url in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ):
        info = video.embed_info(url)
        assert info["kind"] == "youtube"
        assert info["src"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"


def test_vimeo_to_player():
    info = video.embed_info("https://vimeo.com/123456789")
    assert info["kind"] == "vimeo"
    assert info["src"] == "https://player.vimeo.com/video/123456789"


def test_direct_file_is_video():
    info = video.embed_info("https://cdn.example.de/clip.mp4")
    assert info["kind"] == "file"


def test_unknown_url_is_link():
    assert video.embed_info("https://example.de/page")["kind"] == "link"


def test_empty_is_none():
    assert video.embed_info("") is None
    assert video.embed_info(None) is None
