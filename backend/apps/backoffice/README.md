# backoffice (1C o'rniga)

Ta'minotchilar, ombor hujjatlari va kassa. Buxgalteriya va soliq hisobotlarini alohida buxgalter yuritadi.
Tizim unga hisobot va eksport beradi.

## Hujjatlar

| Hujjat | Raqam | O'tkazilganda |
|---|---|---|
| Kirim (`PurchaseReceipt`) | `KR-000001` | qoldiq oshadi, seriya/IMEI ro'yxatga olinadi, tannarx qayta hisoblanadi |
| Ko'chirish (`StockTransfer`) | `KO-000001` | manba ombordan chiqadi, maqsad omborga kiradi, seriyalar ko'chadi |
| Hisobdan chiqarish (`WriteOff`) | `HC-000001` | qoldiq kamayadi, seriyalar `written_off`; sabab: brak, shikast, yo'qolgan, ta'minotchiga qaytarish |

Hujjatlar uchun qoidalar:
- Hujjat avval `draft` (qoralama) holatida bo'ladi va bu holatda erkin tahrirlanadi.
- "O'tkazish" (post) — hujjat qatorlari bitta tranzaksiyada bajariladi: yo hammasi o'tadi, yo hech biri.
- O'tkazilgan hujjat o'zgartirilmaydi va o'chirilmaydi. Xato bo'lsa, teskari hujjat qilinadi.
- Band qilingan (buyurtmadagi) tovarni ko'chirib yoki hisobdan chiqarib bo'lmaydi.

**Tannarx.** O'rtacha og'irlikli usulda hisoblanadi:

`yangi = (eski_qoldiq × eski_tannarx + kirim × xarid_narxi) / (eski_qoldiq + kirim)`

Buyurtmada tannarx "snapshot" qilib saqlanadi, marja hisoboti shundan olinadi.

## Kassa

- `CashAccount` — pul turgan joy: naqd kassa, bank hisobi yoki to'lov tizimi.
- `CashTransaction` — kirim yoki chiqim yozuvi, kategoriyasi bilan: sotuv, kuryerdan naqd, ta'minotchiga to'lov,
  qaytarish, xarajat, o'tkazma.
- Yozuvlar o'zgartirilmaydi va o'chirilmaydi. Xato yozuv teskari "tuzatish" yozuvi bilan bekor qilinadi (`reverse`).
- Naqd kassadan qoldiqdan ortiq pul chiqarib bo'lmaydi.
- Ta'minotchi qarzi = o'tkazilgan kirimlar − to'lovlar.

## API (`/api/v1/admin/backoffice/...`)

| Yo'l | Rol |
|---|---|
| `suppliers` (CRUD, `balance` bilan) | warehouse, finance |
| `receipts`, `transfers`, `write-offs` (+ `/{id}/post`, `/{id}/cancel`) | warehouse |
| `cash-accounts` (`balance` bilan), `cash` (+ `/{id}/reverse`) | finance |
| `stock-valuation` — ombor bo'yicha qoldiq qiymati | warehouse, finance |

Django admin'da (`/admin/`) xuddi shu hujjatlar bor. Ularni tanlab, "O'tkazish" amali bilan o'tkazish mumkin.
