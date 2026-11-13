"""Chat mantiqi: xabar qabul qilish, AI javobi (katalog va do'kon ma'lumoti asosida), xodimga uzatish."""

import logging
import re

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from apps.core.exceptions import ApiError

from .models import Conversation, Message

logger = logging.getLogger(__name__)

MAX_TEXT = 1000
RATE_LIMIT = 15  # mijoz xabarlari
RATE_WINDOW = 300  # soniya
HISTORY = 8  # AI'ga beriladigan oxirgi xabarlar

S, R = Conversation.Status, Message.Sender

PROMPT = """Sen "{store}" onlayn do'konining (maishiy texnika va elektronika, O'zbekiston) yordamchisisan.
Mijozga qisqa (1-4 jumla), xushmuomala va aniq javob ber — mijoz qaysi tilda yozgan bo'lsa, o'sha tilda
(o'zbekcha — lotin yozuvida, yoki ruscha).

Qoidalar:
- Faqat quyidagi ma'lumotlardan foydalan. Narx, mavjudlik, muddat yoki xususiyatni o'ylab topma.
- Tovar so'ralsa — "TOVARLAR" ro'yxatidan mosini tavsiya qil (ko'pi bilan 3 ta) va ularning slug'ini
  "products" ga yoz. Ro'yxatda mosi bo'lmasa — shuni ayt va boshqa so'rov bilan izlashni taklif qil.
- Buyurtma holati, to'lov muammosi, qaytarish/shikoyat, kafolat bo'yicha murojaat yoki sen javob bera
  olmaydigan savol bo'lsa — qisqa javob ber va "handoff": true qo'y (suhbat operatorga uzatiladi).
- Mijoz operator/odam bilan gaplashmoqchi bo'lsa — "handoff": true.
- Do'konga aloqasi yo'q savollarga javob berma, do'kon bo'yicha yordam taklif qil.

DO'KON:
{store_info}

TOVARLAR (mijoz so'roviga mos kelganlari):
{products}

SUHBAT:
{history}

Faqat JSON qaytar: {{"reply": "<javob matni>", "products": ["<slug>", ...], "handoff": false}}"""


def get_or_create(token: str | None, user=None, lang: str = "uz") -> Conversation:
    conv = Conversation.objects.filter(token=token).first() if token else None
    if conv is None:
        conv = Conversation(lang=lang[:8] or "uz")
        if user is not None and user.is_authenticated:
            conv.user, conv.name, conv.phone = user, (user.first_name or "")[:80], (user.phone or "")[:20]
        conv.save()
    elif conv.user_id is None and user is not None and user.is_authenticated:
        conv.user, conv.phone = user, conv.phone or (user.phone or "")[:20]
        conv.save(update_fields=["user", "phone", "updated_at"])
    return conv


def _add(conv: Conversation, sender: str, text: str, *, staff=None, products=None) -> Message:
    msg = Message.objects.create(
        conversation=conv, sender=sender, text=text[:4000], staff=staff, products=products or []
    )
    conv.last_message_at = msg.created_at
    conv.save(update_fields=["last_message_at", "status", "unread_for_staff", "assigned_to", "updated_at"])
    return msg


def _check_rate(conv: Conversation) -> None:
    key = f"chat_rate:{conv.pk}"
    n = cache.get(key, 0)
    if n >= RATE_LIMIT:
        raise ApiError("chat_rate_limited", "Juda ko'p xabar. Bir ozdan keyin yozing.", status_code=429)
    cache.set(key, n + 1, RATE_WINDOW)


def _find_products(text: str, limit: int = 6) -> list[dict]:
    """Mijoz xabariga mos faol tovarlar (katalog qidiruvi) — AI faqat shulardan tavsiya qiladi."""
    from apps.catalog.search import get_search_backend
    from apps.catalog.selectors import public_products, stock_status

    words = [w for w in re.findall(r"[\w'-]{3,}", text.lower()) if not w.isdigit()]
    seen, out = set(), []
    # Butun matn bo'yicha, keyin alohida so'zlar bo'yicha (uzunlari oldin): "samsung muzlatkich bormi?".
    for query in [text, *sorted(set(words), key=len, reverse=True)[:5]]:
        try:
            qs, _ = get_search_backend().filter_queryset(public_products(), query[:100])
        except Exception:  # noqa: BLE001 — qidiruv xatosi chatni to'xtatmasin
            logger.exception("Chat: katalog qidiruvi xatosi")
            break
        for p in qs[:limit]:
            if p.pk in seen:
                continue
            seen.add(p.pk)
            first = p.images.first()
            out.append(
                {
                    "slug": p.slug,
                    "name": p.name.get("uz") or p.name.get("ru") or p.slug,
                    "name_ru": p.name.get("ru") or "",
                    "price": str(int(p.min_price)) if p.min_price is not None else "",
                    "stock": stock_status(p.available or 0),
                    "image": (
                        first.file.url if first and first.file else (first.external_url if first else "")
                    ),
                }
            )
            if len(out) >= limit:
                return out
    return out


def _store_info() -> tuple[str, str]:
    from apps.marketing.services import site_content

    site = site_content()

    def loc(v) -> str:
        return (v.get("uz") or v.get("ru") or "") if isinstance(v, dict) else str(v or "")

    lines = [
        f"Telefon: {site.get('phone') or '—'}",
        f"Ish vaqti: {loc(site.get('working_hours'))}",
        f"Manzil: {loc(site.get('address')) or loc(site.get('city'))}",
        f"To'lov usullari: {site.get('pay_methods') or 'Payme, Click, Uzum Bank, naqd'}",
        "Yetkazish: eshikkacha; narxi va muddati manzilga qarab rasmiylashtirishda hisoblanadi.",
        "Tekshirish: kuryer oldida qadoqni ochib, tovarni yoqib ko'rish mumkin. Rasmiy kafolat bor.",
    ]
    for key, page in (site.get("pages") or {}).items():
        body = loc((page or {}).get("body"))
        if body:
            lines.append(f"{loc((page or {}).get('title')) or key}: {' '.join(body.split())[:500]}")
    return site.get("store_name") or "TexnoDo'kon", "\n".join(lines)


def ai_reply(conv: Conversation, text: str) -> Message:
    """AI javobi. Xizmat ishlamasa yoki javob bera olmasa — suhbat xodimga uzatiladi."""
    from apps.ai_cards import client
    from apps.ai_cards.models import AiCall

    found = _find_products(text)
    store, info = _store_info()
    label = {R.CUSTOMER: "Mijoz", R.AI: "Yordamchi", R.STAFF: "Operator", R.SYSTEM: "Tizim"}
    recent = list(conv.messages.order_by("-id")[:HISTORY])[::-1]
    history = "\n".join(f"{label[m.sender]}: {m.text[:600]}" for m in recent)
    stock = {"in_stock": "bor", "low": "oz qoldi", "out_of_stock": "tugagan"}
    goods = (
        "\n".join(
            f"- slug={p['slug']} | {p['name']} | {p['price']} so'm | {stock.get(p['stock'], p['stock'])}"
            for p in found
        )
        or "(mos tovar topilmadi)"
    )
    prompt = PROMPT.format(store=store, store_info=info, products=goods, history=history)
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64])
    try:
        res = client.generate(prompt, task="chat", search=False, expect_json=True, max_tokens=500)
        call.provider, call.model = res.provider, res.model[:64]
        call.tokens_in, call.tokens_out = getattr(res, "tokens_in", 0), getattr(res, "tokens_out", 0)
        data = client.extract_json(res.text)
        call.save()
    except client.AiError as exc:
        logger.warning("Chat AI xatosi: %s", exc.message)
        if exc.code != "not_configured":
            call.ok = False
            call.save()
        return handoff(conv, note="Avtomatik yordamchi hozir javob bera olmayapti.")
    reply = str(data.get("reply") or "").strip()
    if not reply:
        return handoff(conv, note="")
    by_slug = {p["slug"]: p for p in found}
    picked = [by_slug[s] for s in data.get("products") or [] if isinstance(s, str) and s in by_slug][:3]
    cards = [{k: p[k] for k in ("slug", "name", "price", "image")} for p in picked]
    msg = _add(conv, R.AI, reply, products=cards)
    if data.get("handoff") is True:
        handoff(conv, note="")
    return msg


def handoff(conv: Conversation, *, note: str = "") -> Message:
    """Suhbatni xodimga uzatish (bir marta): mijozga bu haqda tizim xabari yoziladi."""
    if conv.status in (S.WAITING, S.STAFF):
        return conv.messages.order_by("-id").first()
    conv.status = S.WAITING
    conv.unread_for_staff = F("unread_for_staff") + 1
    text = (note + " " if note else "") + (
        "Suhbat operatorga uzatildi — u tez orada shu yerda javob beradi. "
        "Kutib qolmaslik uchun telefon raqamingizni yozib qoldirishingiz mumkin."
    )
    msg = _add(conv, R.SYSTEM, text)
    conv.refresh_from_db()
    return msg


def customer_message(conv: Conversation, text: str) -> list[Message]:
    text = (text or "").strip()
    if not text:
        raise ApiError("empty_message", "Xabar bo'sh.")
    if len(text) > MAX_TEXT:
        raise ApiError("message_too_long", f"Xabar {MAX_TEXT} belgidan oshmasin.")
    _check_rate(conv)
    if conv.status == S.CLOSED:
        conv.status = S.AI  # yopilgan suhbatga yozilsa — yangidan AI bilan boshlanadi
    if conv.status in (S.WAITING, S.STAFF):
        conv.unread_for_staff = F("unread_for_staff") + 1
    if not conv.phone and (
        m := re.search(r"(?:\+?998)?[\s-]?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}", text)
    ):
        conv.phone = re.sub(r"[^\d+]", "", m.group())[:20]
        conv.save(update_fields=["phone"])
    out = [_add(conv, R.CUSTOMER, text)]
    conv.refresh_from_db()
    if conv.status == S.AI:
        out.append(ai_reply(conv, text))
    return out


def staff_reply(conv: Conversation, text: str, *, user) -> Message:
    text = (text or "").strip()
    if not text:
        raise ApiError("empty_message", "Xabar bo'sh.")
    conv.status, conv.unread_for_staff, conv.assigned_to = S.STAFF, 0, user
    return _add(conv, R.STAFF, text, staff=user)


def set_status(conv: Conversation, status: str) -> Conversation:
    """Xodim: suhbatni yopish yoki AI'ga qaytarish."""
    if status not in (S.CLOSED, S.AI):
        raise ApiError("bad_status", "Faqat yopish yoki AI'ga qaytarish mumkin.")
    conv.status, conv.unread_for_staff = status, 0
    conv.save(update_fields=["status", "unread_for_staff", "updated_at"])
    return conv


def mark_read(conv: Conversation) -> None:
    if conv.unread_for_staff:
        Conversation.objects.filter(pk=conv.pk).update(unread_for_staff=0, updated_at=timezone.now())
