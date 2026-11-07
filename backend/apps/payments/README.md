# payments

Onlayn to'lovlar: Payme, Click, Uzum Bank. Hammasi bitta umumiy mantiqqa (`services.py`) tayanadi.

## Kim qancha to'laydi

| Buyurtma | Onlayn to'lanadi | Eshikda to'lanadi |
|---|---|---|
| Onlayn (Payme/Click/Uzum) | hammasi | — |
| Eshikda to'lov (naqd/terminal) | yetkazish narxi (`delivery_fee_prepaid`) | tovar narxi |
| Eshikda to'lov, summa `cod_max_amount` dan katta | `cod_prepayment_percent` (kamida yetkazish narxi) | qolgani |

Talab qilingan summa to'langach buyurtma holati o'zgaradi:
- onlayn buyurtma — `paid`;
- eshikda to'lov — `cod_confirmed` (avans to'lagani xaridorning tasdig'i hisoblanadi).

Shundan keyin tovar bandi muddatsiz bo'ladi. Muddat ichida to'lanmasa, buyurtma o'zi bekor bo'ladi.
Provayderda jarayondagi to'lov bo'lsa, u tugashi kutiladi.

## Xaridor uchun

`POST /api/v1/orders/{number}/pay {provider, return_url}` → `payment_url`. Xaridor shu sahifaga yo'naltiriladi.
Demo rejimda (`DEMO_MODE`): `POST /api/v1/orders/{number}/demo-pay` — to'lov tizimisiz sinov.

## Webhooklar (provayder → biz)

| Provayder | Yo'l | Tekshiruv |
|---|---|---|
| Payme | `POST /api/v1/webhooks/payme` (JSON-RPC) | `Authorization: Basic Paycom:<KEY>` |
| Click | `POST /api/v1/webhooks/click/prepare`, `/complete` (form) | `sign_string` MD5 |
| Uzum Bank | `POST /api/v1/webhooks/uzum/{check,create,confirm,reverse,status}` | `Authorization: Basic LOGIN:PASSWORD` + `serviceId` |

Hamma webhooklar uchun umumiy qoidalar:
- har bir so'rov va bizning javobimiz `WebhookLog` ga yoziladi: tana, IP, imzo natijasi;
- imzo yoki parol xato bo'lsa, hech narsa o'zgarmaydi;
- summa serverda qayta tekshiriladi: buyurtma kutayotgan summa bilan bir tiyingacha mos bo'lishi kerak;
- takroriy so'rovlar idempotent: bir tranzaksiya ikki marta hisoblanmaydi (`UNIQUE(provider, provider_txn_id)`);
- bekor qilingan buyurtmaga pul yechilmaydi — provayderga xato qaytadi;
- ixtiyoriy IP filtri: `PAYME_ALLOWED_IPS`, `CLICK_ALLOWED_IPS`, `UZUM_ALLOWED_IPS`.

### Payme
- Barcha metodlar qo'llab-quvvatlanadi: `CheckPerformTransaction`, `CreateTransaction`, `PerformTransaction`,
  `CancelTransaction`, `CheckTransaction`, `GetStatement`.
- Bitta buyurtmaga bir vaqtda faqat bitta faol tranzaksiya bo'lishi mumkin.
- 12 soat ichida yakunlanmagan tranzaksiya bekor qilinadi (`reason=4`).
- `CheckPerformTransaction` javobida fiskal chek uchun `detail` beriladi: MXIK, qadoq kodi, QQS va
  "Yetkazib berish" qatori.
- Yechilgan pulni qaytarishga faqat tovar kuryerga berilguncha ruxsat bor. Qaytarilsa, buyurtma bekor bo'ladi.

### Click
- `prepare`: buyurtma va summa tekshiriladi, `Payment(pending)` yaratiladi.
- `complete`: pul yechiladi. Click `error < 0` yuborsa, tranzaksiya bekor qilinadi.

### Uzum Bank
- Maydon nomlari va xato kodlari ochiq ma'lumotlar asosida yozilgan.
- Rasmiy hujjat va merchant akkaunti olingach solishtirish kerak (S-14). Kodlar `providers/uzum.py` boshida jamlangan.
- To'lov havolasi shabloni: `UZUM_PAYMENT_URL_TEMPLATE`. Berilmasa, xaridor Uzum Bank ilovasi orqali to'laydi.

## Sozlamalar (env)

`PAYMENT_PROVIDERS`, `PAYME_MERCHANT_ID`, `PAYME_KEY`, `PAYME_CHECKOUT_URL` (test: `https://checkout.test.paycom.uz`),
`CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_SECRET_KEY`, `UZUM_SERVICE_ID`, `UZUM_LOGIN`, `UZUM_PASSWORD`.
Fiskal chek kodlari: `PAYME_DEFAULT_PACKAGE_CODE`, `PAYME_DELIVERY_MXIK`, `PAYME_DELIVERY_PACKAGE_CODE` (S-15).

## Hali qilinmagan

- Click va Uzum to'lovlari uchun fiskal chek (OFD). OFD provayderi tanlangach qilinadi (S-15).
- Biz tomondan pulni qaytarish (refund): hozircha buyurtma `refund_pending` holatiga o'tadi va qaytarish
  provayderning kabinetida qo'lda bajariladi.
