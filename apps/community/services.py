"""Правила ленты поездки: кто автор записи, как она создаётся и модерируется."""

from django.db import IntegrityError

from .models import FeedComment, FeedPost, FeedSpace

MAX_BODY = 4000
MAX_IMAGES = 6


def space_for_event(event, *, create=True):
    """Пространство заезда; при `create` заводит его на лету (гид не настраивает)."""
    ref_id = str(event.pk)
    space = FeedSpace.objects.filter(ref_kind="event", ref_id=ref_id).first()
    if space is not None or not create:
        return space
    return FeedSpace.objects.create(
        ref_kind="event",
        ref_id=ref_id,
        title=event.title[:200],
        tg_link_code=_link_code(),
    )


def _link_code() -> str:
    """Короткий код для команды /link в Telegram-группе (MT-3b)."""
    import secrets

    return secrets.token_hex(4)


def _author_kwargs(*, user=None, customer=None, name=""):
    return {
        "author_user": user if (user is not None and user.is_authenticated) else None,
        "author_customer": customer,
        "author_name": (name or "")[:120],
    }


def add_post(
    space,
    *,
    body="",
    kind=FeedPost.KIND_POST,
    user=None,
    customer=None,
    name="",
    images=None,
    document=None,
    source=FeedPost.SOURCE_WEB,
    external_ref="",
):
    """Создать запись ленты/чата.

    Идемпотентность по `external_ref` (message_id Telegram): повторный апдейт от
    мессенджера не создаёт дубль — уникальный индекс ловит гонку, и мы просто
    отдаём уже сохранённую запись.
    """
    if external_ref:
        existing = FeedPost.objects.filter(space=space, external_ref=external_ref).first()
        if existing is not None:
            return existing
    post = FeedPost(
        space=space,
        kind=kind,
        body=(body or "").strip()[:MAX_BODY],
        images=list(images or [])[:MAX_IMAGES],
        document=document,
        source=source,
        external_ref=external_ref[:64],
        **_author_kwargs(user=user, customer=customer, name=name),
    )
    try:
        post.save()
    except IntegrityError:
        # Гонка двух одинаковых апдейтов Telegram — берём победителя.
        return FeedPost.objects.get(space=space, external_ref=external_ref)
    return post


def add_comment(post, *, body, user=None, customer=None, name=""):
    return FeedComment.objects.create(
        post=post,
        body=(body or "").strip()[:MAX_BODY],
        **_author_kwargs(user=user, customer=customer, name=name),
    )


def toggle_hidden(obj) -> bool:
    """Скрыть/показать запись или комментарий (модерация, паттерн CM-6)."""
    obj.is_hidden = not obj.is_hidden
    obj.save(update_fields=["is_hidden", "updated_at"])
    return obj.is_hidden


def visible_posts(space, kind, *, for_staff=False):
    """Записи пространства: гид видит скрытые (помечены), участники — нет."""
    qs = (
        FeedPost.objects.filter(space=space, kind=kind)
        .select_related("author_customer", "author_user", "document")
        .prefetch_related("comments__author_customer", "comments__author_user")
    )
    return qs if for_staff else qs.filter(is_hidden=False)
