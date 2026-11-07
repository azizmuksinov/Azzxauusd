# catalog

Kategoriyalar, brendlar, xususiyatlar (atributlar), tovarlar va variantlar (SKU), qidiruv, solishtirish,
sevimlilar, Excel import.

## Modellar

- `Category`: daraxt ko'rinishida (`parent`). Filtrlar uchun xususiyatlar `CategoryAttribute` orqali biriktiriladi
  va ichki kategoriyalarga meros bo'lib o'tadi.
- `Attribute`: turlari `number | text | bool | enum`. `is_filterable` bo'lsa, filtr va fasetlarda chiqadi,
  `is_comparable` bo'lsa — solishtirish jadvalida. `enum` turida variantlar `AttributeOption` da.
- `Product` → `ProductVariant` (SKU, narx, eski narx, tannarx, gabarit, `onec_guid`).
  - `AttributeValue.variant = null` — tovarning umumiy xususiyati (ekran).
  - Variantga xos qiymat (xotira, rang) — `AttributeValue.variant` to'ldirilgan bo'ladi.
- Fiskal chek uchun: `mxik_code`, `package_code`, `vat_percent`. MXIK kodisiz tovarni sotuvga chiqarib bo'lmaydi.
- `is_bulky` — yirik texnika: checkout'da qavat va lift so'raladi, yuk mashinasi tarifi qo'llanadi.
- `serial_tracking` — `none | serial | imei | imei2`: kirimda nechta seriya raqam yoki IMEI talab qilinishini belgilaydi.

## Ommaviy API (`/api/v1`)

| Yo'l | Tavsif |
|---|---|
| `GET /categories` | daraxt |
| `GET /categories/{slug}` | breadcrumbs + ichki kategoriyalar |
| `GET /categories/{slug}/filters` | fasetlar: brendlar (soni bilan), narx oralig'i, xususiyatlar |
| `GET /brands`, `/brands/{slug}` | |
| `GET /products` | filtr, saralash, sahifalash (`page`, `page_size` ≤ 60) |
| `GET /products/{slug}` | variantlar, xususiyatlar guruhlab, rasmlar, `stock_status` |
| `GET /products/{slug}/similar` | shu kategoriya, narx ±30% |
| `GET /search?q=` · `/search/suggest?q=` | qidiruv, avtoto'ldirish |
| `GET /compare?products=1,2,3` | solishtirish jadvali (`is_different` bilan) |
| `GET/POST /me/favorites`, `DELETE /me/favorites/{id}` | sevimlilar |
| `GET/POST /me/compare`, `DELETE /me/compare/{id}` | solishtirish ro'yxati (ko'pi bilan 6 ta) |

Filtrlar:
- `category=` — ichki kategoriyalar bilan birga.
- `brand=samsung,lg`, `price_min=`, `price_max=`, `in_stock=true`.
- Xususiyatlar: `f[screen_size]=50..65`, `f[color]=black,white`, `f[smart_tv]=true`.

Saralash `sort=`: `popular` (standart) `| new | price_asc | price_desc | rating | relevance`.

Til: `?lang=uz|uz_cyrl|ru` yoki `Accept-Language`. `uz_cyrl` bo'sh bo'lsa, lotindan avtomatik hosil qilinadi.
Qoldiq aniq son bilan emas, `stock_status` orqali ko'rsatiladi: `in_stock | low | out_of_stock`.
Tannarx (`cost_price`) ommaviy javoblarda va qidiruv indeksida hech qachon chiqmaydi.

## Qidiruv (`SEARCH_BACKEND`)

| Qiymat | Qayerda | Qanday ishlaydi |
|---|---|---|
| `db` | demo, test | `search_text` ustuni bo'yicha qidiradi: 3 tildagi nom, lotindan kirill, brend, SKU, kategoriya. Har bir so'z mos kelishi kerak |
| `meilisearch` | production | xatolarga chidamli (typo-tolerant) qidiruv, natijalar relevantlik bo'yicha. Meilisearch ishlamay qolsa, avtomatik `db` ga o'tadi |

Filtr va fasetlar har doim DB'da hisoblanadi, shuning uchun ikkala backend bir xil natija beradi.
Indeks tovar o'zgarganda signal → Celery orqali yangilanadi.

## Narxlar (S-23)

- Narx faqat `PATCH /api/v1/admin/variants/{id}/price` orqali o'zgaradi va har o'zgarish `PriceHistory` ga yoziladi.
- `CATALOG_MANUAL_PRICE_LOCKS=true` (standart): qo'lda yoki Excel'da o'zgartirilgan narx qulflanadi,
  1C sinxroni (`apply_1c_price`) unga tegmaydi.
- `false` bo'lsa, narx manbai har doim 1C.

## Admin API (`/api/v1/admin`, rol: `content_manager`)

- CRUD: `categories`, `brands`, `attributes` (variantlari bilan), `products` (xususiyatlari bilan),
  `variants`, `product-images`.
- O'chirish: tovar va variant o'chirilmaydi, arxivlanadi yoki nofaol qilinadi, chunki buyurtmalar tarixi saqlanishi kerak.
- Excel: `GET imports/template.xlsx`, `POST imports` (`file`, `dry_run`), `GET imports/{id}` — har bir xato qator raqami bilan.
  Qatorlar SKU bo'yicha moslanadi: bor SKU — narx yangilanadi, yangi SKU — tovar `draft` holatida yaratiladi.

## Demo

`python manage.py seed_demo` — 14 ta soxta tovar, 8 ta kategoriya, xususiyatlar va qoldiq (faqat DEMO/DEBUG).
