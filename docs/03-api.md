# 03. API ro'yxati (v1)

Bazaviy yo'l: `/api/v1`. Format: JSON. Til: `Accept-Language: uz | uz-Cyrl | ru`.
Auth: `Authorization: Bearer <JWT>`. Pul qiymatlari UZS da, satr ko'rinishida (`"12990000.00"`).
Pul yaratadigan so'rovlarda (`POST /orders`, `/pay`, `/refund`) `Idempotency-Key` sarlavhasi majburiy.
Ro'yxatlar cursor bilan sahifalanadi: `?cursor=&page_size=`.
Hujjat: `GET /api/schema/` (OpenAPI 3.1), `GET /api/docs/` (Swagger UI).

Belgilar: 🌐 — ochiq, 👤 — xaridor, 🚚 — kuryer, 🛠 — xodim (rol ko'rsatilgan), 🔏 — imzo/IP bilan himoyalangan webhook.

## 1. Auth va profil

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| POST | `/auth/otp/request` | 🌐 | `{phone}` → SMS-kod yuboradi. Rate-limit: 1 marta/60 s, 5 marta/soat |
| POST | `/auth/otp/verify` | 🌐 | `{phone, code}` → `{access, refresh, is_new_user}` |
| POST | `/auth/token/refresh` | 🌐 | refresh rotation |
| POST | `/auth/logout` | 👤 | refresh tokenni blacklist'ga qo'shadi |
| GET / PATCH | `/me` | 👤 | ism, til, email |
| DELETE | `/me` | 👤 | akkauntni o'chirish (shaxsiy ma'lumotlar anonimlashtiriladi) |
| GET / POST | `/me/addresses` | 👤 | manzillar (qavat, lift, koordinata bilan) |
| PATCH / DELETE | `/me/addresses/{id}` | 👤 | |
| POST | `/me/devices` | 👤 | push token |
| GET | `/geo/regions` | 🌐 | viloyatlar |
| GET | `/geo/regions/{id}/districts` | 🌐 | tumanlar |
| GET | `/geo/reverse?lat=&lng=` | 🌐 | koordinatadan manzil (geokoder proksi, ⚠️ S-04) |

## 2. Katalog va qidiruv

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| GET | `/categories` | 🌐 | daraxt |
| GET | `/categories/{slug}` | 🌐 | kategoriya + breadcrumb |
| GET | `/categories/{slug}/filters` | 🌐 | fasetlar: brend, narx oralig'i, atributlar (sonlari bilan) |
| GET | `/brands` · `/brands/{slug}` | 🌐 | |
| GET | `/products` | 🌐 | `?category=&brand=&price_min=&price_max=&f[screen_size]=50..65&f[smart_tv]=true&in_stock=&sort=popular\|price_asc\|price_desc\|new\|rating` |
| GET | `/products/{slug}` | 🌐 | variantlar, atributlar guruhlab, rasmlar, qoldiq holati, kafolat, yetkazish taxmini |
| GET | `/products/{slug}/similar` | 🌐 | |
| GET | `/products/{slug}/delivery-estimate?district_id=` | 🌐 | kartochkadagi "ertaga yetkazamiz" |
| GET | `/search?q=` | 🌐 | Meilisearch, typo-tolerance, lotin↔kirill |
| GET | `/search/suggest?q=` | 🌐 | avtoto'ldirish (tovar, kategoriya, brend) |
| GET | `/compare?products=1,2,3` | 🌐 | solishtirish jadvali (faqat `is_comparable` atributlar) |
| GET / POST / DELETE | `/me/compare` · `/me/compare/{product_id}` | 👤 | serverdagi solishtirish ro'yxati |
| GET / POST / DELETE | `/me/favorites` · `/me/favorites/{product_id}` | 👤 | |
| GET | `/banners?placement=home_top` | 🌐 | |

## 3. Sharhlar va savol-javob

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| GET | `/products/{id}/reviews` | 🌐 | `?rating=&with_photos=&sort=` + reyting taqsimoti |
| POST | `/products/{id}/reviews` | 👤 | faqat yetkazilgan buyurtma bo'lsa (`order_item_id`) |
| POST | `/reviews/{id}/vote` | 👤 | foydali / foydasiz |
| GET | `/me/reviews/pending` | 👤 | sotib olingan, lekin sharh yozilmagan tovarlar |
| GET / POST | `/products/{id}/questions` | 🌐 / 👤 | |
| POST | `/questions/{id}/answers` | 👤 | xaridorlar ham javob bera oladi; rasmiy javob — xodimdan |
| POST | `/uploads/presign` | 👤 | S3 ga yuklash uchun presigned URL (sharh rasmi, qaytarish rasmi) |

## 4. Savat va checkout

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| GET | `/cart` | 🌐 / 👤 | mehmon uchun `X-Cart-Token` |
| POST | `/cart/items` | 🌐 / 👤 | `{variant_id, qty}` |
| PATCH / DELETE | `/cart/items/{id}` | 🌐 / 👤 | |
| POST | `/cart/merge` | 👤 | login'dan keyin mehmon savatini birlashtiradi |
| POST / DELETE | `/cart/promo` | 🌐 / 👤 | promo-kod |
| POST | `/checkout/delivery-options` | 👤 | `{address_id, floor?, elevator?, lifting?}` → smart routing: tanlangan variant + muqobillar, `quote_id`, muddat, ko'tarish narxi |
| POST | `/checkout/summary` | 👤 | `{address_id, quote_id, payment_method?}` → summalar, ruxsat etilgan to'lov usullari, talab qilinadigan avans, nasiya takliflari |
| POST | `/orders` | 👤 | `{address_id, quote_id, payment_method, lifting, comment}` + `Idempotency-Key` → buyurtma + (onlayn bo'lsa) `payment_url` |

## 5. Buyurtmalar (xaridor)

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| GET | `/orders` | 👤 | `?status=active\|completed` |
| GET | `/orders/{number}` | 👤 | tarkib, statuslar tarixi, jo'natma, cheklar, akt |
| POST | `/orders/{number}/cancel` | 👤 | faqat `packed` gacha ruxsat |
| GET | `/orders/{number}/tracking` | 👤 | normallashtirilgan voqealar + provayder trek raqami |
| POST | `/orders/{number}/pay` | 👤 | `{provider: payme\|click\|uzum, purpose: full\|prepayment}` → `payment_url` |
| GET | `/orders/{number}/receipts` | 👤 | fiskal cheklar (QR havola) |
| GET | `/orders/{number}/handover-act` | 👤 | topshirish akti PDF |

## 6. To'lov va nasiya

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| POST | `/webhooks/payme` | 🔏 | JSON-RPC (Basic auth + IP) |
| POST | `/webhooks/click/prepare` | 🔏 | `sign_string` tekshiruvi |
| POST | `/webhooks/click/complete` | 🔏 | |
| POST | `/webhooks/uzum/{check\|create\|confirm\|reverse\|status}` | 🔏 | |
| GET | `/installments/offers?amount=` | 🌐 | hamkor(lar) muddat/oylik to'lov kalkulyatori |
| POST | `/installments/applications` | 👤 | `{order_number, partner, term_months, ...}` → ariza (⚠️ S-17) |
| GET | `/installments/applications/{id}` | 👤 | holati |
| POST | `/webhooks/installments/{partner}` | 🔏 | hamkordan qaror |

## 7. Kafolat va qaytarish

| Metod | Yo'l | Kim | Tavsif |
|---|---|---|---|
| GET | `/me/warranties` | 👤 | elektron kafolat kartalari (seriya, muddat) |
| POST | `/returns` | 👤 | `{order_item_id, serial, type, reason_code, description, photo_keys[]}` |
| GET | `/returns` · `/returns/{number}` | 👤 | holati, olib ketish sanasi |
| POST | `/returns/{number}/cancel` | 👤 | |

## 8. Kuryer ilovasi (`/courier/...`, rol `courier`)

| Metod | Yo'l | Tavsif |
|---|---|---|
| GET | `/courier/routes/today` | kunlik marshrut, to'xtash joylari tartibi |
| GET | `/courier/stops/{id}` | buyurtma, manzil, qavat/lift, kutilgan seriyalar, COD summasi |
| POST | `/courier/stops/{id}/pickup` | **oldi** — omborda seriyalarni skanerlash |
| POST | `/courier/stops/{id}/start` | **yo'lda** — mijozga "kuryer yo'lda" SMS |
| POST | `/courier/stops/{id}/handover/send-code` | mijozga tasdiqlash SMS-kodi |
| POST | `/courier/stops/{id}/deliver` | **topshirdi**: `{sms_code, serials[], checks{opened, powered_on}, photo_keys[], cash, terminal}` |
| POST | `/courier/stops/{id}/refuse` | **rad etildi**: `{reason_code, comment, photo_keys[]}` |
| POST | `/courier/stops/{id}/reschedule` | mijoz uyda emas / boshqa kun |
| POST | `/courier/stops/{id}/return-to-warehouse` | **qaytardi** — omborga topshirdi (omborchi tasdiqlaydi) |
| POST | `/courier/uploads/presign` | foto uchun presigned URL |
| GET | `/courier/cash` | qo'ldagi naqd balansi, yozuvlar |
| POST | `/courier/cash/handover` | kassaga topshirish so'rovi |
| POST | `/courier/location` | joylashuv (ixtiyoriy, har 60 s) |

## 9. Boshqaruv paneli API (`/api/v1/admin/...`)

> Jadvaldagi `/admin-api/` prefiksi kodda `/api/v1/admin/` deb amalga oshirilgan.

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| CRUD | `/admin-api/categories`, `/brands`, `/attributes`, `/products`, `/products/{id}/variants`, `/products/{id}/images` | content_manager | |
| PATCH | `/admin-api/variants/{id}/price` | content_manager | narx tarixiga yoziladi |
| GET | `/admin-api/imports/template.xlsx` | content_manager | Excel shablon |
| POST | `/admin-api/imports` | content_manager | Excel yuklash → fon vazifa, `dry_run` rejimi |
| GET | `/admin-api/imports/{id}` | content_manager | natija, qator bo'yicha xatolar |
| GET | `/admin-api/stock` | warehouse | `?warehouse=&low_stock=` |
| POST | `/admin-api/stock/receipts` | warehouse | kirim (seriya/IMEI ro'yxati bilan) |
| POST | `/admin-api/stock/adjustments` | warehouse | inventarizatsiya tuzatishi |
| GET | `/admin-api/serials?q=` · `/admin-api/serials/{id}` | warehouse, support | seriya/IMEI bo'yicha to'liq tarix |
| GET | `/admin-api/orders` | support, warehouse, logistics | filtrlar: status, sana, to'lov, provayder, tuman |
| GET | `/admin-api/orders/{id}` | 〃 | |
| POST | `/admin-api/orders/{id}/transition` | 〃 | `{to, note}` — ruxsat etilgan o'tishlar |
| POST | `/admin-api/orders/{id}/confirm-cod` | support | COD tasdiqlash |
| GET | `/admin-api/picking-list` | warehouse | yig'ish varag'i (bugungi) |
| POST | `/admin-api/orders/{id}/assign-serials` | warehouse | `{items: [{order_item_id, serial_unit_ids[]}]}` |
| POST | `/admin-api/orders/{id}/ship` | logistics | jo'natma yaratish (provayderni qo'lda almashtirish mumkin) |
| GET | `/admin-api/orders/{id}/label` · `/packing-slip` | warehouse | PDF |
| GET | `/admin-api/shipments` | logistics | |
| POST | `/admin-api/shipments/{id}/cancel` · `/refresh-tracking` | logistics | |
| CRUD | `/admin-api/courier-zones`, `/delivery-tariffs`, `/delivery-providers` | logistics | |
| POST | `/admin-api/routes/plan` | logistics | `{date, courier_ids[]}` → avtomatik marshrut |
| CRUD | `/admin-api/routes`, `/routes/{id}/stops` | logistics | qo'lda tahrir |
| GET | `/admin-api/couriers/{id}/cash` | finance | |
| POST | `/admin-api/couriers/{id}/cash/confirm` | finance | kassir pulni qabul qildi |
| GET | `/admin-api/payments` · `/admin-api/payments/{id}` | finance | |
| POST | `/admin-api/payments/{id}/refund` | finance | |
| GET | `/admin-api/fiscal-receipts` · POST `/{id}/retry` | finance | |
| GET | `/admin-api/returns` · POST `/returns/{id}/transition` | support | |
| CRUD | `/admin-api/promotions`, `/promo-codes`, `/banners` | content_manager | |
| GET / POST | `/admin-api/reviews`, `/questions` (moderatsiya, rasmiy javob) | support | |
| GET | `/admin-api/reports/sales` | finance | `?from=&to=&group_by=day\|category\|brand` |
| GET | `/admin-api/reports/margin` | finance | tushum − tannarx − chegirma |
| GET | `/admin-api/reports/delivery-costs` | finance, logistics | provayder bo'yicha: quote vs haqiqiy, mijozdan olingan vs to'langan |
| GET | `/admin-api/reports/cod` | finance | kuryer/provayder bo'yicha naqd |
| GET | `/admin-api/reports/{name}.xlsx` | finance | eksport |
| CRUD | `/admin-api/staff` | admin | xodimlar va rollar |
| GET | `/admin-api/customers?q=` | support | audit_log ga yoziladi |
| GET / PATCH | `/admin-api/settings` | admin | `cod_max_amount`, `prepayment_percent`, ... |
| GET | `/admin-api/sync/jobs` · POST `/admin-api/sync/run` | admin | 1C sinxron jurnali, qo'lda ishga tushirish |
| GET | `/admin-api/audit-log` | admin | |

## 10. Integratsiya endpointlari

| Metod | Yo'l | Tavsif |
|---|---|---|
| POST | `/webhooks/bts` · `/webhooks/fargo` | provayder status webhooki (agar qo'llab-quvvatlasa; aks holda polling) |
| GET | `/integrations/1c/orders?since=` | agar 1C o'zi tortib olsa (⚠️ S-16) |
| POST | `/integrations/1c/stock` | agar 1C o'zi yuborsa (⚠️ S-16) |
| GET | `/health` · `/health/ready` | monitoring |

## Xato formati

```json
{ "error": { "code": "cod_not_allowed", "message": "…", "fields": { "payment_method": ["…"] } } }
```

Asosiy kodlar: `otp_invalid`, `otp_expired`, `rate_limited`, `out_of_stock`, `quote_expired`,
`cod_not_allowed`, `prepayment_required`, `invalid_transition`, `serial_mismatch`, `sms_code_invalid`.
