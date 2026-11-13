"""Rasm sifati — AI'siz, bepul (Pillow bilan hisoblanadi).

Nima uchun: bir xil ishonchli manbadan bir nechta rasm topilganda qaysi biri asosiy bo'lishi kerakligini
va qaysi biri umuman yaramasligini (banner, bo'sh rasm, xira eskiz) bilish kerak. Shuningdek do'konda
suratlar bir xil ko'rinsin: oq fondagi surat chetidagi bo'sh joy kesiladi va kvadrat qilib tekislanadi.

- `analyse(content)` → Quality: o'lcham, fon oqligi, tovar kadrni qanchalik to'ldirgani, aniqlik, baho (0–100)
  va `problem` (bo'sh bo'lmasa — rasm olinmaydi).
- `normalize(content)` → do'kon uchun tayyor fayl (kvadrat, chetlari tekis, ko'pi bilan 1600 px).
"""

import io
from dataclasses import dataclass

MAX_SIDE = 1600  # do'konda saqlanadigan eng katta tomon
MARGIN = 0.06  # tekislanganda tovar atrofida qoladigan bo'sh joy (tomonning ulushi)
WHITE = 236  # shundan yorug' piksel — "oq fon"
BANNER_RATIO = 2.6  # tomonlar nisbati bundan katta — banner yoki chiziqcha, tovar surati emas


@dataclass
class Quality:
    width: int
    height: int
    white_bg: float  # chet piksellarining qancha qismi oq (0..1)
    fill: float  # oq fonda tovar egallagan maydon ulushi (0..1); boshqa fonda 1.0
    sharp: float  # aniqlik (chegaralar kuchi); xira yoki kattalashtirilgan eskizda past
    score: int  # 0..100 — kattasi yaxshi
    problem: str = ""  # bo'sh emas — rasm yaramaydi (sababi o'zbekcha)

    @property
    def clean(self) -> bool:
        """Toza katalog surati: oq fonda, tovar kadrni yetarlicha to'ldirgan."""
        return self.white_bg >= 0.85 and self.fill >= 0.12 and not self.problem


def _open(content: bytes):
    """RGB (shaffof fon oq deb olinadi). O'qilmasa — None."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.split()[-1])
                return flat
            return im.convert("RGB")
    except Exception:  # noqa: BLE001 — buzuq yoki noma'lum turdagi fayl
        return None


def _border(im) -> list[tuple[int, int, int]]:
    """Chetdagi (≈4% qalinlikdagi hoshiya) piksellar — fon rangini aniqlash uchun."""
    w, h = im.size
    t = max(1, min(w, h) // 25)
    px = im.load()
    step_x, step_y = max(1, w // 64), max(1, h // 64)
    out = []
    for x in range(0, w, step_x):
        out += [px[x, y] for y in (0, t - 1, h - t, h - 1)]
    for y in range(0, h, step_y):
        out += [px[x, y] for x in (0, t - 1, w - t, w - 1)]
    return out


def _content_box(im, bg: tuple[int, int, int], tolerance: int = 18):
    """Fondan farq qiladigan qism chegarasi (x0, y0, x1, y1) yoki None (hammasi fon)."""
    from PIL import Image, ImageChops, ImageFilter

    diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L")
    # Yakka "shovqin" piksellari (JPEG siqish izlari) hisobga olinmaydi.
    mask = diff.point(lambda v: 255 if v > tolerance else 0).filter(ImageFilter.MedianFilter(3))
    return mask.getbbox()


def _sharpness(im) -> float:
    """Mayda tafsilotlar ulushi (0..1 atrofida): aniq suratda yuqori, xira (kattalashtirilgan) eskizda past.

    Suratning ozgina va kuchli xiralashtirilgan nusxalaridan farqi solishtiriladi — o'lcham va yorug'likka
    bog'liq emas.
    """
    from PIL import ImageChops, ImageFilter, ImageStat

    gray = im.convert("L")
    gray.thumbnail((512, 512))  # bir xil masshtabda: katta surat kichraytirilgani uchun "xira" chiqmasin
    fine = ImageStat.Stat(ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(1.2)))).mean[0]
    coarse = ImageStat.Stat(ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(6)))).mean[0]
    return fine / coarse if coarse > 0.2 else 0.0


def _median(values: list[int]) -> int:
    values = sorted(values)
    return values[len(values) // 2]


def analyse(content: bytes) -> Quality | None:
    im = _open(content)
    if im is None:
        return None
    from PIL import ImageStat

    w, h = im.size
    small = im.copy()
    small.thumbnail((256, 256))
    border = _border(small)
    white_bg = sum(1 for p in border if min(p) >= WHITE) / len(border)
    gray = small.convert("L")
    spread = ImageStat.Stat(gray).stddev[0]
    fill = 1.0
    if white_bg >= 0.85:
        box = _content_box(small, (255, 255, 255), 255 - WHITE + 6)
        sw, sh = small.size
        fill = ((box[2] - box[0]) * (box[3] - box[1]) / (sw * sh)) if box else 0.0
    sharp = _sharpness(im)

    problem = ""
    ratio = max(w, h) / max(1, min(w, h))
    if ratio > BANNER_RATIO:
        problem = f"banner yoki chiziqcha ({w}x{h})"
    elif spread < 4:
        problem = "bo'sh rasm (bir xil rang)"
    elif white_bg >= 0.85 and fill < 0.03:
        problem = "deyarli bo'sh rasm"

    score = 40 * min(min(w, h), 1200) / 1200  # o'lcham
    score += 22 * max(0.0, min(1.0, (white_bg - 0.4) / 0.5))  # oq fon — katalog surati
    score += 18 * (min(fill, 0.45) / 0.45 if white_bg >= 0.85 else 0.5)  # tovar kadrda yirik
    score += 20 * max(0.0, min((sharp - 0.12) / 0.25, 1.0))  # aniqlik
    if ratio > 1.9:
        score -= 10  # juda cho'zinchoq — kartochkada kichik ko'rinadi
    return Quality(w, h, round(white_bg, 2), round(fill, 2), round(sharp, 3), max(0, round(score)), problem)


def normalize(content: bytes) -> tuple[bytes, str] | None:
    """Do'kon uchun tayyorlash: (fayl, kengaytma). O'zgartirish shart bo'lmasa yoki o'qilmasa — None.

    Oq (yoki och bir tekis) fondagi surat: chetidagi bo'sh joy kesiladi, tovar kvadrat kadr markaziga
    bir xil hoshiya bilan qo'yiladi — ro'yxatda hamma tovar bir xil kattalikda ko'rinadi. Boshqa suratlar
    (xonadagi ko'rinish va h.k.) faqat kerak bo'lsa kichraytiriladi.
    """
    im = _open(content)
    if im is None:
        return None
    from PIL import Image

    w, h = im.size
    small = im.copy()
    small.thumbnail((256, 256))
    border = _border(small)
    light = sum(1 for p in border if min(p) >= WHITE) / len(border)
    changed = False
    bg = tuple(_median([p[i] for p in border]) for i in range(3))
    # Fon bir tekis bo'lsagina kesiladi (gradient yoki naqshli fonda yangi hoshiya "tikuv" bo'lib ko'rinardi).
    even = sum(1 for p in border if max(abs(p[i] - bg[i]) for i in range(3)) <= 5) / len(border)
    if light >= 0.9 and even >= 0.9:
        box = _content_box(im, bg, 5)
        bw, bh = (box[2] - box[0], box[3] - box[1]) if box else (0, 0)
        # Topilgan qism juda kichik bo'lsa (oq tovar oq fonda: faqat dastasi ko'ringan) — tegilmaydi.
        if box and bw * bh >= 0.1 * w * h:
            side = round(max(bw, bh) * (1 + 2 * MARGIN))
            # Tovar allaqachon kvadrat kadrda va hoshiyasi me'yorda bo'lsa — tegilmaydi.
            if abs(w - h) > 0.02 * max(w, h) or abs(side - max(w, h)) > 0.08 * max(w, h):
                canvas = Image.new("RGB", (side, side), bg)
                canvas.paste(im.crop(box), ((side - bw) // 2, (side - bh) // 2))
                im, changed = canvas, True
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        changed = True
    if not changed:
        return None
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue(), "jpg"
