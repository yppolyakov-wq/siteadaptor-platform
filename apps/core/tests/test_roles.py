"""M6-шов: роли пользователя в тенанте (Membership + roles.role_of)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.core.models import Membership
from apps.core.roles import has_cabinet_access, is_owner, role_of

pytestmark = pytest.mark.django_db


def _user(name="u1"):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@t.de", password="pw12345678"
    )


def test_role_of_without_membership_is_blank_fail_closed():
    user = _user()
    # Fail-closed: без явной строки Membership доступа/роли нет (защита от
    # эскалации, если User появится в схеме не через create_business).
    assert role_of(user) == "" and not is_owner(user)
    assert not has_cabinet_access(user)


def test_owner_membership_grants_access():
    user = _user("owner1")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert role_of(user) == "owner" and is_owner(user)
    assert has_cabinet_access(user)


def test_role_of_reads_membership():
    user = _user("staff1")
    Membership.objects.create(user=user, role=Membership.ROLE_STAFF)
    assert role_of(user) == "staff" and not is_owner(user)
    # Staff — член тенанта: доступ к кабинету есть, роль владельца — нет.
    assert has_cabinet_access(user)


def test_role_of_anonymous_is_blank():
    assert role_of(AnonymousUser()) == "" and not has_cabinet_access(AnonymousUser())
