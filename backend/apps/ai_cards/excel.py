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
        "model",
        "модел",
        "product",
    ],
    "sku": ["artikul", "артикул", "sku", "kod", "код", "code", "article"],
    "price": ["narx", "цена", "price", "xarid", "закуп", "стоимост", "sum", "сумма"],
    "qty": ["soni", "кол", "qty", "miqdor", "остат", "quantity"],
    "brand": ["brend", "бренд", "brand", "марка", "ishlab chiqaruvchi", "производ"],
}


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
    return found


def read_rows(data: bytes, max_rows: int) -> tuple[dict[str, str], list[Row], str]:
    """Qaytaradi: ({kalit: sarlavha}, qatorlar, valyuta). Nom ustuni topilmasa — eng uzun matnli ustun."""
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl turli xato beradi
        raise ExcelError("Fayl o'qilmadi: .xlsx formatidagi Excel fayl yuklang.") from exc
    ws = wb.worksheets[0]
    rows = [[_text(c) for c in r] for r in ws.iter_rows(values_only=True)]
    wb.close()
    header_idx = next((i for i, r in enumerate(rows[:15]) if sum(1 for c in r if c) >= 2), None)
    if header_idx is None:
        raise ExcelError("Faylda sarlavha qatori topilmadi.")
    headers = rows[header_idx]
    body = [r for r in rows[header_idx + 1 :] if any(r)]
    cols = detect_columns(headers)
    if "name" not in cols:
        lengths = [sum(len(r[i]) for r in body if i < len(r)) for i in range(len(headers))]
        if not lengths or max(lengths) == 0:
            raise ExcelError("Tovar nomi ustuni topilmadi.")
        cols["name"] = lengths.index(max(lengths))

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
        qty = _decimal(cell(r, "qty"))
        out.append(
            Row(
                number=n,
                name=name[:500],
                sku=cell(r, "sku")[:64],
                price=_decimal(cell(r, "price")),
                qty=int(qty) if qty is not None else None,
                brand=cell(r, "brand"),
                raw={headers[i] or f"#{i + 1}": v for i, v in enumerate(r) if v},
            )
        )
        if len(out) > max_rows:
            raise ExcelError(f"Bir faylda ko'pi bilan {max_rows} ta tovar bo'lishi mumkin.")
    if not out:
        raise ExcelError("Faylda tovar topilmadi.")
    texts = [c for r in rows[: header_idx + 1] for c in r]  # sarlavha va undan yuqoridagi qatorlar
    if "price" in cols:
        texts += [cell(r, "price") for r in body[:50]]
    columns = {k: headers[i] or f"#{i + 1}" for k, i in cols.items()}
    return columns, out, detect_currency(texts)
