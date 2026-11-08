# ai_cards — Gemini yordamida tovar kartochkalari

Ta'minotchi Excel faylidagi har bir tovar uchun Gemini (Google qidiruvi bilan) internetdan ma'lumot topadi va
kartochka tuzadi: nom (uz, ru), tavsif, brend, model, kategoriya, xususiyatlar, kafolat, og'irlik va rasmlar.
Kartochka **qoralama** bo'lib turadi; kontent menejer tekshirib, narx qo'yib nashr qiladi.

## Jarayon

1. `/xodim` → "AI kartochkalar" → `.xlsx` fayl yuklash (`POST /admin/ai-cards/batches`, multipart `file`).
   Ustunlar sarlavha bo'yicha aniqlanadi (uz/ru/en): nomi, artikul, xarid narxi, soni, brend.
   Nom ustuni topilmasa — eng uzun matnli ustun olinadi. Bir faylda 500 tagacha qator.
2. "Gemini bilan to'ldirish" — UI `POST /admin/ai-cards/batches/{id}/process` ni qayta-qayta chaqiradi
   (har chaqiruvda bitta qator; alohida worker kerak emas).
3. Har bir kartochkani ko'rib chiqish: tahrirlash (`PATCH /admin/ai-cards/drafts/{id}`), rasmni olib tashlash,
   kategoriyani almashtirish.
4. "Nashr qilish" (`POST .../approve` — `{price, old_price?, sku?, publish}`):
   tovar, variant (xarid narxi → `cost_price`), xususiyatlar va rasmlar (serverga yuklab olinadi) yaratiladi.
   Qoldiq — back-office kirim hujjati orqali.
5. "Rad etish" yoki "Qayta yaratish".

## Gemini javobiga ishonilmaydi

- Kategoriya va xususiyat kodlari faqat bizdagi ro'yxatdan qabul qilinadi; enum qiymati kod yoki nom bo'yicha
  moslanadi, son tekshiriladi. Mos kelmagani `warnings` ga yoziladi.
- Rasm havolalari tekshiriladi: faqat ochiladigan `image/*` (8 MB gacha) qoldiriladi.
- Katalogda shu model allaqachon bo'lsa — ogohlantirish.
- Ishonch (`confidence`) 0.6 dan past bo'lsa — ogohlantirish.

## Sozlash

AI provayder kodni o'zgartirmasdan almashtiriladi (env/secret):

| O'zgaruvchi | Ma'nosi |
|---|---|
| `AI_PROVIDER` | `gemini` (standart, Google qidiruvi bilan) yoki `openai` (OpenAI-mos API) |
| `GEMINI_API_KEY` | Google AI Studio kaliti |
| `GEMINI_MODEL` | standart `gemini-3.8-flash` (`gemini-2.5-flash` yangi foydalanuvchilarga yopilgan) |
| `GEMINI_THINKING_LEVEL` | `low` (tezroq); model qo'llamasa avtomatik o'chiriladi; bo'sh — model standarti |
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | `AI_PROVIDER=openai` uchun: OpenRouter (`https://openrouter.ai/api/v1`), Groq, o'z serverdagi Ollama (`http://host:11434/v1`, kalitsiz) va h.k. |

`openai` provayderida internet qidiruvi yo'q — model o'z bilimidan foydalanadi (sifati pastroq, o'zbekcha matn
zaifroq bo'lishi mumkin); rasm havolalari tekshiriladi.

**Kunlik limit** (`ai_cards_daily_limit`, `/xodim` → AI kartochkalar → "AI" bloki): har bir AI so'rovi
`AiCall` jadvaliga yoziladi; bugungi (Toshkent vaqti) so'rovlar limitga yetsa — `429 ai_daily_limit`,
qatorlar navbatda qoladi va ertaga davom ettiriladi. Bepul tarif limitidan oshmaslik uchun.

**Xatolar**: kalit/model/limit/aloqa xatolari (`ai_unauthorized`, `ai_model_unavailable`, `ai_rate_limited`,
`ai_unavailable`, ...) qatorni buzmaydi — to'ldirish to'xtaydi, qatorlar navbatda qoladi. Faqat javobning
o'zi yaroqsiz bo'lsa qator "Xato" bo'ladi; ularni "Xatolarni qayta navbatga" bilan qaytarish mumkin.

Ishga tushishda `python manage.py ai_check` kalit va modelni tekshirib, natijani log'ga yozadi.

## Eslatma

Rasmlar istalgan saytdan olinadi (buyurtmachi qarori). Har bir rasmning manbasi `ProductImage.external_url` da
saqlanadi — kerak bo'lsa almashtirish uchun. Gemini'ga faqat tovar nomlari va fayldagi qator yuboriladi
(shaxsiy ma'lumot yo'q).
