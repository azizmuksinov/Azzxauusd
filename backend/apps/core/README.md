# core

Umumiy yordamchilar, boshqa modullar shularga tayanadi.

- `exceptions.py` — yagona xato formati `{"error": {"code", "message", "fields"?, ...}}` va `ApiError`.
- `phone.py` — `normalize_phone()` (`+998XXXXXXXXX` ga keltiradi), `mask_phone()` (loglar uchun).
- `translit.py` — o'zbek lotin → kirill (`O'zbekiston` → `Ўзбекистон`).
- `i18n.py` — `{"uz", "uz_cyrl", "ru"}` JSON maydonlar: `localize()`, `request_language()`
  (`?lang=` yoki `Accept-Language`). `uz_cyrl` bo'sh bo'lsa, lotindan avtomatik hosil qilinadi.
- `models.TimeStampedModel` — `created_at`, `updated_at`.
- `GET /health` — DB bilan aloqa tekshiruvi.
