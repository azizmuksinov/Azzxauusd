# inventory

Omborlar, qoldiq, band qilish (rezerv), harakatlar jurnali, seriya raqam / IMEI hisobi.

## Modellar

- `Warehouse`:
  - `is_sellable=false` — ombordagi tovar saytda sotuvga hisoblanmaydi (masalan, nuqsonli tovarlar ombori).
- `Stock (warehouse, variant)`:
  - maydonlar: `on_hand` (jismonan bor), `reserved` (band), `available = on_hand − reserved`;
  - DB cheklovlari qoldiqni manfiy bo'lishiga va bandning qoldiqdan oshishiga yo'l qo'ymaydi.
- `StockMovement` — har bir o'zgarish: `delta`, keyingi qoldiq, sabab, hujjat, xodim.
- `Reservation` — buyurtma uchun band (`ref_type="order"`), muddati o'tsa Celery har daqiqada bo'shatadi.
- `SerialUnit` — har bir dona: seriya raqam, IMEI1/IMEI2 (Luhn tekshiruvi), status, tarix.

## Servislar (`services.py`) — qoldiq faqat shular orqali o'zgaradi

| Funksiya | Tavsif |
|---|---|
| `receive(wh, variant, qty, serials=...)` | kirim; seriyali tovarda donalar soni = seriyalar soni |
| `adjust(wh, variant, new_on_hand, comment=)` | inventarizatsiya; band qilingandan kam qilib bo'lmaydi |
| `reserve(ref_type, ref_id, [(variant, qty)])` | hammasi yoki hech biri; kerak bo'lsa bir nechta omborga bo'linadi |
| `release(ref_type, ref_id)` | bandni bekor qilish |
| `commit(ref_type, ref_id)` | sotuv: tovar ombordan chiqdi |
| `release_expired()` | muddati o'tgan bandlar (celery-beat, 60 s) |

Bir vaqtdagi so'rovlarda xavfsiz: qatorlar `SELECT ... FOR UPDATE` bilan qulflanadi. Test bunga misol:
oxirgi dona uchun 5 ta parallel so'rov — faqat bittasi muvaffaqiyatli.

Qaysi ombordan jo'natish — hozircha bo'sh qoldig'i eng ko'p ombor. Mijoz manziliga eng yaqin omborni tanlash
logistics modulida qilinadi (S-18 javobiga bog'liq).

## Admin API (`/api/v1/admin`, rol: `warehouse`)

| Yo'l | Tavsif |
|---|---|
| `GET/POST/PATCH warehouses` | omborlar |
| `GET stock?warehouse=&sku=&low_stock=3` | qoldiqlar |
| `POST stock/receipts` | `{warehouse, variant, qty, serials:[{imei1}], document}` |
| `POST stock/adjustments` | `{warehouse, variant, on_hand, comment}` |
| `GET stock/movements?variant=` | jurnal |
| `GET serials?q=<seriya yoki IMEI>`, `GET serials/{id}` | to'liq tarix (`warehouse` va `support` rollari) |
