import httpx
import pytest
from django.core.cache import cache

from apps.notifications.sms.base import SmsError
from apps.notifications.sms.eskiz import TOKEN_CACHE_KEY, EskizSmsBackend


@pytest.fixture(autouse=True)
def eskiz_settings(settings):
    settings.ESKIZ = {
        **settings.ESKIZ,
        "EMAIL": "a@b.uz",
        "PASSWORD": "secret",
        "BASE_URL": "https://eskiz.test/api",
    }
    cache.clear()


def make_backend(handler):
    return EskizSmsBackend(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_login_then_send():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"token": "T1"}})
        assert request.headers["Authorization"] == "Bearer T1"
        body = request.content.decode()
        assert "mobile_phone=998901234567" in body
        return httpx.Response(200, json={"id": "abc-1", "status": "waiting"})

    result = make_backend(handler).send("+998901234567", "Kod: 123456")
    assert result.message_id == "abc-1"
    assert calls == ["/api/auth/login", "/api/message/sms/send"]
    assert cache.get(TOKEN_CACHE_KEY) == "T1"


def test_expired_token_relogin():
    cache.set(TOKEN_CACHE_KEY, "OLD")
    tokens = iter(["NEW"])

    def handler(request: httpx.Request):
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"token": next(tokens)}})
        if request.headers["Authorization"] == "Bearer OLD":
            return httpx.Response(401, json={"message": "Expired"})
        return httpx.Response(200, json={"id": "abc-2"})

    assert make_backend(handler).send("+998901234567", "x").message_id == "abc-2"


def test_client_error_not_retryable():
    def handler(request: httpx.Request):
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"token": "T"}})
        return httpx.Response(400, json={"message": "Template not approved"})

    with pytest.raises(SmsError) as exc:
        make_backend(handler).send("+998901234567", "x")
    assert exc.value.retryable is False


def test_missing_credentials(settings):
    settings.ESKIZ = {**settings.ESKIZ, "EMAIL": "", "PASSWORD": ""}
    with pytest.raises(SmsError):
        make_backend(lambda r: httpx.Response(200)).send("+998901234567", "x")
