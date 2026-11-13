# marketing

Bannerlar, sayt matnlari, ommaviy chegirma, promokodlar, murojaatlar, bonus, to'plamlar va kun tovari.

## Bonus (keshbek) — `bonus.py`

Daftar (`BonusEntry`): balans — yozuvlar yig'indisi, 1 bonus = 1 so'm. Sozlamalar: `bonus_earn_percent`
(bo'sh — tizim o'chiq), `bonus_max_pay_percent` (tovarlar summasining ko'pi bilan necha foizi; 90 dan oshmaydi).

- Yoziladi: buyurtma **yetkazilganda** (`orders.state` → `bonus.earn`), pul bilan to'langan tovarlar summasidan.
- Sarflanadi: rasmiylashtirishda `use_bonus=true` — mumkin bo'lgan eng ko'p summa (`bonus.usable`); buyurtma
  tranzaksiyasi ichida foydalanuvchi qatori qulflanadi (ikki marta sarflab bo'lmaydi).
- Qaytadi: buyurtma bekor qilinsa yoki omborga qaytsa (`bonus.refund`), bir marta.
- API: `GET /bonus` (shartlar), `GET /me/bonus` (balans, tarix), `POST /admin/bonus/adjust` (administrator).

## Birga arzonroq — `bundles.py`

`Bundle(product, extra, discount_percent)`: asosiy tovar savatda bo'lsa, qo'shimcha tovarga chegirma. Har bir
asosiy dona bitta qo'shimcha donaga chegirma beradi; bitta donaga faqat bitta (eng katta) chegirma. Savat
(`bundle_discount`, `bundles`) va rasmiylashtirish summalarida hisobga olinadi; promokod undan keyin qo'llanadi.
API: `GET /products/{slug}/bundles`, `/admin/marketing/bundles`.

## Kun tovari — `deals.py`

`Deal(variant, price, starts_at, ends_at)`: boshlanganda variant narxi aksiya narxiga almashadi (eski narx
ustiga chiziladi), tugaganda qaytadi. Fon vazifasi shart emas: `deals.maybe_sync()` savat, rasmiylashtirish va
`GET /deals` so'ralganda chaqiriladi. Aksiya davomida narxni xodim o'zgartirgan bo'lsa — tugaganda tegilmaydi.
API: `GET /deals`, `/admin/marketing/deals` (yaratish, ro'yxat, `DELETE` — bekor qilish).
