# cart

Xaridor savati. Login qilmagan mehmon ham savat to'ldira oladi.

- Mehmon: birinchi `POST /cart/items` javobida `guest_token` keladi (`X-Cart-Token` sarlavhasida ham).
  Keyingi so'rovlarda shu token `X-Cart-Token` sarlavhasida yuboriladi.
- Login'dan keyin `POST /cart/merge {guest_token}` — mehmon savati foydalanuvchi savatiga qo'shiladi.
- Narx savatda saqlanmaydi: har doim tovarning joriy narxi ko'rsatiladi.
- Cheklovlar:
  - bitta tovardan ko'pi bilan `cart_max_qty_per_item` dona (sozlama, standart 10);
  - qo'shiladigan miqdor ombordagi bo'sh qoldiqdan oshmasligi kerak.
- Qator `problem` maydoni:
  - `unavailable` — tovar sotuvdan olingan;
  - `not_enough_stock` — qoldiq kamaygan.
  - Muammoli qator bo'lsa, `can_checkout=false` bo'ladi.
- 30 kundan eski mehmon savatlari kuniga bir marta o'chiriladi (celery-beat).

| Metod | Yo'l |
|---|---|
| GET / DELETE | `/api/v1/cart` |
| POST | `/api/v1/cart/items` `{variant_id, qty}` |
| PATCH / DELETE | `/api/v1/cart/items/{id}` |
| POST | `/api/v1/cart/merge` |
