"""Шаблонные фильтры витрины (site_config UI)."""

from django import template

from apps.tenants import video

register = template.Library()


@register.filter(name="video_embed")
def video_embed(url):
    """URL видео → {"kind","src"} (см. apps.tenants.video.embed_info) или None."""
    return video.embed_info(url)
