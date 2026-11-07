# geo

Viloyat va tumanlar ma'lumotnomasi. Manzil va yetkazish narxini hisoblash shunga tayanadi.

- Modellar: `Region` (SOATO kodi bilan), `District` (`bts_city_code`, `fargo_city_code` — provayder kodlari).
- Migratsiya `0002_seed_regions`: 14 ta viloyat va Toshkent shahrining 12 ta tumani (3 tilda).
  Boshqa viloyatlarning tumanlari keyin qo'shiladi.
- API: `GET /api/v1/geo/regions`, `GET /api/v1/geo/regions/{id}/districts` — ochiq, tilga qarab nom qaytaradi.
