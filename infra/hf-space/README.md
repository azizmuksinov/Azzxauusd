---
title: Onlayn dokon demo
emoji: 🛒
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Onlayn do'kon — DEMO API

**Bu demo muhit.** Faqat soxta (test) ma'lumotlar. Haqiqiy shaxsiy ma'lumot kiritmang:
qonunga ko'ra mijozlarning shaxsiy ma'lumotlari O'zbekistondagi serverda saqlanadi.

- Veb-do'kon: `/` (katalog, savat, SMS-kod bilan kirish, checkout, buyurtmalar)
- Admin panel: `/admin/` (back-office: kirim, ko'chirish, hisobdan chiqarish, kassa)
- Swagger: `/api/docs/`
- OpenAPI: `/api/schema/`
- Demo rejimda SMS yuborilmaydi: kirish sahifasida kod ekranda ko'rsatiladi.
- Onlayn to'lov demo: buyurtma sahifasida "To'lash (demo)" tugmasi.
- Space uxlab qolsa yoki qayta ishga tushsa, baza tozalanadi.

Kod GitHub'dagi asosiy repodan avtomatik joylanadi — bu yerda tahrirlamang.

## Xodim paneli administratori

Space **Settings → Variables and secrets** bo'limida ikkita **secret** qo'shing: `ADMIN_LOGIN` va
`ADMIN_PASSWORD` (parol kamida 10 belgi). Space qayta ishga tushganda shu login/parolli administrator
yaratiladi va namuna (demo) parollar yopiladi. Qolgan xodimlarga login/parolni administrator panelning
"Xodimlar" bo'limida beradi. Secretlar berilmagan bo'lsa — kirish sahifasida namuna login/parol ko'rsatiladi.

## Ma'lumotlarni saqlash (ixtiyoriy)

Bepul Space qayta ishga tushganda (yangilanish, 48 soatlik uyqu) diski tozalanadi. Space Secrets'ga yozish
huquqli `HF_TOKEN` qo'shilsa, `persist.py` baza va rasmlarni har 5 daqiqada (va to'xtashda) yopiq
`<egasi>/<space>-data` Dataset'iga saqlaydi va ishga tushishda tiklaydi. Boshqa Dataset: `DEMO_PERSIST_REPO`.
Token yo'q bo'lsa — har ishga tushishda yangi demo baza. AI kartochkalarni qo'lda saqlash uchun "AI kartochkalar"
bo'limida "Zaxira (JSON)" va "Zaxiradan tiklash" tugmalari bor.
