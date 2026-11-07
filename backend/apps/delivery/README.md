# delivery — yig'ish, kuryerlar, marshrutlar, eshik oldida topshirish

Ombordan eshikkacha bo'lgan jarayon (o'z kuryerlarimiz). Fargo/BTS ulanganda ular `logistics.providers` orqali qo'shiladi.

## Jarayon

| Qadam | Kim | API | Buyurtma holati |
|---|---|---|---|
| Yig'ishni boshlash | omborchi | `POST /admin/orders/{n}/start-picking` | `picking` |
| Qadoqlash (+ IMEI/seriya tanlash) | omborchi | `POST /admin/orders/{n}/pack` | `packed` |
| Marshrut varag'i (`MV-…`) | logist | `POST /admin/route-sheets` | — |
| Kuryerga berish | omborchi/logist | `POST /admin/route-sheets/{id}/issue` | `handed_to_courier`, tovar ombordan chiqadi |
| Yo'lga chiqdim (mijozga SMS) | kuryer | `POST /courier/stops/{id}/start` | `out_for_delivery` |
| Topshirdim (akt `TA-…`) | kuryer | `POST /courier/stops/{id}/deliver` | `delivered` |
| Rad etdi | kuryer | `POST /courier/stops/{id}/refuse` | `refused_at_door` |
| Yetkazib bo'lmadi | kuryer | `POST /courier/stops/{id}/fail` | `in_transit` |
| Kun yakuni | omborchi/logist | `POST /admin/route-sheets/{id}/close` | rad etilgan / urinishi tugagan → `returned` |
| Naqd pulni qabul qilish (`KN-…`) | kassir | `POST /admin/courier-cash/handovers` | — |

## Qoidalar

- Bitta buyurtma bir vaqtda faqat bitta ochiq marshrutda (DB cheklovi `uniq_open_stop_per_order`).
- Marshrutga faqat `packed` yoki `in_transit` (urinishlari tugamagan) buyurtma qo'shiladi;
  yirik tovar (`delivery_vehicle=truck`) faqat yuk mashinali kuryerga;
  `packed` buyurtma tovari marshrut omborida band qilingan bo'lishi kerak.
- **3 urinish** (S-08): muvaffaqiyatsiz urinishlar (`not_home`, `no_answer`, `wrong_address`, `rescheduled`)
  `delivery_max_attempts` ga yetsa, marshrut yopilganda tovar omborga qaytadi.
  Borilmagan nuqta (`not_visited`) urinish hisoblanmaydi.
- **Eshikda to'lov**: qolgan summa naqd (`CodCollection` — kuryer qarzi) yoki Payme/Click QR
  (`/courier/stops/{id}/qr`, `payments.services.payable_at_door`). Naqd/QR olinmasdan "topshirdim" bo'lmaydi.
  Payme chekida bu holda faqat tovarlar bo'ladi (yetkazish oldindan to'langan).
- **Kassa**: kassir kuryerning barcha topshirilmagan naqdini (yoki tanlanganlarini) faqat `cash` turidagi
  hisobga qabul qiladi → `backoffice.CashTransaction(category=courier_cod)`.
- **Seriyalar**: qadoqlashda `reserved`, kuryerga berilganda `sold`, qaytganda yoki bekor qilinganda `in_stock`.
  Qaytgan tovar omborga sotuvga yaroqli bo'lib kiradi — nuqsonli bo'lsa, back-office'da hisobdan chiqariladi.
- **Qaytarish (S-26)**: eshikda sababi bilan rad etilsa — to'langan hamma summa (yetkazish narxi ham);
  3 urinishda bog'lanib bo'lmasa — yetkazish narxi qaytarilmaydi. Summa `Order.refund_due` da;
  kassir `POST /admin/orders/{n}/refund` bilan qaytaradi (kassadan chiqim).

## Demo

`seed_demo` ikkita xodim yaratadi: kuryer `+998900000001` (yuk mashinali), xodim `+998900000002`
(warehouse, logistics_manager, finance, support). Demo'da OTP kodi ekranda chiqadi.
Veb: `/kuryer`, `/xodim`.

## Hali yo'q

Foto va mijoz SMS-kodi bilan tasdiqlash, akt PDF (S-25); avtomatik marshrut rejalash; joylashuvni kuzatish;
OFD cheki (S-15).
