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
    # Фидбэк 2026-07-28: «тарелка» — только для гастро-контекста, иначе нейтраль
    # (в карточке стрижки тарелка выглядела ошибкой).
    assert "🍽️" in demo_images.svg_for("essen,anderes")
    assert "✨" in demo_images.svg_for("etwas,anderes")
    assert "💇" in demo_images.svg_for("hair,styling")  # сервисные темы покрыты
    assert "🚗" in demo_images.svg_for("auto,inspektion")


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
    # Фидбэк 2026-07-28: точного файла нет → берём тематически близкий по префиксу
    # токена (детерминированно), вместо SVG-заглушки.
    assert demo_images.photo_static_name("shop,front", lock=5) == "shop-front-2.webp"
    assert demo_images.photo_static_name("voellig,unbekannt") is None  # группы нет → SVG


def test_demo_image_url_prefers_photo_over_svg(tmp_path, settings):
    """Есть файл → static-URL фото; нет → прежний SVG-плейсхолдер (фолбэк цел)."""
    photos = tmp_path / "demo" / "photos"
    photos.mkdir(parents=True)
    (photos / "pretzel.webp").write_bytes(b"x")
    settings.STATICFILES_DIRS = [str(tmp_path)]

    assert demo_image("pretzel") == "/static/demo/photos/pretzel.webp"
    assert demo_image("unfotografiert").startswith("/medien/demo.svg?")


def test_demo_image_url_survives_manifest_storage(tmp_path, settings):
    """Регресс прод-инцидента 2026-07-10: под ManifestStaticFilesStorage сидинг падал
    (`static()` → Missing manifest entry). demo_image_url обязан строить ПЛОСКИЙ URL
    без обращения к манифесту — не падать и не хешировать (URL живёт в БД)."""
    photos = tmp_path / "demo" / "photos"
    photos.mkdir(parents=True)
    (photos / "bruschetta.webp").write_bytes(b"x")
    settings.STATICFILES_DIRS = [str(tmp_path)]
    # прод-хранилище: .url() потребовал бы манифест и упал бы на несобранном файле
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }
    url = demo_image("bruschetta,tomato")  # не должно кинуть ValueError
    assert url == "/static/demo/photos/bruschetta.webp"  # плоский, без хеша
    assert ".webp" in url and url.count(".") == 1  # нет .<hash>.webp


def test_photo_group_choice_is_stable_per_keyword(tmp_path, settings):
    """Ревью 2026-07-28: член префиксной группы выбирается по КЛЮЧУ, а не по
    lock — вставка позиции в кит не перетасовывает фото у соседей."""
    photos = tmp_path / "demo" / "photos"
    photos.mkdir(parents=True)
    for name in ("hair-salon.webp", "hair-colorist.webp", "hair-oil.webp"):
        (photos / name).write_bytes(b"x")
    settings.STATICFILES_DIRS = [str(tmp_path)]

    # hair-styling/hair-highlights короткозамкнуты _PHOTO_ALIASES — для проверки
    # самой формулы group[seed % len(group)] берём ключ БЕЗ алиаса
    picked = demo_images.photo_static_name("hair,pflege", lock=3)
    assert picked in {"hair-salon.webp", "hair-colorist.webp", "hair-oil.webp"}
    assert picked == demo_images.photo_static_name("hair,pflege", lock=99)  # lock не влияет
    # алиасы ведут на подобранный вручную сюжет
    assert demo_images.photo_static_name("hair,styling", lock=3) == "hair-salon.webp"
    assert demo_images.photo_static_name("hair,highlights", lock=1) == "hair-colorist.webp"


def test_catering_dish_keys_never_borrow_another_dishs_photo():
    """Catering-Welle 2026-08-25: die 49 Gerichtsschlüssel bilden dichte
    Präfix-Gruppen (ragout-, salad-, cucumber-, rice-…). Fehlt für einen
    Schlüssel die eigene Datei, liefert der Präfix-Fallback still das Foto eines
    NACHBARGERICHTS — der Kürbisragout bekäme das der Kürbissuppe, die
    Reisbratlinge das des Gemüsereises. Das sieht aus wie ein Fehler und fällt in
    der Abdeckungsstatistik nicht auf (jeder Treffer zählt dort als «abgedeckt»).

    Erlaubt bleibt der dokumentierte thematische Fallback auf ein GENERISCHES
    Bibliotheksfoto (ein Salat bekommt die Salatschüssel). Verboten ist nur, das
    Foto eines anderen Gerichts DIESER Karte zu zeigen.
    """
    from apps.tenants.demo_kits import KITS

    catering = next(c for c in KITS["pranasy"].categories if c[1] == "catering")
    dishes = [item for child in catering[3] for item in child[2]]
    assert len(dishes) == 49

    def _name(item):
        return item["name"]["de"] if isinstance(item["name"], dict) else item["name"]

    own_files = {}
    for item in dishes:
        found = demo_images.photo_static_name(item["img"])
        slug = demo_images._kw_slug(item["img"])
        if found and found.rsplit(".", 1)[0] == slug:
            own_files[found] = _name(item)

    stolen = []
    for item in dishes:
        found = demo_images.photo_static_name(item["img"])
        if not found:
            continue  # ehrlicher SVG-Platzhalter
        slug = demo_images._kw_slug(item["img"])
        if found.rsplit(".", 1)[0] == slug:
            continue  # eigenes Foto
        if found in own_files:
            stolen.append((_name(item), item["img"], found, own_files[found]))
    assert not stolen, f"Gericht zeigt das Foto eines anderen Gerichts: {stolen}"


def test_catering_placeholders_are_topical_not_a_generic_plate():
    """Фидбэк 2026-08-26 «сгенерируй недостающие изображения блюд».

    Сгенерировать фотографии в этой среде нечем (модели изображений нет), а
    честный CC0-кадр нашёлся не для всех блюд. Тогда минимум — читаемый
    плейсхолдер: реестр эмодзи знал только английские слова, поэтому немецкие
    ключи («schmorkohl», «kürbisragout», «minzsauce») получали общую «тарелку»
    🍽️ или вовсе ✨. Замок держит: у каждого блюда карты — своя тема.
    """
    import re

    from apps.tenants.demo_kits import KITS

    catering = next(c for c in KITS["pranasy"].categories if c[1] == "catering")
    dishes = [item for child in catering[3] for item in child[2]]
    generic = []
    for item in dishes:
        if demo_images.photo_static_name(item["img"]):
            continue  # реальное фото — плейсхолдер не рисуется
        emoji = re.findall(r">([^<>]+)</text>", demo_images.svg_for(item["img"]))
        name = item["name"]["de"] if isinstance(item["name"], dict) else item["name"]
        if not emoji or emoji[0] in ("🍽️", "✨"):
            generic.append((name, item["img"], emoji))
    assert not generic, f"Плейсхолдер без темы: {generic}"


def test_catering_placeholder_caption_reads_like_the_dish():
    """Подпись плейсхолдера = первое слово ключа. Ключи вроде «gekochter,reis»
    давали «Gekochter» — обрывок. Проверяем, что подпись начинается так же, как
    название блюда (или входит в него): случайных слов на витрине нет."""
    import re

    from apps.tenants.demo_kits import KITS

    catering = next(c for c in KITS["pranasy"].categories if c[1] == "catering")
    dishes = [item for child in catering[3] for item in child[2]]
    bad = []
    for item in dishes:
        if demo_images.photo_static_name(item["img"]):
            continue
        parts = re.findall(r">([^<>]+)</text>", demo_images.svg_for(item["img"]))
        caption = parts[1] if len(parts) > 1 else ""
        name = item["name"]["de"] if isinstance(item["name"], dict) else item["name"]
        # Подпись должна складываться из слов НАЗВАНИЯ блюда: «Paneerragout» —
        # это «Paneer» + «Ragout» из «Weißes Ragout mit Paneer», а «Mahabrinjal»
        # к «Mahabridschal» отношения не имеет (чужая транслитерация).
        words = [w for w in re.split(r"[^\wäöüß]+", name.lower()) if len(w) > 2]
        rest = caption.lower()
        changed = True
        while rest and changed:
            changed = False
            for w in sorted(words, key=len, reverse=True):
                if rest.startswith(w):
                    rest, changed = rest[len(w) :], True
                    break
        # хвост может быть НАЧАЛОМ слова названия («Reisbratling» ← «Reisbratlinge»)
        if rest and not any(w.startswith(rest) for w in words):
            bad.append((name, item["img"], caption))
    assert not bad, f"Подпись плейсхолдера не про блюдо: {bad}"
