import json
from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.catalog.tests import factories as f
from apps.support.models import Conversation

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai(monkeypatch):
    """AI javobini soxtalash: state["reply"] — qaytadigan JSON; prompts — yuborilgan matnlar."""
    from apps.ai_cards import client

    state = {
        "reply": {"reply": "Salom! Qanday yordam beray?", "products": [], "handoff": False},
        "prompts": [],
    }

    def generate(prompt, **kw):
        state["prompts"].append(prompt)
        if state.get("error"):
            raise client.AiError("rate_limited", "limit tugadi")
        return SimpleNamespace(
            text=json.dumps(state["reply"]), provider="groq", model="test", tokens_in=10, tokens_out=5
        )

    monkeypatch.setattr(client, "generate", generate)
    return state


def test_guest_chat_gets_ai_answer_with_products_from_catalog(api_client, ai):
    cat = f.category(slug="muzlatkichlar", name={"uz": "Muzlatkichlar"})
    p = f.product(cat, name={"uz": "Samsung RB38 muzlatkichi"}, price="8990000")
    f.product(cat, name={"uz": "Artel HD 455 muzlatkichi"})
    ai["reply"] = {"reply": "Samsung RB38 bor, narxi 8 990 000 so'm.", "products": [p.slug, "yoq-slug"]}
    r = api_client.post(reverse("chat"), {"text": "Samsung muzlatkich bormi?", "lang": "uz"}, format="json")
    assert r.status_code == 200, r.json()
    d = r.json()
    assert d["status"] == "ai" and [m["sender"] for m in d["messages"]] == ["customer", "ai"]
    assert d["messages"][1]["products"][0]["slug"] == p.slug and len(d["messages"][1]["products"]) == 1
    assert d["messages"][1]["products"][0]["price"] == "8990000"
    # AI'ga katalogdagi mos tovar va do'kon ma'lumoti berilgan; mijoz xabari tarixda
    prompt = ai["prompts"][0]
    assert f"slug={p.slug}" in prompt and "Samsung RB38 muzlatkichi" in prompt and "To'lov usullari" in prompt
    assert "Mijoz: Samsung muzlatkich bormi?" in prompt
    # keyingi so'rov: faqat yangi xabarlar; token bilan suhbat davom etadi
    token, last = d["token"], d["messages"][-1]["id"]
    assert api_client.get(reverse("chat"), {"token": token, "after": last}).json()["messages"] == []
    r = api_client.post(reverse("chat"), {"token": token, "text": "Rahmat"}, format="json")
    assert Conversation.objects.count() == 1 and len(r.json()["messages"]) == 2
    assert api_client.get(reverse("chat"), {"token": "notogri"}).json() == {
        "token": "",
        "status": "ai",
        "messages": [],
    }


def test_handoff_to_staff_and_reply(api_client, staff_client, ai):
    ai["reply"] = {"reply": "Buyurtmangizni operator tekshiradi.", "handoff": True}
    d = api_client.post(
        reverse("chat"), {"text": "Buyurtmam qayerda? +998 90 123 45 67"}, format="json"
    ).json()
    assert d["status"] == "waiting" and [m["sender"] for m in d["messages"]] == ["customer", "ai", "system"]
    token = d["token"]
    # kutish paytida AI javob bermaydi; xabar xodimga "o'qilmagan" bo'lib tushadi
    d = api_client.post(reverse("chat"), {"token": token, "text": "Kutyapman"}, format="json").json()
    assert [m["sender"] for m in d["messages"]] == ["customer"] and len(ai["prompts"]) == 1

    assert api_client.get(reverse("admin-chat-list")).status_code == 401
    assert staff_client("courier").get(reverse("admin-chat-list")).status_code == 403
    s = staff_client("support")
    assert s.get(reverse("admin-chat-summary")).json() == {"waiting": 1, "unread": 0}
    row = s.get(reverse("admin-chat-list"), {"status": "waiting"}).json()["results"][0]
    assert (
        row["unread_for_staff"] == 2 and row["phone"] == "+998901234567" and row["last_text"] == "Kutyapman"
    )
    detail = s.get(reverse("admin-chat-detail", args=[row["id"]])).json()
    assert len(detail["messages"]) == 4 and detail["unread_for_staff"] == 0
    r = s.post(reverse("admin-chat-reply", args=[row["id"]]), {"text": "Buyurtmangiz yo'lda."}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "staff"
    new = api_client.get(reverse("chat"), {"token": token, "after": d["messages"][-1]["id"]}).json()
    assert new["status"] == "staff" and new["messages"][0]["sender"] == "staff"
    # xodim suhbatni AI'ga qaytaradi — keyingi savolga yana AI javob beradi
    assert (
        s.post(
            reverse("admin-chat-set-status", args=[row["id"]]), {"status": "ai"}, format="json"
        ).status_code
        == 200
    )
    ai["reply"] = {"reply": "Yana savol bo'lsa yozing."}
    d = api_client.post(reverse("chat"), {"token": token, "text": "Rahmat"}, format="json").json()
    assert [m["sender"] for m in d["messages"]] == ["customer", "ai"]


def test_customer_can_call_operator_and_ai_failure_hands_off(api_client, ai):
    d = api_client.post(reverse("chat"), {"text": "Salom"}, format="json").json()
    d2 = api_client.post(reverse("chat"), {"token": d["token"], "handoff": True}, format="json").json()
    assert d2["status"] == "waiting" and d2["messages"][-1]["sender"] == "system"
    ai["error"] = True  # AI limiti tugagan: mijoz javobsiz qolmaydi — suhbat xodimga o'tadi
    d3 = api_client.post(reverse("chat"), {"text": "Narxi qancha?"}, format="json").json()
    assert d3["status"] == "waiting" and "operatorga uzatildi" in d3["messages"][-1]["text"]
    assert api_client.post(reverse("chat"), {"text": "  "}, format="json").status_code == 400


def test_chat_rate_limit(api_client, ai, monkeypatch):
    from django.core.cache import cache

    from apps.support import services

    cache.clear()
    monkeypatch.setattr(services, "RATE_LIMIT", 2)
    token = api_client.post(reverse("chat"), {"text": "1"}, format="json").json()["token"]
    assert api_client.post(reverse("chat"), {"token": token, "text": "2"}, format="json").status_code == 200
    r = api_client.post(reverse("chat"), {"token": token, "text": "3"}, format="json")
    assert r.status_code == 429 and r.json()["error"]["code"] == "chat_rate_limited"
