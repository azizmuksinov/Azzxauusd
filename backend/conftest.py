import itertools

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(phone="+998901112233", first_name="Ali")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


_phones = itertools.count(1)


@pytest.fixture
def staff_client(django_user_model):
    """staff_client("content_manager") -> shu roldagi xodim bilan APIClient."""
    from django.contrib.auth.models import Group

    def make(*roles):
        u = django_user_model.objects.create_user(phone=f"+99891{next(_phones):07d}")
        for r in roles:
            u.groups.add(Group.objects.get(name=r))
        client = APIClient()
        client.force_authenticate(u)
        client.user = u
        return client

    return make
