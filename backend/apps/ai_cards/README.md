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

## AI xizmatlari (bir nechtasi bir vaqtda)

Tartib bo'yicha birinchi ulangan xizmat ishlatiladi; kvota/limit/aloqa xatosida avtomatik keyingisiga o'tiladi
(kartochkada "Zaxira AI ishlatildi" ogohlantirishi). Tartib — `/xodim` → AI kartochkalar → "AI" bloki
(`ai_provider_order`), standart: `AI_PROVIDERS` env. Kalitlar faqat env/secret'da.

| Xizmat | Secret(lar) | Model (env, standart) | Internetdan qidiradimi |
|---|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` = `gemini-3.8-flash` | ha (Google Search, url_context) |
| Perplexity Sonar | `PERPLEXITY_API_KEY` | `PERPLEXITY_MODEL` = `sonar` | ha (manbalar bilan) |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` = `deepseek-chat` | yo'q |
| YandexGPT (Yandex AI Studio) | `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` | `YANDEX_MODEL` = `yandexgpt/latest` | yo'q |
| Groq (bepul tarif) | `GROQ_API_KEY` | `GROQ_MODEL` = `openai/gpt-oss-120b` | bepul tadqiqot orqali |
| Cerebras (bepul tarif) | `CEREBRAS_API_KEY` | `CEREBRAS_MODEL` = `gpt-oss-120b` | bepul tadqiqot orqali |
| OpenRouter (bepul modellar) | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` (majburiy, masalan `...:free`) | bepul tadqiqot orqali |
| Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | `CLOUDFLARE_MODEL` | bepul tadqiqot orqali |
| Boshqa OpenAI-mos (Ollama, vLLM) | `AI_API_KEY` (ixtiyoriy), `AI_BASE_URL` | `AI_MODEL` | yo'q |

**Vazifalar bo'yicha taqsimlash** (`client.ROUTES`, admin `ai_provider_order` bo'lsa — u):
- barcha vazifalarda (`card`, `url`, `images`, kategoriya) **avval Groq** (`client.PRIMARY`). Kunlik chegara yo'q:
  bepul tarifda token tugasa 429 → xabardagi kutish vaqtigacha navbatdan chiqadi, zaxiralar ishlaydi
  (Cerebras, OpenRouter, Cloudflare — yuklama bo'yicha; keyin Gemini, Perplexity);
- internet qidiruvini AI emas, tizim bepul qiladi (DuckDuckGo/Bing + Jina, natija 7 kun keshda); Groq yozadi;
- rasm: tizim topgan havolalardan Groq aynan shu tovarnikini tanlaydi (`select_relevant_images`). "Internetdan
  rasm qidir" so'rovi faqat o'zi qidira oladigan AI'ga yuboriladi (qidira olmaydigani havola o'ylab topmasin);
- har so'rov tokenlari `AiCall.tokens_in/out` da; narx `client.PRICES` (Groq gpt-oss-120b: $0.15/$0.60 1 mln
  token); `ai_daily_budget_usd` — kunlik xarajat chegarasi (yetganda Groq to'xtaydi, bepullar ishlaydi).

**Haqiqiy bepul limitlar** (2026-11, demo serverda xizmatlar javobidan o'lchangan; bitta kartochka ~6 ming token):

| Xizmat | Limit | Kartochka/kun (taxm.) | Standart chegara |
|---|---|---|---|
| Groq `openai/gpt-oss-120b` | 1000 so'rov/kun, 8 000 token/daq, 200 000 token/kun | ~30 | 30 |
| Cerebras `gpt-oss-120b` | 5/daq, 150/soat, 2400/kun; 30 000 token/daq, 1 mln token/kun | ~150 | 150 |
| Gemini | AI Studio'da (ai.dev/rate-limit) | — | 200 |
| OpenRouter bepul modellar | ~50 so'rov/kun | ~45 | 45 |

**Kunlik chegaralar** (`ai_provider_caps`, masalan `groq=900,openrouter=45`): bepul limitdan oshmaslik uchun;
chegaraga yetgan xizmat o'sha kuni tashlab o'tiladi. `POST /admin/ai-cards/check` — har xizmatga kichik so'rov:
ishlaydimi, javob vaqti va javob sarlavhalaridagi haqiqiy limitlar (`x-ratelimit-*`).

**O'rganish:** xodim tahrirlab tasdiqlagan oxirgi kartochkalar keyingi so'rovlarga uslub namunasi sifatida qo'shiladi
(nom, tavsif uslubi, uzunligi) — tizim do'kon uslubini o'rganadi; faktlar namunadan olinmaydi.

**Bepul rejim (`AI_FREE_RESEARCH`, standart yoqiq).** O'zi qidira olmaydigan AI uchun internetni tizim bepul
qidiradi: `ddgs` (DuckDuckGo/Bing/Brave metaqidiruv, kalitsiz) → topilgan sahifalarning schema.org/og ma'lumoti va
rasmlari + Jina Reader (`r.jina.ai`, sahifa matni; `JINA_API_KEY` ixtiyoriy). AI faqat shu matndan kartochka yozadi —
bitta kichik so'rov, bepul tariflar ichida. "AI bilan rasm topish" avval AI'siz (qidiruv + sahifa rasmlari)
ishlaydi, topilmasa AI'ga murojaat qiladi. Hech narsa topilmasa — "bilimingdan foydalan" prompti.
Gemini sozlamalari: `GEMINI_THINKING_LEVEL` (`low`), `GEMINI_FALLBACK_MODEL` (`gemini-flash-latest`, 503 da),
`GEMINI_TIMEOUT` (120).

**Kunlik limit** (`ai_cards_daily_limit`): har bir AI so'rovi `AiCall` jadvaliga yoziladi; limitga yetsa — `429`,
qatorlar navbatda qoladi. Xizmat darajasidagi xatolar qatorni buzmaydi. `python manage.py ai_check` — ulangan
xizmatlar va modellar ro'yxati (kvota sarflamaydi), `--generate` — kichik so'rov bilan tekshirish.

## Valyuta

Fayldagi narx valyutasi sarlavhadan aniqlanadi ($, USD, сум...); aniqlanmasa — panelda qo'lda tanlanadi
(`POST /admin/ai-cards/batches/{id}/currency`). Dollar bo'lsa, tannarx `usd_uzs_rate` sozlamasi
(AI blokida "Dollar kursi") bo'yicha so'mga o'giriladi; kurs kiritilmagan bo'lsa — tannarx yozilmaydi.

## Eslatma

Rasmlar istalgan saytdan olinadi (buyurtmachi qarori). Har bir rasmning manbasi `ProductImage.external_url` da
saqlanadi — kerak bo'lsa almashtirish uchun. Gemini'ga faqat tovar nomlari va fayldagi qator yuboriladi
(shaxsiy ma'lumot yo'q).
