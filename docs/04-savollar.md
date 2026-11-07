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
| S-06 | COD chegarasi qancha (`cod_max_amount`)? Undan yuqorida avans foizi qancha yoki faqat 100% oldindan to'lovmi? Bu chegara toifaga bog'liqmi (masalan, telefonlar uchun pastroq)? | Bloklovchi |
| S-07 | `cod_confirmed` qanday bo'ladi: operator qo'ng'iroq qiladimi, mijoz SMS-kod bilan tasdiqlaydimi yoki COD buyurtma avtomatik tasdiqlanadimi? | Bloklovchi |
| S-14 | Payme, Click, Uzum Bank merchant akkauntlari bormi? Test (sandbox) kalitlari va Uzum Bank hujjatining versiyasi kerak. | Keyinroq (payments) |
| S-15 | Fiskal chek: qaysi virtual kassa / OFD provayderi orqali? Avans uchun alohida chek, yetkazilganda yakuniy chek kerakmi? Fargo/BTS kuryeri naqd olganda chekni kim chiqaradi? Barcha tovarlarda MXIK (IKPU) kodlari bormi? | Keyinroq (payments) |
| S-17 | Nasiya hamkori kim (bitta yoki bir nechta)? Ularning API hujjati, ariza oqimi (hamkor sahifasiga yo'naltirishmi yoki bizda forma), bizda pasport/PINFL saqlash kerakmi? | Keyinroq |
| S-19 | Qaytarish siyosati: necha kun ichida sifatli tovar qaytariladi? Qaysi toifalar qaytarilmaydi? Kafolat ta'mirini o'zimiz qilamizmi yoki brend servis markazlariga yo'naltiramizmi? | Keyinroq (warranty) |

## Logistika

| # | Savol | Muhimligi |
|---|---|---|
| S-08 | Mijoz uyda bo'lmasa: nechta qayta urinish, keyin qaytarishmi? Statuslar ro'yxatiga `delivery_failed` qo'shamizmi yoki `out_for_delivery → in_transit` bilan ifodalaymizmi? | Keyinroq |
| S-09 | ⏸ Fargo/BTS hozircha ulanmaydi (javob berildi) — narx admin panelda kiritiladigan tariflardan. Smart routing provayderlar ulanganda. | Keyinroq |
| S-10 | Fargo va BTS yirik texnikani (muzlatkich, kir yuvish mashinasi) qabul qiladimi va qavatga ko'taradimi? Viloyatlarda yirik tovarni kim yetkazadi? | Keyinroq |
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
| S-24 | 1C o'rniga qaysi ishlar kerak: ta'minotchilar va kirim hujjatlari (xarid narxi), omborlar orasida ko'chirish, kassa — yetadimi? Buxgalteriya/soliq hisobotlarini kim yuritadi (alohida buxgalter/dastur)? | backoffice oldidan |

## Jarayon

| # | Savol |
|---|---|
| S-21 | Muddatlar va jamoa: veb va mobilni ham men yozamanmi yoki faqat backend + API kontraktmi? MVP qaysi sanaga kerak? |
