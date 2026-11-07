# accounts (auth)

SMS-kod bilan kirish, JWT, profil, yetkazish manzillari, xodim rollari.

## API

| Metod | Yo'l | Tavsif |
|---|---|---|
| POST | `/api/v1/auth/otp/request` | `{phone}` → `{expires_in, resend_in, debug_code?}` |
| POST | `/api/v1/auth/otp/verify` | `{phone, code}` → `{access, refresh, is_new_user}` |
| POST | `/api/v1/auth/token/refresh` | `{refresh}` → yangi juftlik (rotation) |
| POST | `/api/v1/auth/logout` | `{refresh}` → blacklist |
| GET / PATCH / DELETE | `/api/v1/me` | profil; DELETE — shaxsiy ma'lumotlarni anonimlashtiradi |
| GET / POST | `/api/v1/me/addresses` | manzillar |
| GET / PATCH / DELETE | `/api/v1/me/addresses/{id}` | |

Telefon har qanday formatda qabul qilinadi (`90 123 45 67`, `+998901234567`, ...).

## OTP xavfsizligi

- 6 xonali kod `secrets` bilan yaratiladi, 120 soniya amal qiladi, bir martalik.
- Keshda faqat HMAC-SHA256 xeshi saqlanadi, kodning o'zi bazaga ham, jurnalga ham yozilmaydi.
- 5 ta xato urinishdan keyin kod bekor qilinadi. Hisoblagich atomar, parallel so'rovlar bilan chetlab bo'lmaydi.
- Qayta yuborish oralig'i 60 s, bitta telefonga soatiga 5 ta, bitta IP'dan soatiga 20 ta so'rov.
- `debug_code` faqat `DEMO_MODE=true` bo'lganda qaytadi. Production sozlamasida bu rejim taqiqlangan.

## Manzillar

Qavat, lift turi (`none / passenger / freight`), mo'ljal, koordinata (O'zbekiston chegarasida
bo'lishi tekshiriladi), oluvchi ismi va telefoni saqlanadi. Har foydalanuvchida bitta asosiy manzil
bo'ladi (DB darajasida cheklov). Birinchi manzil avtomatik asosiy bo'ladi, asosiy manzil
o'chirilsa — keyingisi asosiy qilinadi.
MVP'da koordinatalar oddiy `decimal`. Logistika modulida PostGIS'ga o'tkaziladi.

## Rollar

Xaridorlar faqat SMS-kod bilan kiradi (paroli yo'q). Xodimlar Django guruhlari orqali boshqariladi:
`courier`, `warehouse`, `logistics_manager`, `content_manager`, `support`, `finance`, `admin`
(migratsiya `0002_roles`). Admin panelga kirish — telefon + parol.
