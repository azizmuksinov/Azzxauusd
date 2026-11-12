"""Ta'minotchi faylini o'qish: ustunlar har xil bo'lishi mumkin — sarlavhalar bo'yicha aniqlanadi."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

KEYWORDS = {
    "name": [
        "nomi",
        "nom ",
        "наимен",
        "назван",
        "товар",
        "tovar",
        "mahsulot",
        "name",
        "product",
    ],
    "sku": ["artikul", "артикул", "sku", "kod", "код", "code", "article"],
    "price": ["narx", "цена", "price", "xarid", "закуп", "стоимост", "sum", "сумма"],
    "qty": ["soni", "кол", "qty", "miqdor", "остат", "quantity"],
    "brand": ["brend", "бренд", "brand", "марка", "ishlab chiqaruvchi", "производ"],
}


# "Model" ustuni ko'pincha seriya nomi xolos ("Aspire Lite", "Laptop") — to'liq nom ustuni bo'lmasa olinadi.
NAME_WEAK = ["model", "модел"]

# Butun so'z sifatida: "сум" "Сумма" (jami ustuni) ichida, "som" boshqa so'zlar ichida uchramasin.
CURRENCY_MARKS = {
    "USD": [r"\$", r"\busd\b", r"\bу\.\s?е\b", r"\bдолл", r"\bdollar"],
    # qo'shimchalar: so'mda, so'mlik, сумах, сумов, сўмда...
    "UZS": [
        r"\bсум(ы|ов|ах|ам)?\b",
        r"\bso['ʻ‘’`]?m(da|ga|lik|dan)?\b",
        r"\buzs\b",
        r"\bсўм(да|га|лик|дан)?\b",
    ],
}


def detect_currency(texts: list[str]) -> str:
    """Valyuta faqat aniq belgi bo'lsa aniqlanadi; taxmin qilinmaydi."""
    low = " ".join(texts).lower()
    found = [cur for cur, marks in CURRENCY_MARKS.items() if any(re.search(m, low) for m in marks)]
    return found[0] if len(found) == 1 else ""


class ExcelError(Exception):
    pass


@dataclass
class Row:
    number: int
    name: str
    sku: str
    price: Decimal | None
    qty: int | None
    brand: str
    raw: dict
    sheet: str = ""


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _decimal(v) -> Decimal | None:
    s = _text(v).replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d.quantize(Decimal("0.01")) if d >= 0 else None


def detect_columns(headers: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, h in enumerate(headers):
        low = f"{h.lower()} "
        for key, words in KEYWORDS.items():
            if key not in found and any(w in low for w in words):
                found[key] = idx
                break
    if "name" not in found:
        for idx, h in enumerate(headers):
            if idx not in found.values() and any(w in h.lower() for w in NAME_WEAK):
                found["name"] = idx
                break
    return found


def _better_name_column(cols: dict[str, int], headers: list[str], body: list[list[str]]) -> int | None:
    """Nom ustuni takrorlanuvchi qisqa qiymatlardan iborat bo'lsa (seriya/tur nomi), yonida esa har qatorda
    har xil uzun matnli ustun bo'lsa — nom o'sha. Aks holda None."""
    if len(body) < 4:
        return None

    def stats(i: int) -> tuple[float, float]:
        values = [r[i] for r in body if i < len(r) and r[i]]
        if len(values) < len(body) * 0.8:
            return 0.0, 0.0
        return len(set(values)) / len(values), sum(len(v) for v in values) / len(values)

    uniq, avg = stats(cols["name"])
    if uniq >= 0.8:
        return None
    best, best_len = None, avg * 1.5
    for i in range(len(headers)):
        if i in cols.values():
            continue
        u, a = stats(i)
        if u >= 0.9 and a > best_len and a >= 20:
            best, best_len = i, a
    return best


def _qty(text: str) -> int | None:
    """Soni: "36", "12.0", ">1000", "50 шт", "1 000" → butun son."""
    m = re.search(r"\d[\d\s\u00a0]*", text or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group())
    return int(digits) if digits and len(digits) <= 9 else None


SHEET_KEY = (
    "Varaq"  # ko'p varaqli faylda qatorga varaq (bo'lim) nomi qo'shiladi — AI kategoriya uchun ko'radi
)


@dataclass
class Sheet:
    name: str
    columns: dict[str, str]  # {kalit: sarlavha}
    rows: list[Row]
    texts: list[str]  # valyutani aniqlash uchun: sarlavha qatorlari va narx kataklari


def _read_sheet(title: str, rows: list[list[str]], *, strict: bool) -> Sheet | None:
    """Bitta varaq. `strict` (ko'p varaqli fayl): jadvalga o'xshamagan varaq (shartlar, aloqa ma'lumoti)
    tashlab ketiladi — None; aks holda sababi bilan ExcelError."""

    def fail(message: str):
        if strict:
            return None
        raise ExcelError(message)

    header_idx = next((i for i, r in enumerate(rows[:15]) if sum(1 for c in r if c) >= 2), None)
    if header_idx is None:
        return fail("Faylda sarlavha qatori topilmadi.")
    headers = rows[header_idx]
    body = [r for r in rows[header_idx + 1 :] if any(r)]
    cols = detect_columns(headers)
    if "name" not in cols:
        # Nom ustuni sarlavhasidan tanilmadi — eng uzun matnli ustun. Ko'p varaqli faylda bunga faqat
        # narx/soni/artikul ustuni bor varaqda ishoniladi (aks holda bu jadval emas, oddiy matn).
        if strict and not ({"price", "qty", "sku"} & cols.keys()):
            return None
        lengths = [sum(len(r[i]) for r in body if i < len(r)) for i in range(len(headers))]
        if not lengths or max(lengths) == 0:
            return fail("Tovar nomi ustuni topilmadi.")
        cols["name"] = lengths.index(max(lengths))
    elif (better := _better_name_column(cols, headers, body)) is not None:
        cols["name"] = better

    def cell(r, key):
        i = cols.get(key)
        return r[i] if i is not None and i < len(r) else ""

    out: list[Row] = []
    for n, r in enumerate(body, start=header_idx + 2):
        name = cell(r, "name")
        if not name:
            continue
        # Guruh sarlavhasi ("Газ Плита"): narx va soni ustunlari bor, lekin qatorda ikkalasi ham bo'sh.
        if ("price" in cols or "qty" in cols) and not cell(r, "price") and not cell(r, "qty"):
            continue
        out.append(
            Row(
                number=n,
                name=name[:500],
                sku=cell(r, "sku")[:64],
                price=_decimal(cell(r, "price")),
                qty=_qty(cell(r, "qty")),
                brand=cell(r, "brand"),
                raw={headers[i] or f"#{i + 1}": v for i, v in enumerate(r) if v},
                sheet=title,
            )
        )
    if not out:
        return fail("Faylda tovar topilmadi.")
    texts = [c for r in rows[: header_idx + 1] for c in r]  # sarlavha va undan yuqoridagi qatorlar
    if "price" in cols:
        texts += [cell(r, "price") for r in body[:50]]
    return Sheet(title, {k: headers[i] or f"#{i + 1}" for k, i in cols.items()}, out, texts)


def read_book(data: bytes, max_rows: int, only: list[str] | None = None) -> list[Sheet]:
    """Fayldagi barcha (yashirilmagan) varaqlar — har birining ustunlari alohida aniqlanadi.

    `only` — xodim tanlagan varaqlar nomlari (bo'sh/None — hammasi)."""
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl turli xato beradi
        raise ExcelError("Fayl o'qilmadi: .xlsx formatidagi Excel fayl yuklang.") from exc
    raw_sheets = []
    for ws in wb.worksheets:
        if getattr(ws, "sheet_state", "visible") != "visible":
            continue
        rows = [[_text(c) for c in r] for r in ws.iter_rows(values_only=True)]
        if any(any(r) for r in rows):
            raw_sheets.append((str(ws.title).strip(), rows))
    wb.close()
    if not raw_sheets:
        raise ExcelError("Faylda tovar topilmadi.")
    if len(raw_sheets) == 1:
        sheets = [_read_sheet(*raw_sheets[0], strict=False)]
    else:
        sheets = [x for x in (_read_sheet(t, rows, strict=True) for t, rows in raw_sheets) if x]
        if not sheets:  # hech bir varaq jadvalga o'xshamadi — birinchisining aniq xatosi ko'rsatiladi
            sheets = [_read_sheet(*raw_sheets[0], strict=False)]
        if len(sheets) > 1:
            for sh in sheets:
                for r in sh.rows:
                    r.raw = {SHEET_KEY: sh.name, **r.raw}
    if only:
        sheets = [sh for sh in sheets if sh.name in set(only)]
        if not sheets:
            raise ExcelError("Tanlangan varaqlarda tovar topilmadi.")
    if sum(len(sh.rows) for sh in sheets) > max_rows:
        raise ExcelError(
            f"Bir yuklashda ko'pi bilan {max_rows} ta tovar bo'lishi mumkin — varaqlarni bo'lib yuklang."
        )
    return sheets


def read_rows(data: bytes, max_rows: int) -> tuple[dict[str, str], list[Row], str]:
    """Qaytaradi: ({kalit: sarlavha} — birinchi varaqniki, barcha varaqlar qatorlari, valyuta)."""
    sheets = read_book(data, max_rows)
    rows = [r for sh in sheets for r in sh.rows]
    return sheets[0].columns, rows, detect_currency([t for sh in sheets for t in sh.texts])
