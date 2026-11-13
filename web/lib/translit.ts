// O'zbek lotin -> kirill (backend apps/core/translit.py bilan bir xil qoidalar).
const DIGRAPHS: [string, string][] = [["o'", "ў"], ["g'", "ғ"], ["sh", "ш"], ["ch", "ч"], ["yo", "ё"], ["yu", "ю"], ["ya", "я"]];
const SINGLE: Record<string, string> = {
  a: "а", b: "б", d: "д", e: "е", f: "ф", g: "г", h: "ҳ", i: "и", j: "ж", k: "к", l: "л", m: "м", n: "н",
  o: "о", p: "п", q: "қ", r: "р", s: "с", t: "т", u: "у", v: "в", x: "х", y: "й", z: "з", c: "с",
};
const VOWELS = new Set("aeiouAEIOU");
const isAlpha = (c: string) => /\p{L}/u.test(c);

function applyCase(src: string, dst: string) {
  if (src.length > 1 && src === src.toUpperCase() && src !== src.toLowerCase()) return dst.toUpperCase();
  if (src[0] !== src[0].toLowerCase()) return dst[0].toUpperCase() + dst.slice(1);
  return dst;
}

export function latinToCyrillic(input: string): string {
  const text = input.replace(/[ʻʼ‘’`]/g, "'");
  let out = "";
  for (let i = 0; i < text.length; ) {
    const ch = text[i];
    const prev = i > 0 ? text[i - 1] : "";
    const wordStart = !isAlpha(prev) && prev !== "'";
    const pair = text.slice(i, i + 2);
    const match = DIGRAPHS.find(([lat]) => pair.toLowerCase() === lat && !(lat === "yo" && text[i + 2] === "'"));
    if (match) {
      out += applyCase(pair === pair.toUpperCase() ? pair : pair[0], match[1]);
      i += 2;
      continue;
    }
    const low = ch.toLowerCase();
    if (low === "e") out += applyCase(ch, wordStart || VOWELS.has(prev) ? "э" : "е");
    else if (ch === "'") out += isAlpha(prev) ? "ъ" : ch;
    else if (SINGLE[low]) out += applyCase(ch, SINGLE[low]);
    else out += ch;
    i += 1;
  }
  return out;
}
