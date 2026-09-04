"""Волна AMP (2026-09-03): фотографии демо продуктового магазина.

Кит `aktionsmarkt` собирался из ОБЩЕЙ библиотеки `static/demo/photos/`, которая
росла под другие киты. У дискаунтера половина кадров была чужой: средство для
посуды показывало пульверизатор, минеральная вода — стакан, Gouda — ресторанную
сырную тарелку с бокалами вина, молотый кофе — латте-арт, а hero — американский
рынок с ценниками в долларах.

Чинить перезаписью файлов нельзя: 27 из 41 файла общие с bakery/cafe/shop/catering/
restaurant. Поэтому у слотов, которым нужен свой сюжет, появилось собственное
пространство ключей `markt-*`; там, где библиотечное фото и так верное (`bananas`,
`tomatoes`, `butter`, `eggs`, `vegetable,box`, `cheese,wheel`, `fresh-fruit`,
`farm-vegetables`, `orange,juice`), кит продолжает ссылаться на него.

Фидбэк владельца той же датой: (1) убрать из демо туалетную бумагу и бытовую химию —
продуктовый магазин торгует едой; (2) сгенерированные кадры не годятся («много пальцев
и неестественно»). Оба требования держат замки ниже.
"""

import pytest

from apps.tenants import demo_images
from apps.tenants.demo_kits import KITS

PREFIX = "markt-"

# Непищевой ассортимент, который владелец попросил убрать (пункт 1 фидбэка).
NON_FOOD = ("toilettenpapier", "spülmittel", "spuelmittel", "waschmittel", "haushalt")


def _kit_image_keys(kit) -> list[tuple[str, int, str]]:
    """[(keyword, lock, где)] по всем фото-слотам кита — включая кадры карусели
    (`img` списком) и собственные фото акций, которых `demo_photo_report` не знает."""
    out: list[tuple[str, int, str]] = []

    def add(kw, where, lock=1):
        if isinstance(kw, str) and kw.strip():
            out.append((kw, lock, where))

    def add_frames(img, where):
        keys = list(img) if isinstance(img, (list, tuple)) else [img]
        for i, kw in enumerate(keys):
            add(kw, where, lock=1 + i)

    add(kit.hero_image_kw, "hero")
    for h in kit.heroes:
        add(h.get("image_kw"), "hero-Slide")
    for kw in kit.gallery_kw:
        add(kw, "Galerie")

    def walk(entry, path=""):
        here = f"{path}/{entry[0]}" if path else entry[0]
        for item in entry[2]:
            name = item["name"]
            add_frames(item.get("img"), f"Produkt {here}/{name}")
        extra = entry[3] if len(entry) > 3 else []
        if isinstance(extra, str):  # DS-2: 4-й элемент-строка = фото плитки
            add(extra, f"Kachel {here}")
        else:
            for child in extra:
                walk(child, here)
            for tail in entry[4:]:  # KAT-1: у направления фото — последним элементом
                if isinstance(tail, str) and demo_images.photo_static_name(tail):
                    add(tail, f"Kachel {here}")

    for entry in kit.categories:
        walk(entry)

    for i, spec in enumerate(kit.promotions_spec or []):
        title = spec.get("title", f"#{i}")
        if spec.get("image"):
            add(spec["image"], f"Aktion «{title}»")
        for j, kw in enumerate(spec.get("images") or []):
            add(kw, f"Aktion «{title}»", lock=1 + j)
    return out


@pytest.mark.django_db
def test_every_slot_has_a_photo_of_its_own():
    """У каждого слота — СВОЙ файл, а не кадр соседа и не SVG-заглушка.

    Резолвер добирает фото по токенам и по префиксной группе. Ключи `markt-*`
    образуют одну плотную группу, поэтому пропавший файл молча отдал бы кадр
    соседнего слота — и в покрытии `demo_photo_report` это выглядело бы как
    «закрыто» (класс дефекта из catering-волны).
    """
    kit = KITS["aktionsmarkt"]
    broken = []
    for kw, lock, where in _kit_image_keys(kit):
        found = demo_images.photo_static_name(kw, lock=lock)
        if not found or found.rsplit(".", 1)[0] != demo_images._kw_slug(kw):
            broken.append((where, kw, found or "— SVG —"))
    assert not broken, "Слот показывает чужое/пустое фото: " + repr(broken)


@pytest.mark.django_db
def test_grocery_demo_sells_only_food():
    """Фидбэк владельца: продуктовый магазин не торгует бытовой химией.

    Позиции убраны не «спрятаны в другую категорию», а заменены продуктами
    (Nudeln/Basmatireis/Sonnenblumenöl) ПОЗИЦИЯ В ПОЗИЦИЮ — поэтому индексы
    `promotions_spec.product` остались целы, что проверяет соседний замок.
    """
    kit = KITS["aktionsmarkt"]
    hits = []

    def walk(entry, path=""):
        here = f"{path}/{entry[0]}" if path else entry[0]
        if any(bad in entry[0].lower() for bad in NON_FOOD):
            hits.append(f"Kategorie {here}")
        for item in entry[2]:
            name = item["name"] if isinstance(item["name"], str) else item["name"]["de"]
            if any(bad in name.lower() for bad in NON_FOOD):
                hits.append(f"Produkt {here}/{name}")
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child, here)

    for entry in kit.categories:
        walk(entry)
    for spec in kit.promotions_spec or []:
        if any(bad in spec.get("title", "").lower() for bad in NON_FOOD):
            hits.append(f"Aktion «{spec['title']}»")
    assert not hits, "В продуктовом демо остался непищевой ассортимент: " + repr(hits)


# Голден-таблица «акция → её товар». Индекс в `promotions_spec.product` считает
# ПОЗИЦИЮ товара в обходе категорий — самая хрупкая связка кита: любая вставка,
# удаление или перестановка позиции молча уводит все последующие акции на чужой
# товар (цена в карточке при этом остаётся правдоподобной, поэтому глазами не
# ловится). AMP-2 заменил бытовую химию продуктами позиция-в-позицию именно
# ради этого инварианта.
PROMO_TARGETS = [
    ("Kaffee-Woche: −25 % ab Montag", "Gemahlener Kaffee 500 g"),
    ("Käse-Tage −20 %", "Gouda jung 400 g"),
    ("Sonnenblumenöl 1 L für 1,99 €", "Sonnenblumenöl 1 L"),
    ("Äpfel −20 %", "Äpfel 1 kg"),
    ("Croissant −30 % – nur heute!", "Croissant"),
    ("Brot zum Festpreis 0,99 €", "Bauernbrot 750 g"),
    ("Limonade Dauertiefpreis 0,79 €", "Limonade 1,5 L"),
    ("Gemahlener Kaffee −25 % (limitiert)", "Gemahlener Kaffee 500 g"),
    ("Backwaren-Überraschungstüte 5 € statt 15 €", "Backwaren-Tüte"),
    ("Obst & Gemüse-Überraschungstüte 4 € statt 12 €", "Obst & Gemüse-Tüte"),
    ("Brötchen am Abend −50 %", "Brötchen 6er"),
    ("Mineralwasser −15 % (jede Woche)", "Mineralwasser 1,5 L"),
    ("Sonnenblumenöl −40 % (Räumung)", "Sonnenblumenöl 1 L"),
    ("Basmatireis −35 % – Countdown", "Basmatireis 1 kg"),
    ("Bio-Gemüsekiste −20 % – nur 5 Stück", "Bio-Gemüsekiste"),
    ("Mystery-Deal der Woche", "Bergkäse am Stück"),
    ("Tomaten 500 g −25 %", "Tomaten 500 g"),
    ("Bananen — dauerhaft ab 1,29 €", "Bananen 1 kg"),
    ("Orangensaft −20 % — nur 40 Flaschen", "Orangensaft 1 L"),
    ("Gouda jung −20 %", "Gouda jung 400 g"),
    ("Butter 250 g −30 % — MHD-Ware", "Butter 250 g"),
    ("Bergkäse-Anschnitt −25 % — Reste retten", "Bergkäse am Stück"),
    ("Nudeln −30 % (Räumung)", "Nudeln 500 g"),
]


@pytest.mark.django_db
def test_promotion_targets_still_match_their_products():
    """Каждая акция кита указывает на тот товар, что и раньше."""
    kit = KITS["aktionsmarkt"]
    products = []

    def walk(entry):
        for item in entry[2]:
            products.append(item["name"] if isinstance(item["name"], str) else item["name"]["de"])
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)

    actual = [
        (spec["title"], products[spec["product"]])
        for spec in kit.promotions_spec or []
        if isinstance(spec.get("product"), int)
    ]
    assert actual == PROMO_TARGETS


@pytest.mark.django_db
def test_grocery_photos_are_not_shared_with_other_kits():
    """Изоляция: файлы `markt-*` не должны утечь в чужие киты — иначе следующая
    правка дискаунтера снова поедет по чужим демо."""
    leaked = []
    for key, kit in KITS.items():
        if key == "aktionsmarkt":
            continue
        for kw, lock, where in _kit_image_keys(kit):
            found = demo_images.photo_static_name(kw, lock=lock)
            if found and found.startswith(PREFIX):
                leaked.append((key, where, kw, found))
    assert not leaked, "Чужой кит подхватил фото дискаунтера: " + repr(leaked)
