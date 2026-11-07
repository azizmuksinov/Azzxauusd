# notifications

SMS yuborish va jurnal. Push bildirishnomalar keyingi bosqichda qo'shiladi.

## SMS backendlari (`SMS_BACKEND`)

| Qiymat | Tavsif | Narx |
|---|---|---|
| `console` | SMS yuborilmaydi, logga yoziladi. Dev va demo uchun. Production'da **taqiqlangan** | Bepul |
| `eskiz` | [Eskiz.uz](https://eskiz.uz): token keshda saqlanadi, 401 bo'lsa qayta login | SMS uchun to'lov |

Eskiz sozlamalari: `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM` (standart `4546`).
Eskiz'ning bepul test rejimida faqat Eskiz bergan test matni yuboriladi. OTP kodli SMS uchun
balans to'ldirilgan va SMS shabloni tasdiqlangan bo'lishi kerak.

Yangi provayder qo'shish: `SmsBackend.send(phone, text) -> SmsResult` ni yozib, `sms/base.py` dagi
`BACKENDS` ga qo'shing.

## Oqim

`services.send_sms()` → `NotificationLog` (status `pending`) → Celery `send_sms_task` →
`sent` / `failed`. Tarmoq va 5xx xatolarida eksponensial kechikish bilan 3 marta qayta uriniladi.
OTP matni jurnalga `******` bilan niqoblangan holda yoziladi.
