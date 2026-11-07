# Onlayn do'kon — loyiha hujjatlari

Bitta sotuvchili (single-vendor) maishiy texnika va elektronika do'koni. Yetkazish faqat eshikkacha:
o'z kuryerlarimiz, Fargo va BTS Express orqali.

| Hujjat | Mazmuni |
|---|---|
| [01-arxitektura.md](01-arxitektura.md) | Stek, modullar, statuslar mashinasi, smart routing, to'lovlar, xavfsizlik, 1C |
| [02-mb-sxemasi.md](02-mb-sxemasi.md) | ER-diagrammalar (Mermaid), indekslar va cheklovlar |
| [03-api.md](03-api.md) | REST API ro'yxati: xaridor, kuryer, admin, webhooklar |
| [04-savollar.md](04-savollar.md) | Ochiq savollar — javobsiz kod yozilmaydi |

## Bosqichlar

1. ✅ MB sxemasi va API ro'yxati (shu hujjatlar) — ko'rib chiqish kutilmoqda
2. ✅ auth (core, geo, notifications, accounts)
3. ✅ catalog/inventory
4. ⏳ cart/checkout → payments → orders → logistics → admin → sync_1c
   (har modul: modellar, API, testlar, README)
