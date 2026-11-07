# 04. Ochiq savollar

Quyidagi savollarga javob berilmaguncha tegishli joylar taxmin bilan yozilmaydi.
**Bloklovchi** — kodni boshlashdan oldin kerak. **Keyinroq** — tegishli modulga yetganda kerak.

## Umumiy

| # | Savol | Mening tavsiyam | Muhimligi |
|---|---|---|---|
| S-01 | Boshqaruv paneli: MVP uchun Django Admin (Unfold) yetadimi yoki darhol alohida React/Next.js panel kerakmi? | MVP — Django Admin + yig'ish/marshrut uchun 3–4 ta maxsus sahifa | Bloklovchi (admin uchun) |
| S-02 | ✅ Yangi repo ochiladi (javob berildi). | — | — |
| S-03 | 🟡 Bepul variant: demo'da `console` (kod ekranda). Eskiz ulagichi tayyor — haqiqiy SMS uchun Eskiz akkaunti (email/parol), balans va tasdiqlangan shablon kerak. | Eskiz | Production oldidan |
| S-04 | Xarita va geokoder: Yandex Maps, Google Maps yoki OSM? API kaliti bormi? | Yandex (O'zbekistonda manzillar bazasi to'liqroq) | Keyinroq |
| S-20 | 🟡 Demo: Hugging Face `azizmuksinov/Azentertrade` Space'i (yopiq) ishlatiladi — yangi Docker Space uchun PRO kerak edi. Production uchun O'zbekistondagi qaysi data-markaz? | MVP prod — docker compose, 2 server (app + db) | Keyinroq (prod) |

## Checkout va to'lov

| # | Savol | Muhimligi |
|---|---|---|
| S-05 | ✅ Yetkazish narxini to'liq mijoz to'laydi (javob berildi). Bepul yetkazish chegarasi yo'q. | — |
| S-06 | ✅ Eshikda to'lov uchun summa chegarasi yo'q; oldindan faqat yetkazish narxi to'lanadi (javob berildi). | — |
| S-07 | ✅ Eshikda to'lovda yetkazish narxi oldindan onlayn to'lanadi — to'langach buyurtma avtomatik `cod_confirmed` (javob asosida). | — |
| S-14 | ⏸ To'lovlar hozircha demo rejimda (javob berildi). Payme, Click, Uzum test kalitlari va Uzum rasmiy hujjati — ishga tushirishdan oldin. | Production oldidan |
| S-15 | Fiskal chek: qaysi virtual kassa / OFD provayderi orqali? Avans uchun alohida chek, yetkazilganda yakuniy chek kerakmi? Fargo/BTS kuryeri naqd olganda chekni kim chiqaradi? Barcha tovarlarda MXIK (IKPU) kodlari bormi? | Keyinroq (payments) |
| S-17 | Nasiya hamkori kim (bitta yoki bir nechta)? Ularning API hujjati, ariza oqimi (hamkor sahifasiga yo'naltirishmi yoki bizda forma), bizda pasport/PINFL saqlash kerakmi? | Keyinroq |
| S-19 | Qaytarish siyosati: necha kun ichida sifatli tovar qaytariladi? Qaysi toifalar qaytarilmaydi? Kafolat ta'mirini o'zimiz qilamizmi yoki brend servis markazlariga yo'naltiramizmi? | Keyinroq (warranty) |

## Logistika

| # | Savol | Muhimligi |
|---|---|---|
| S-08 | ✅ Mijoz topilmasa 3 ta urinish, keyin tovar omborga qaytadi; buyurtmani kuryerga logist biriktiradi; eshikda naqd yoki Payme/Click QR (terminal yo'q); naqd kun oxirida kassirga (javob berildi). | — |
| S-25 | Eshik oldida mijoz tasdig'i: SMS-kod (har topshirishda SMS xarajati) va foto kerakmi? Akt PDF mijozga yuborilsinmi? | Keyinroq |
| S-26 | Eshikda rad etilganda yoki 3 urinishdan keyin qaytganda: oldindan to'langan yetkazish narxi mijozga qaytariladimi? Tovarda nuqson bo'lsa-chi? | Keyinroq |
| S-09 | ⏸ Fargo/BTS hozircha ulanmaydi (javob berildi) — narx admin panelda kiritiladigan tariflardan. Smart routing provayderlar ulanganda. | Keyinroq |
| S-10 | ⏸ Qavatga ko'tarish xizmati hozircha yo'q (javob berildi); Fargo/BTS yirik tovar masalasi — ular ulanganda. | Keyinroq |
| S-11 | BTS: test va prod token, to'liq API hujjati (shahar/filial ma'lumotnomasi, jo'natuvchi filiali, COD parametrlari, webhook bormi). | Keyinroq |
| S-12 | Fargo: API hujjati va kalitlar. | Keyinroq |
| S-13 | Fargo/BTS orqali yetkazilganda eshik oldida tekshiruv (ochish, yoqib ko'rish, seriya raqam, akt) kafolatlanadimi? Yo'q bo'lsa, bunday buyurtmalarda nima qilamiz? | Keyinroq |
| S-18 | 🟡 Nechta ombor bor va qayerda? Buyurtma qaysi ombordan jo'natilishini tizim tanlaydimi? _Hozircha: model istalgan sondagi omborni qo'llab-quvvatlaydi; buyurtma bo'sh qoldig'i eng ko'p ombordan band qilinadi._ | Keyinroq (logistics) |
| S-22 | O'z kuryerlarimiz zonasi: faqat Toshkent shahrimi yoki Toshkent viloyati ham? Chegarani poligon qilib berasizmi yoki tumanlar ro'yxatimi? Yuk mashinasi va ko'tarish tariflari qancha? | Keyinroq |

## 1C

| # | Savol | Muhimligi |
|---|---|---|
| S-16 | ✅ 1C ishlatilmaydi — tizim yagona manba (javob berildi). | — |
| S-23 | ✅ Narx va qoldiq manbai — shu tizim (1C yo'q). | — |
| S-24 | ✅ Ta'minotchilar, kirim hujjatlari, ko'chirish, kassa — kerak; buxgalteriya va soliq hisobotlarini alohida buxgalter yuritadi (javob berildi). Tizim hisobot va eksport beradi. | — |

## Jarayon

| # | Savol |
|---|---|
| S-21 | Muddatlar va jamoa: veb va mobilni ham men yozamanmi yoki faqat backend + API kontraktmi? MVP qaysi sanaga kerak? |
