# orders (checkout + buyurtmalar)

## Checkout oqimi

1. `POST /api/v1/checkout/delivery-options {address_id}` → `quote_id`, yetkazish narxi, muddat, ko'tarish narxi.
2. `POST /api/v1/checkout/summary {address_id, quote_id, lifting}` → summalar va to'lov usullari
   (`available`, `required_prepayment`, izoh).
3. `POST /api/v1/orders {address_id, quote_id, payment_method, lifting, comment}`.
   `Idempotency-Key` sarlavhasi majburiy, bir xil kalit bilan qayta yuborilsa — o'sha buyurtma qaytadi.

Buyurtma yaratilganda:
- tovarlar omborda band qilinadi (hammasi yoki hech biri);
- narx, nom, tannarx, MXIK va manzil "snapshot" sifatida saqlanadi;
- quote ishlatilgan deb belgilanadi va savat tozalanadi.

## To'lov qoidalari (sozlamalar, S-06)

| Sozlama | Ma'nosi |
|---|---|
| `cod_max_amount` | Eshik oldida to'lov mumkin bo'lgan maksimal summa. `None` — cheklovsiz |
| `cod_prepayment_percent` | Chegaradan qimmat buyurtmada avans foizi. `100` — faqat to'liq oldindan to'lov |
| `online_payment_ttl_minutes` | Onlayn to'lov (yoki avans) muddati; o'tsa buyurtma bekor bo'ladi va tovar bo'shaydi |

Onlayn to'lov (Payme, Click, Uzum) — keyingi bosqich (payments moduli).

## Statuslar

`state.py` dagi mashina (`docs/01-arxitektura.md`, 3-bo'lim). Status faqat `transition()` orqali o'zgaradi:
- qatorni qulflaydi, o'tishga ruxsat borligini tekshiradi va tarixga yozadi;
- yon ta'sirlarni bajaradi:
  - `cancelled` — band bo'shatiladi, to'langan bo'lsa `refund_pending`;
  - `handed_to_courier` — tovar ombordan chiqadi (`commit`).

Xaridor buyurtmani `packed` holatigacha bekor qila oladi: `POST /api/v1/orders/{number}/cancel`.

## API

| Metod | Yo'l |
|---|---|
| GET | `/api/v1/orders?status=active\|completed` |
| GET | `/api/v1/orders/{number}` |
| POST | `/api/v1/orders/{number}/cancel` `{reason}` |
