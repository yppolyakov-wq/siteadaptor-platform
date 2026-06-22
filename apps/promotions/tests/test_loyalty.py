"""Тесты лояльности (штампы + награда)."""

import pytest

from apps.loyalty.models import LoyaltyProgram, Voucher
from apps.promotions.models import Customer
from apps.promotions.services import LoyaltyError, add_stamp, get_or_create_card


def _program(stamps=10):
    return LoyaltyProgram.objects.create(
        label="Kaffee", stamps_required=stamps, reward_label="Gratis Kaffee"
    )


def _customer():
    return Customer.objects.create(name="Ann", email="ann@test.de")


@pytest.mark.django_db
def test_get_or_create_card_is_idempotent():
    program, customer = _program(), _customer()
    c1 = get_or_create_card(program, customer)
    c2 = get_or_create_card(program, customer)
    assert c1.pk == c2.pk


@pytest.mark.django_db
def test_add_stamp_increments():
    card = get_or_create_card(_program(), _customer())
    card, reward = add_stamp(card, cooldown_seconds=0)
    assert card.stamps == 1
    assert reward is None


@pytest.mark.django_db
def test_reward_at_threshold_resets_and_issues_voucher():
    card = get_or_create_card(_program(stamps=2), _customer())
    add_stamp(card, cooldown_seconds=0)
    card, reward = add_stamp(card, cooldown_seconds=0)
    assert card.stamps == 0
    assert card.rewards_earned == 1
    assert reward is not None
    assert Voucher.objects.filter(code=reward.code, label="Gratis Kaffee").exists()


@pytest.mark.django_db
def test_cooldown_blocks_double_stamp():
    card = get_or_create_card(_program(), _customer())
    add_stamp(card)  # дефолтный кулдаун
    with pytest.raises(LoyaltyError) as exc:
        add_stamp(card)
    assert exc.value.reason == "cooldown"
