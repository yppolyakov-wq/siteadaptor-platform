"""Локальные самодостаточные демо-фото (PR-IMG).

Внешние фото-сервисы (loremflickr/picsum/unsplash) недоступны в защищённых сетях
и являются внешним ресурсом (GDPR-вопрос на витрине). Поэтому демо-картинки
генерируем локально как тематические SVG: градиент (детерминирован по ключевому
слову+lock) + крупное эмодзи блюда/темы + подпись. Отдаёт сам storefront (вьюха
`demo_image_view`), без внешних зависимостей — грузится везде и GDPR-чисто.

`demo_kits.demo_image()` возвращает URL на эту вьюху; FileRef-конверты товаров/
галерей/баннеров ссылаются на неё. Изображение встраивается как <img src>, скрипт
в таком SVG не исполняется; подпись санитайзится и XML-экранируется.
"""

import hashlib
from urllib.parse import urlencode

# Путь вьюхи (маршрут `demo-image` в urls_tenant). Хардкод — demo_image() строит
# URL на этапе сидинга, без request/reverse.
DEMO_IMAGE_PATH = "/medien/demo.svg"

# Тема → эмодзи. Подбор по подстроке ключевого слова (первое совпадение), иначе
# фолбэк по «вегану»/общий. Ключи — латиницей, как в demo-kit keywords.
_EMOJI = [
    ("burger", "🍔"),
    ("pizza", "🍕"),
    ("pita", "🥙"),
    ("wrap", "🌯"),
    ("falafel", "🧆"),
    ("pakora", "🧆"),
    ("kofta", "🍢"),
    ("schaschlik", "🍢"),
    ("skewer", "🍢"),
    ("hotdog", "🌭"),
    ("hot,dog", "🌭"),
    ("sausage", "🌭"),
    ("wurst", "🥓"),
    ("salami", "🥓"),
    ("aufschnitt", "🥓"),
    ("nori", "🍣"),
    ("sushi", "🍣"),
    ("bowl", "🥗"),
    ("salad", "🥗"),
    ("curry", "🍛"),
    ("dal", "🍛"),
    ("rice", "🍚"),
    ("pasta", "🍝"),
    ("lasagne", "🍝"),
    ("noodle", "🍜"),
    ("soup", "🍲"),
    ("chili", "🌶️"),
    ("oats", "🥣"),
    ("smoothie", "🥤"),
    ("juice", "🥤"),
    ("coffee", "☕"),
    ("tea", "🍵"),
    ("fries", "🍟"),
    ("potato", "🥔"),
    ("cake", "🍰"),
    ("torte", "🍰"),
    ("muffin", "🧁"),
    ("cupcake", "🧁"),
    ("cookie", "🍪"),
    ("keks", "🍪"),
    ("chocolate", "🍫"),
    ("praline", "🍫"),
    ("donut", "🍩"),
    ("bread", "🍞"),
    ("brot", "🍞"),
    ("konditorei", "🍰"),
    ("dessert", "🍮"),
    ("yoga", "🧘"),
    ("meditation", "🧘"),
    ("retreat", "🏕️"),
    ("forest", "🌲"),
    ("wald", "🌲"),
    ("nature", "🌿"),
    ("campfire", "🔥"),
    ("buffet", "🍽️"),
    ("catering", "🍽️"),
    ("table", "🍽️"),
    ("restaurant", "🍽️"),
    ("festival", "🎪"),
    ("cooking", "👩‍🍳"),
    ("chef", "👩‍🍳"),
    ("cook", "👨‍🍳"),
    ("woman", "👩"),
    ("man", "👨"),
    ("portrait", "🙂"),
    ("logo", "🌿"),
    ("seal", "🏅"),
    ("hotel", "🏨"),
    ("room", "🛏️"),
    ("lake", "🏞️"),
    ("terrace", "⛱️"),
    ("breakfast", "🥐"),
]

# Палитры градиентов (тёплые/свежие/зелёные) — выбор детерминирован по хэшу.
_PALETTES = [
    ("#16a34a", "#86efac"),  # зелёный (веган)
    ("#f59e0b", "#fde68a"),  # янтарь
    ("#ef4444", "#fca5a5"),  # томат
    ("#0e7490", "#67e8f9"),  # cyan
    ("#7c3aed", "#c4b5fd"),  # фиолет
    ("#d97706", "#fcd34d"),  # карри
    ("#059669", "#6ee7b7"),  # изумруд
    ("#db2777", "#f9a8d4"),  # ягода
]


def _emoji_for(keyword: str) -> str:
    kw = keyword.lower()
    for needle, emoji in _EMOJI:
        if needle in kw:
            return emoji
    return "🌿" if "vegan" in kw else "🍽️"


def _caption(keyword: str) -> str:
    """Первое «слово» ключа (до запятой), капитализированное, безопасное для XML."""
    head = keyword.replace(",", " ").split()
    word = head[0] if head else ""
    word = "".join(ch for ch in word if ch.isalnum() or ch in " -")[:24]
    return word.capitalize()


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _clamp(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def svg_for(keyword: str, *, w: int = 800, h: int = 600, lock: int = 1) -> str:
    """Сгенерировать тематический SVG-плейсхолдер (детерминирован по keyword+lock)."""
    w = _clamp(w, 16, 2400, 800)
    h = _clamp(h, 16, 2400, 600)
    lock = _clamp(lock, 0, 10**6, 1)
    digest = hashlib.md5(f"{keyword}|{lock}".encode()).hexdigest()
    c1, c2 = _PALETTES[int(digest[:4], 16) % len(_PALETTES)]
    emoji = _emoji_for(keyword)
    caption = _xml_escape(_caption(keyword))
    short = min(w, h)
    emoji_size = round(short * 0.42)
    cap_size = max(11, round(short * 0.075))
    # Подпись — только если фото достаточно крупное (иконкам/аватаркам не нужна).
    cap = (
        f'<text x="50%" y="76%" text-anchor="middle" font-size="{cap_size}" '
        f'fill="#ffffff" fill-opacity="0.92" font-family="system-ui,Segoe UI,Roboto,'
        f'Helvetica,Arial,sans-serif" font-weight="600">{caption}</text>'
        if caption and short >= 200
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>'
        f"</linearGradient></defs>"
        f'<rect width="{w}" height="{h}" fill="url(#g)"/>'
        f'<text x="50%" y="{"46%" if cap else "50%"}" text-anchor="middle" '
        f'dominant-baseline="central" font-size="{emoji_size}">{emoji}</text>'
        f"{cap}</svg>"
    )


# --- Реальные фото (решение владельца 2026-07-10: CC0/AI-набор) --------------
# Фото кладутся в static/demo/photos/ (см. README там). Резолв по ключевому слову:
#   1) <slug>-<lock>.<ext> (вариант для галерей:同 keyword, разный lock)
#   2) <slug>.<ext>        (точный ключ: "bread,bakery" → bread-bakery.webp)
#   3) <token>.<ext>       (по токенам ключа: "bread,rolls" → bread.webp)
# Ничего нет → тематический SVG (как раньше). URL пишется в FileRef при СИДИНГЕ:
# добавили фото → перезалить демо (`seed_demo_tenants --recreate`).
_PHOTO_DIR = "demo/photos"
_PHOTO_EXTS = (".webp", ".jpg", ".jpeg", ".png")


def _kw_slug(text: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower().strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def photo_static_name(keyword: str, *, lock: int = 1) -> str | None:
    """Имя файла в static/demo/photos/ для ключа (или None → SVG-фолбэк).

    Ищет через staticfiles.finders (работает в dev и на сервере до/после
    collectstatic). Любая ошибка → None (сидинг не должен падать из-за фото).
    """
    try:
        from django.contrib.staticfiles import finders

        slug = _kw_slug(keyword)
        candidates = [f"{slug}-{lock}"] if lock and lock != 1 else []
        candidates.append(slug)
        candidates += [_kw_slug(t) for t in keyword.split(",") if _kw_slug(t) != slug]
        for name in candidates:
            if not name:
                continue
            for ext in _PHOTO_EXTS:
                if finders.find(f"{_PHOTO_DIR}/{name}{ext}"):
                    return f"{name}{ext}"
    except Exception:  # noqa: BLE001 — нет staticfiles/настроек → SVG
        return None
    return None


def demo_image_url(keyword: str, *, w: int = 800, h: int = 600, lock: int = 1) -> str:
    """URL локальной демо-картинки (для FileRef в демо-китах): реальное фото из
    static/demo/photos/ (если положено) или тематический SVG-плейсхолдер."""
    photo = photo_static_name(keyword, lock=lock)
    if photo:
        from django.templatetags.static import static

        return static(f"{_PHOTO_DIR}/{photo}")
    qs = urlencode({"kw": keyword, "w": w, "h": h, "lock": lock})
    return f"{DEMO_IMAGE_PATH}?{qs}"


def demo_image_view(request):
    """Storefront-вьюха: отдать тематический SVG-плейсхолдер (PR-IMG). Без БД,
    кэшируется агрессивно (контент детерминирован параметрами)."""
    from django.http import HttpResponse

    svg = svg_for(
        request.GET.get("kw", "")[:80],
        w=request.GET.get("w"),
        h=request.GET.get("h"),
        lock=request.GET.get("lock"),
    )
    resp = HttpResponse(svg, content_type="image/svg+xml")
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
