"""M6-шов: роли пользователя в тенанте (Membership + roles.role_of)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.core.models import Membership
from apps.core.roles import is_owner, role_of

pytestmark = pytest.mark.django_db


def _user(name="u1"):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@t.de", password="pw12345678"
    )


def test_role_of_defaults_to_owner_without_membership():
    user = _user()
    # легаси-тенант без строки Membership: единственный пользователь = владелец
    assert role_of(user) == Membership.ROLE_OWNER and is_owner(user)


def test_role_of_reads_membership():
    user = _user("staff1")
    Membership.objects.create(user=user, role=Membership.ROLE_STAFF)
    assert role_of(user) == "staff" and not is_owner(user)


def test_role_of_anonymous_is_blank():
    assert role_of(AnonymousUser()) == ""
