import re

import pytest
from django.urls import reverse

from apps.notifications.models import NotificationLog

pytestmark = pytest.mark.django_db

PHONE = "+998901234567"


@pytest.fixture
def sent(monkeypatch):
    """Yuborilgan SMS matnlarini ushlab qoladi."""
    messages = []
    from apps.notifications.sms.console import ConsoleSmsBackend

    def fake_send(self, phone, text):
        messages.append((phone, text))
        from apps.notifications.sms.base import SmsResult

        return SmsResult(provider="console", message_id="t")

    monkeypatch.setattr(ConsoleSmsBackend, "send", fake_send)
    return messages


def request_code(client, phone="90 123 45 67", ip="10.0.0.1"):
    return client.post(reverse("otp-request"), {"phone": phone}, format="json", REMOTE_ADDR=ip)


def code_of(sent) -> str:
    return re.search(r"\d{6}", sent[-1][1]).group(0)


def test_request_sends_sms_and_hides_code(api_client, sent):
    resp = request_code(api_client)
    assert resp.status_code == 200
    assert resp.json() == {"expires_in": 120, "resend_in": 60}  # DEMO_MODE=False -> debug_code yo'q
    assert sent[0][0] == PHONE
    log = NotificationLog.objects.get()
    assert log.status == "sent"
    assert "******" in log.body and code_of(sent) not in log.body  # kod bazaga yozilmaydi


def test_demo_mode_returns_code(api_client, sent, settings):
    settings.DEMO_MODE = True
    resp = request_code(api_client)
    assert resp.json()["debug_code"] == code_of(sent)


def test_invalid_phone(api_client):
    resp = api_client.post(reverse("otp-request"), {"phone": "12345"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"
    assert "phone" in resp.json()["error"]["fields"]


def test_resend_cooldown(api_client, sent):
    assert request_code(api_client).status_code == 200
    resp = request_code(api_client)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert len(sent) == 1


def test_hourly_limit_per_phone(api_client, sent, settings):
    settings.OTP = {**settings.OTP, "RESEND_COOLDOWN_SECONDS": 0, "MAX_PER_PHONE_PER_HOUR": 2}
    from django.core.cache import cache

    for _ in range(2):
        cache.delete(f"otp:cooldown:{PHONE}")
        assert request_code(api_client).status_code == 200
    cache.delete(f"otp:cooldown:{PHONE}")
    assert request_code(api_client).status_code == 429


def test_hourly_limit_per_ip(api_client, sent, settings):
    settings.OTP = {**settings.OTP, "MAX_PER_IP_PER_HOUR": 2}
    assert request_code(api_client, "901111111").status_code == 200
    assert request_code(api_client, "901111112").status_code == 200
    assert request_code(api_client, "901111113").status_code == 429


def test_verify_creates_user_and_returns_tokens(api_client, sent, django_user_model):
    request_code(api_client)
    resp = api_client.post(reverse("otp-verify"), {"phone": PHONE, "code": code_of(sent)}, format="json")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["is_new_user"] is True and body["access"] and body["refresh"]
    user = django_user_model.objects.get(phone=PHONE)
    assert not user.has_usable_password()

    # kod bir martalik
    resp = api_client.post(reverse("otp-verify"), {"phone": PHONE, "code": code_of(sent)}, format="json")
    assert resp.json()["error"]["code"] == "otp_expired"


def test_verify_existing_user(api_client, sent, user):
    request_code(api_client, user.phone)
    resp = api_client.post(reverse("otp-verify"), {"phone": user.phone, "code": code_of(sent)}, format="json")
    assert resp.json()["is_new_user"] is False


def test_wrong_code_attempts_exhausted(api_client, sent):
    request_code(api_client)
    good = code_of(sent)
    wrong = "000000" if good != "000000" else "111111"
    for left in (4, 3, 2, 1, 0):
        resp = api_client.post(reverse("otp-verify"), {"phone": PHONE, "code": wrong}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == {
            "code": "otp_invalid",
            "message": "Kod noto'g'ri.",
            "attempts_left": left,
        }
    # 5 xato urinishdan keyin to'g'ri kod ham ishlamaydi
    resp = api_client.post(reverse("otp-verify"), {"phone": PHONE, "code": good}, format="json")
    assert resp.json()["error"]["code"] == "otp_expired"


def test_verify_without_request(api_client):
    resp = api_client.post(reverse("otp-verify"), {"phone": PHONE, "code": "123456"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "otp_expired"


def test_blocked_user_cannot_login(api_client, sent, user):
    user.is_active = False
    user.save()
    request_code(api_client, user.phone)
    resp = api_client.post(reverse("otp-verify"), {"phone": user.phone, "code": code_of(sent)}, format="json")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "account_disabled"


def test_sms_failure_is_logged(api_client, monkeypatch):
    from apps.notifications.sms.base import SmsError
    from apps.notifications.sms.console import ConsoleSmsBackend

    def boom(self, phone, text):
        raise SmsError("down", retryable=False)

    monkeypatch.setattr(ConsoleSmsBackend, "send", boom)
    assert request_code(api_client).status_code == 200
    log = NotificationLog.objects.get()
    assert log.status == "failed" and log.error == "down"
