"""AIS A-3a: «создать X» понимает фразы владельца так, как он их пишет.

Фидбэк владельца 2026-11-06 (два скриншота):
* «добавь новый товар Колбаса копченая 200 гр 50 евро как услугу» → помощник выбрал
  товар (хотя явно «как услугу») и не увидел цену («евро»);
* «создай услугу прыжки с парашутом, 200 евро, 60 минут» → из имени выпал предлог «с»,
  цена и длительность после запятых потерялись.

Замки: явная сущность («как/als/as/як <X>», «<X> olarak») сильнее найденной первой; цена
в евро на 5 языках и с символом до числа; часы → минуты; хвост «, 200 евро, 60 минут»
приклеивается к предыдущему шагу, а не создаёт товар; служебные слова режутся только по
краям имени; явная сущность недоступна → следующая с пометкой; палитра = create_intent.
"""

import pytest

from apps.core import setup_assistant as sa
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL = [sa.ENTITY_CATEGORY, sa.ENTITY_PRODUCT, sa.ENTITY_SERVICE, sa.ENTITY_PROMO]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(business_type="friseur")


def _one(text, tenant, allowed=ALL):
    plan = sa.plan_from_rules(text, tenant, allowed)
    assert len(plan.steps) == 1, [s.title for s in plan.steps]
    return plan.steps[0]


def _val(step, name):
    return next(f.value for f in step.fields if f.name == name)


def test_owner_phrase_sausage_as_service(tenant):
    step = _one("добавь новый товар Колбаса копченая 200 гр 50 евро как услугу", tenant)
    assert step.entity == sa.ENTITY_SERVICE
    assert _val(step, "name") == "Колбаса копченая 200 гр"
    assert _val(step, "price_eur") == "50,00"


def test_owner_phrase_parachute_tail_after_commas(tenant):
    step = _one("создай услугу прыжки с парашутом, 200 евро, 60 минут", tenant)
    assert step.entity == sa.ENTITY_SERVICE
    assert _val(step, "name") == "прыжки с парашутом"
    assert _val(step, "price_eur") == "200,00"
    assert _val(step, "duration") == "60"
    assert "price_eur=200%2C00" in step.form_url and "duration=60" in step.form_url


@pytest.mark.parametrize(
    "text",
    [
        "Räucherwurst 200 g 5 € als Leistung",
        "smoked sausage 5 € as service",
        "füme sucuk 5 € hizmet olarak",
        "ковбаса 5 євро як послугу",
    ],
)
def test_explicit_entity_wins_in_all_languages(tenant, text):
    assert _one(text, tenant).entity == sa.ENTITY_SERVICE


@pytest.mark.parametrize(
    "text, price",
    [
        ("Käsekuchen 3,20 €", "3,20"),
        ("Käsekuchen 50 евро", "50,00"),
        ("Käsekuchen €50", "50,00"),
        ("Käsekuchen € 4,50", "4,50"),
        ("Käsekuchen 50 EUR", "50,00"),
        ("Käsekuchen EUR 7", "7,00"),
        ("Käsekuchen 12 євро", "12,00"),
        ("Käsekuchen 9 avro", "9,00"),
    ],
)
def test_price_in_euro_words_and_symbol_first(tenant, text, price):
    assert sa._price_in(text) == price


def test_weight_is_not_a_price(tenant):
    assert sa._price_in("Колбаса копченая 200 гр") == ""
    assert sa._price_in("Mehl 500 g") == ""


@pytest.mark.parametrize(
    "text, minutes",
    [
        ("60 минут", "60"),
        ("45 min", "45"),
        ("1 час", "60"),
        ("1,5 часа", "90"),
        ("2 Stunden", "120"),
        ("1 h", "60"),
        ("2 saat", "120"),
    ],
)
def test_duration_minutes_and_hours(text, minutes):
    assert sa._duration_in(text) == minutes


def test_inner_prepositions_stay_in_the_name(tenant):
    step = _one("neue Leistung Haarschnitt mit Föhnen 30 €", tenant)
    assert _val(step, "name") == "Haarschnitt mit Föhnen"


def test_named_tail_after_comma_is_still_its_own_product(tenant):
    plan = sa.plan_from_rules("neue Kategorie Kuchen, Käsekuchen 3,20 €", tenant, ALL)
    assert [s.entity for s in plan.steps] == [sa.ENTITY_CATEGORY, sa.ENTITY_PRODUCT]


def test_unavailable_explicit_entity_falls_back_with_a_note(tenant):
    allowed = [sa.ENTITY_CATEGORY, sa.ENTITY_PRODUCT]
    plan = sa.plan_from_rules("добавь товар Колбаса 50 евро как услугу", tenant, allowed)
    assert [s.entity for s in plan.steps] == [sa.ENTITY_PRODUCT]
    assert plan.note  # «Leistungen sind bei Ihnen nicht eingeschaltet — als Produkt …»


def test_create_intent_matches_palette(tenant, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(sa, "allowed_entities", lambda t, u: ALL)
    user = SimpleNamespace(pk=1)
    phrase = "создай услугу прыжки с парашутом, 200 евро"
    assert sa.create_intent(tenant, user, phrase)
    assert sa.palette_section(tenant, user, phrase) is not None
    assert not sa.create_intent(tenant, user, "Wo stelle ich die Lieferzeiten ein?")
    assert sa.palette_section(tenant, user, "Wo stelle ich die Lieferzeiten ein?") is None


# ── ИИ понимает формулировку, сервер проверяет только факт ──
# (фидбэк владельца: «замки не обязательно такие — как научить ИИ распознавать?»)
# На скриншоте «прыжки с парашутом» стоял «Vorschlag der KI»: модель нашла цену и
# длительность, а проверка выбросила их, не узнав «евро». Теперь проверка не зависит от
# списка валютных слов: число цены обязано стоять в тексте ЦЕЛЫМ и не быть весом/объёмом.

PARACHUTE = "создай услугу прыжки с парашутом, 200 евро, 1,5 часа"


def _ai(steps, text, tenant):
    return sa._from_ai({"steps": steps}, text, tenant, ALL)


def test_ai_price_and_duration_in_any_wording(tenant):
    step = {
        "entity": "service",
        "name": "прыжки с парашутом",
        "price_text": "200 евро",
        "duration_text": "1,5 часа",
    }
    got = _ai([step], PARACHUTE, tenant).steps[0]
    assert _val(got, "name") == "прыжки с парашутом"
    assert _val(got, "price_eur") == "200,00"
    assert _val(got, "duration") == "90"


@pytest.mark.parametrize("written", ["200 евр.", "200 €uro", "200", "200 Euronen", "€200"])
def test_ai_price_does_not_need_an_exact_euro_word(tenant, written):
    text = f"neue Leistung Fallschirmsprung {written}"
    step = {"entity": "service", "name": "Fallschirmsprung", "price_text": written}
    assert _val(_ai([step], text, tenant).steps[0], "price_eur") == "200,00"


@pytest.mark.parametrize("currency", ["USD", "$", "CHF", "Franken", "zł", "грн", "руб", "TL", "£"])
def test_ai_foreign_currency_is_not_taken_as_euro(tenant, currency):
    text = f"neue Leistung Fallschirmsprung 200 {currency}"
    step = {"entity": "service", "name": "Fallschirmsprung", "price_text": f"200 {currency}"}
    assert _val(_ai([step], text, tenant).steps[0], "price_eur") == ""


@pytest.mark.parametrize(
    "price_text",
    ["200 гр", "200", "300 евро", "50,5 евро", "0 евро"],
)
def test_ai_price_must_be_a_whole_written_non_weight_number(tenant, price_text):
    text = "добавь товар Колбаса копченая 200 гр 50 евро как услугу"
    step = {"entity": "service", "name": "Колбаса копченая", "price_text": price_text}
    assert _val(_ai([step], text, tenant).steps[0], "price_eur") == ""


def test_ai_duration_only_as_written(tenant):
    step = {"entity": "service", "name": "прыжки с парашутом", "duration_text": "120 min"}
    assert _val(_ai([step], PARACHUTE, tenant).steps[0], "duration") == ""


def test_system_prompt_carries_examples_in_five_languages():
    for marker in ("Herrenhaarschnitt", "прыжки с парашутом", "200 гр", "olarak", "Käsekuchen"):
        assert marker in sa.SYSTEM
