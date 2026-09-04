"""Волна O (2026-09-03): демо аутлета «Zweitgut» — фото, ассортимент, акции.

Кит собран из СВОЕГО пространства ключей `ol-*`: одежные ключи без префикса
(`jeans`, `sale`, `tshirt`, `denim`) увели бы кадры кита `clothing` через
токенный фолбэк резолвера, а техники в библиотеке не было вовсе.

Из 249 слотов честный CC0-кадр нашёлся для 171; остальные ЗАКОНОМЕРНО живут на
тематическом SVG-плейсхолдере. Поэтому здесь замок не «у всех есть фото», а
более сильное утверждение: слот показывает СВОЙ кадр либо осмысленный
плейсхолдер — но никогда кадр соседа и никогда безликое «✨».
"""

import pytest

from apps.tenants import demo_images
from apps.tenants.demo_kits import KITS

PREFIX = "ol-"
KEY = "outlet"

#: Плейсхолдеры, которые НЕ несут темы: их появление означает, что реестр
#: `_EMOJI` не знает предмета (класс дефекта catering-волны).
GENERIC_EMOJI = ("✨", "🍽️")


def _kit_image_keys(kit) -> list[tuple[str, int, str]]:
    """[(keyword, lock, где)] по всем фото-слотам кита — включая кадры карусели
    (`img` списком) и фото акций, которых `demo_photo_report` не видит."""
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
    for member in kit.team:
        add(member[2], f"Team {member[0]}")

    def walk(entry, path=""):
        here = f"{path}/{entry[0]}" if path else entry[0]
        for item in entry[2]:
            add_frames(item.get("img"), f"Produkt {here}/{item['name']}")
        extra = entry[3] if len(entry) > 3 else []
        if isinstance(extra, str):
            add(extra, f"Kachel {here}")
        else:
            for child in extra:
                walk(child, here)
            for tail in entry[4:]:
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

    for name, spec in kit.collections or []:
        for j, kw in enumerate(spec.get("photos") or []):
            add(kw, f"Kollektion «{name}»", lock=1 + j)
    for combo in kit.combos or []:
        for j, kw in enumerate(combo.get("photos") or []):
            add(kw, f"Set «{combo['name']}»", lock=1 + j)
    return out


def _flat_products(kit) -> list[str]:
    """Товары в порядке обхода сидером (DFS pre-order) — по нему считается
    индекс `promotions_spec.product`."""
    names: list[str] = []

    def walk(entry):
        for item in entry[2]:
            names.append(item["name"] if isinstance(item["name"], str) else item["name"]["de"])
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)
    return names


@pytest.mark.django_db
def test_no_slot_borrows_another_slots_photo():
    """Слот показывает СВОЙ файл — либо ничего (плейсхолдер), но не чужой кадр.

    Резолвер добирает фото по токенам и по префиксной ГРУППЕ, а `ol-*` — одна
    плотная группа: слот без своего файла молча получил бы кадр соседа, и в
    `demo_photo_report` это выглядело бы как «закрыто».
    """
    kit = KITS[KEY]
    borrowed = []
    for kw, lock, where in _kit_image_keys(kit):
        found = demo_images.photo_static_name(kw, lock=lock)
        if found and found.rsplit(".", 1)[0] != demo_images._kw_slug(kw):
            borrowed.append((where, kw, found))
    assert not borrowed, "Слот показывает ЧУЖОЕ фото: " + repr(borrowed)


@pytest.mark.django_db
def test_slots_without_photo_get_a_topical_placeholder():
    """Там, где честного кадра нет, плейсхолдер обязан быть тематическим.

    До волны реестр `_EMOJI` знал только гастро и услуги, поэтому ноутбук и
    кроссовки получали безликое «✨» — по сути пустое место на витрине.
    """
    kit = KITS[KEY]
    faceless = []
    for kw, lock, where in _kit_image_keys(kit):
        if demo_images.photo_static_name(kw, lock=lock):
            continue
        emoji = next((em for token, em in demo_images._EMOJI if token in kw.lower()), "✨")
        if emoji in GENERIC_EMOJI:
            faceless.append((where, kw, emoji))
    assert not faceless, "Плейсхолдер без темы (дополнить _EMOJI): " + repr(faceless)


@pytest.mark.django_db
def test_outlet_photos_are_not_shared_with_other_kits():
    """Изоляция пространства `ol-*`: чужой кит не должен подхватывать кадры
    аутлета — иначе следующая правка ассортимента поедет по чужим демо."""
    leaked = []
    for key, kit in KITS.items():
        if key == KEY:
            continue
        for kw, lock, where in _kit_image_keys(kit):
            found = demo_images.photo_static_name(kw, lock=lock)
            if found and found.startswith(PREFIX):
                leaked.append((key, where, kw, found))
    assert not leaked, "Чужой кит подхватил фото аутлета: " + repr(leaked)


#: Голден-таблица «акция → её товар». Индекс `promotions_spec.product` — ПОЗИЦИЯ
#: товара в обходе категорий: вставка или перестановка позиции молча уводит все
#: последующие акции на чужой товар, а цена в карточке остаётся правдоподобной,
#: поэтому глазами это не ловится.
PROMO_TARGETS = [
    ("Tagesdeal: Saugroboter Vireo Round −35 %", "Saugroboter Vireo Round"),
    ("Tagesdeal: Kaffeevollautomat statt 399 € nur 329 €", "Kaffeevollautomat Ostrand Barista"),
    ("Tagesdeal: Over-Ear Kamira Studio 2 zum Festpreis 69 €", "Over-Ear Kamira Studio 2"),
    ("Neu ohne OVP: Notebook Nordvolt N15 −20 %", "Notebook Nordvolt N15 Office"),
    ("Neu ohne OVP: Wollmantel Traverso Nord ab 89 €", "Wollmantel Traverso Nord"),
    ("Neu ohne OVP: Armbanduhr Traverso Stahl −25 %", "Armbanduhr Traverso Stahl"),
    ("Lagerräumung: Fernseher Ferrit 55 Zoll −30 %", "Fernseher Ferrit 55 Zoll 4K"),
    ("Lagerräumung: Beamer Ferrit Cine Mini 139 € statt 179 €", "Beamer Ferrit Cine Mini"),
    ("Lagerräumung: Toaster Halden Duo −40 %", "Toaster Halden Duo"),
    ("Mode-Sale: Kleid Silvana Sommer −40 %", "Kleid Silvana Sommer"),
    ("Mode-Sale: Sneaker Traverso Court 39,90 € statt 49,90 €", "Sneaker Traverso Court"),
    ("Mode-Sale: Chelsea-Boots Brentwood −25 %", "Chelsea-Boots Brentwood Leder"),
    ("Mode-Sale: Pullover Traverso Merino ab 39,90 €", "Pullover Traverso Merino"),
    ("Technik-Deal: Monitor Kamira View 27 QHD −22 %", "Monitor Kamira View 27 QHD"),
    ("Technik-Deal: Externe SSD Ferrit 1 TB zum Festpreis 54,90 €", "Externe SSD Ferrit 1 TB"),
    ("Technik-Deal: VR-Brille Ferrit View −20 %", "VR-Brille Ferrit View"),
    ("Mystery-Deal der Woche", "Smartwatch Lumeo Fit 2"),
    ("Nur noch 4 Stück: Siebträger Bragg Espresso Pro −25 %", "Siebträger Bragg Espresso Pro"),
    ("Shopper Traverso Leder −20 %", "Shopper Traverso Leder"),
    ("Laufschuh Ahlberg Road Neutral 54,90 € statt 69,90 €", "Laufschuh Ahlberg Road Neutral"),
    ("Ab Montag: Winter-Räumung bis −50 %", "Steppjacke Brentwood Winter"),
]


@pytest.mark.django_db
def test_promotion_targets_still_match_their_products():
    kit = KITS[KEY]
    products = _flat_products(kit)
    actual = [
        (spec["title"], products[spec["product"]])
        for spec in kit.promotions_spec or []
        if isinstance(spec.get("product"), int)
    ]
    assert actual == PROMO_TARGETS


@pytest.mark.django_db
def test_every_department_has_at_least_twenty_items():
    """Требование владельца: в каждом направлении не меньше 20 позиций —
    иначе аутлет не выглядит магазином, а фасеты нечего фильтровать."""
    kit = KITS[KEY]
    thin = []
    for entry in kit.categories:
        count = len(entry[2]) + sum(len(sub[2]) for sub in (entry[3] if len(entry) > 3 else []))
        if count < 20:
            thin.append((entry[0], count))
    assert not thin, "Направление беднее 20 позиций: " + repr(thin)


@pytest.mark.django_db
def test_collections_describe_what_they_promise():
    """Подборка-фасет обязана быть честной: «Neu ohne OVP» — только такая ware,
    «Ausstellungsstücke» — только витринные, «Unter 25 €» — только дешевле 25 €.
    Иначе чип фильтра врёт покупателю (и UWG это не одобряет)."""
    kit = KITS[KEY]
    items = []

    def walk(entry):
        items.extend(entry[2])
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)

    checks = {
        "Neu ohne OVP": lambda it: it.get("condition") == "neu_ohne_ovp",
        "Ausstellungsstücke": lambda it: it.get("condition") == "ausstellung",
        "Unter 25 €": lambda it: float(it["price"]) < 25,
    }
    wrong = []
    for name, spec in kit.collections or []:
        rule = checks.get(name)
        if not rule:
            continue
        for i in spec.get("products", []):
            if not rule(items[i]):
                wrong.append((name, items[i]["name"]))
    assert not wrong, "Состав подборки не соответствует названию: " + repr(wrong)


@pytest.mark.django_db
def test_every_non_new_item_names_its_condition():
    """§ 476 Abs. 2 BGB: известный недостаток должен быть назван. В демо это
    значит — у каждой позиции с состоянием есть конкретный `condition_note`."""
    kit = KITS[KEY]
    silent = []

    def walk(entry):
        for item in entry[2]:
            if item.get("condition") and not item.get("condition_note"):
                silent.append(item["name"])
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)
    assert not silent, "Состояние без описания: " + repr(silent)


@pytest.mark.django_db
def test_condition_note_does_not_repeat_the_label():
    """Стенд: витрина печатает «Zustand: <метка> — <примечание>», и примечание,
    начинавшееся с той же метки, давало «Ausstellungsstück — Ausstellungsstück —
    feine Kratzer…». Примечание обязано ДОБАВЛЯТЬ факт, а не повторять ярлык."""
    from apps.catalog.models import Product

    kit = KITS[KEY]
    labels = {code: str(label) for code, label in Product.CONDITION_CHOICES if code}
    echoed = []

    def walk(entry):
        for item in entry[2]:
            code, note = item.get("condition"), item.get("condition_note") or ""
            if code and labels.get(code) and note.startswith(labels[code]):
                echoed.append((item["name"], note))
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)
    assert not echoed, "Примечание повторяет метку состояния: " + repr(echoed)


@pytest.mark.django_db
def test_uvp_is_always_above_the_selling_price():
    """UWG: зачёркнутая цена должна быть выше нашей — иначе «скидка» фиктивна."""
    kit = KITS[KEY]
    bad = []

    def walk(entry):
        for item in entry[2]:
            uvp = item.get("uvp")
            if uvp and float(uvp) <= float(item["price"]):
                bad.append((item["name"], item["price"], uvp))
        extra = entry[3] if len(entry) > 3 else []
        if not isinstance(extra, str):
            for child in extra:
                walk(child)

    for entry in kit.categories:
        walk(entry)
    assert not bad, "UVP не выше цены продажи: " + repr(bad)


def test_outlet_offers_a_payment_method_that_works_for_delivery():
    """O-9c: у аутлета включена доставка, а способов оплаты был ровно один —
    «на месте». Оплатить на месте доставленный заказ нельзя, поэтому у заказа с
    доставкой не было пути к оплате вовсе, и пикер способов (E7) не появлялся.
    Vorkasse — классика немецкой розницы: не требует Stripe и закрывает дыру."""
    from apps.core.payment_methods import available
    from apps.tenants.demo_kits import KITS

    kit = KITS["outlet"]
    assert kit.delivery.get("enabled"), "у аутлета доставка включена — предпосылка теста"
    assert kit.payments.get("vorkasse"), "кит обязан задать Vorkasse"
    assert kit.payments.get("bank_iban"), "без IBAN гейт E7 не пустит Vorkasse в пикер"

    class _T:  # тенант, каким его сделает apply_kit
        vorkasse_enabled = True
        bank_iban = kit.payments["bank_iban"]
        stripe_payment_methods: list = []
        stripe_account_id = ""
        stripe_charges_enabled = False
        invoice_b2b_enabled = False

    codes = set(available(_T()))
    assert "vorkasse" in codes
    assert len(codes) > 1, "пикер способов показывается только при двух и более"
