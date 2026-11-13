# logistics

Yetkazish narxi va muddati. Yetkazish faqat eshikkacha, narxini to'liq mijoz to'laydi.

## Hozirgi holat

Fargo va BTS API'lari hozircha ulanmagan. Narx admin panelda kiritiladigan tariflardan hisoblanadi
(`own` provayderi — o'z kuryerlarimiz).

- `DeliveryZone`:
  - zonaga viloyatlar va/yoki tumanlar biriktiriladi;
  - tuman bo'yicha moslik viloyatdan ustun turadi (masalan, chekka tuman uchun alohida narx);
  - har bir zonada yetkazish muddati (`eta_days_min..max`) beriladi.
- `DeliveryTariff`: zona + transport (`standard | truck`) + vazn chegarasi → narx.
  Savat og'irligiga mos keladigan eng kichik chegara tanlanadi.
  Savatda yirik texnika (`product.is_bulky`) bo'lsa, `truck` tarifi qo'llanadi.
- Qavatga ko'tarish (faqat yirik texnika uchun, sozlamalar):
  - lift yo'q bo'lsa: `lifting_price_per_floor` × (qavat − 1) × yirik tovarlar soni;
  - lift bor bo'lsa: `lifting_price_with_elevator` × yirik tovarlar soni;
  - narx sozlanmagan bo'lsa — xizmat taklif qilinmaydi.
- `DeliveryQuote`:
  - checkout'da hisoblangan narx 15 daqiqa amal qiladi;
  - savat yoki manzil o'zgarsa, yoki bir marta ishlatilgan bo'lsa — yaroqsiz bo'ladi va qayta hisoblash kerak.

## Provayderlar interfeysi

`providers/base.py`: `DeliveryProvider` — `calculate()`, `create_shipment()`, `track()`, `cancel()`.
`services.best_quote()` barcha yoqilgan provayderlardan (`LOGISTICS_PROVIDERS`) narx so'raydi.
Xato bergan provayder o'tkazib yuboriladi va eng arzoni tanlanadi.
`FargoProvider` va `BTSProvider` API'lar ulanganda shu interfeys bo'yicha qo'shiladi.

## Admin API (rol: `logistics_manager`)

`/api/v1/admin/delivery-zones`, `/api/v1/admin/delivery-tariffs?zone=` — CRUD.
