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

| O'zgaruvchi | Ma'nosi |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio kaliti (faqat secret/env'da) |
| `GEMINI_MODEL` | Model nomi, standart `gemini-2.5-flash` |
| `GEMINI_TIMEOUT` | So'rov kutish vaqti, soniya (120) |

So'rov: `POST {base}/models/{model}:generateContent`, `x-goog-api-key` sarlavhasi, `tools: [{google_search: {}}]`.
Kalit bo'lmasa API `503 gemini_not_configured` qaytaradi.

## Eslatma

Rasmlar istalgan saytdan olinadi (buyurtmachi qarori). Har bir rasmning manbasi `ProductImage.external_url` da
saqlanadi — kerak bo'lsa almashtirish uchun. Gemini'ga faqat tovar nomlari va fayldagi qator yuboriladi
(shaxsiy ma'lumot yo'q).
