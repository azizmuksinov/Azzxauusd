# web — xaridor veb-do'koni (Next.js 15)

Sahifalar:
- bosh sahifa;
- kategoriya — filtrlar (brend, narx, xususiyatlar, "faqat sotuvda borlari") va saralash bilan;
- tovar sahifasi — variantlar, xususiyatlar, o'xshash tovarlar;
- qidiruv va avtoto'ldirish;
- savat (mehmon uchun ham);
- SMS-kod bilan kirish;
- checkout — manzil, yetkazish narxi, to'lov usuli;
- buyurtmalar — holat tarixi, onlayn to'lash (demo), bekor qilish.

Xodimlar uchun (interfeys hozircha faqat o'zbekcha):
- `/kuryer` — kuryer ilovasi (telefon ekrani uchun): marshrut, qo'ng'iroq, "yo'lga chiqdim",
  eshik oldida tekshiruv va topshirish (naqd yoki Payme/Click QR), rad etish, "yetkazib bo'lmadi", qo'ldagi naqd;
- `/xodim` — xodim paneli: yig'ish va qadoqlash (IMEI tanlash), marshrut varaqlari, kuryer kassasi, kuryerlar.
  Bo'limlar rolga qarab ko'rinadi.

Demo'da (`NEXT_PUBLIC_DEMO=1`) login sahifasida demo xodim raqamlari ko'rsatiladi:
kuryer `+998 90 000 00 01`, ombor/logist/kassir `+998 90 000 00 02`.

Tillar: o'zbek (lotin), o'zbek (kirill — lotindan avtomatik), rus.

## Ishga tushirish

```bash
# backend 8000-portda ishlayotgan bo'lsin (backend/README)
cd web
npm install
API_ORIGIN=http://127.0.0.1:8000 npm run dev    # http://localhost:3000
```

Lokal rejimda `/api/v1/*` so'rovlari Next rewrite orqali Django'ga yuboriladi.
Admin panelni to'g'ridan-to'g'ri `http://127.0.0.1:8000/admin/` da oching.
Demo va production'da oldida nginx turadi: `/api`, `/admin`, `/static` Django'ga, qolgani Next'ga yo'naltiriladi
(`infra/hf-space/nginx.conf`).

## Tuzilishi

- `lib/api.ts`:
  - JWT access/refresh, 401 bo'lsa tokenni bir marta yangilaydi;
  - mehmon savati (`X-Cart-Token`) va til sarlavhasini qo'shadi;
  - xatolarni `ApiError` (`code`, `message`) ko'rinishida qaytaradi.
- `lib/i18n.ts` — UI matnlari (uz, ru); kirill yozuvi `lib/translit.ts` orqali hosil qilinadi.
- `components/providers.tsx`:
  - umumiy holat: til, foydalanuvchi, savat;
  - login'dan keyin mehmon savatini foydalanuvchi savatiga birlashtiradi.
- Demo'da tovar rasmlari yo'q, o'rniga kategoriya belgisi ko'rsatiladi.

## Tekshiruv

```bash
npm run typecheck && npm run build
```
