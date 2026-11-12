// Rasm yuklanmagan tovarlar uchun neytral belgi: kulrang fon va kategoriya siluetining ingichka chizig'i.
// Bosh sahifadagi kategoriya katakchalarida esa rangli (tinted) ko'rinishi ishlatiladi.
// Haqiqiy rasm (admin panel yoki Excel import) yuklanganda avtomatik o'sha ko'rsatiladi.

type Kind = "phone" | "tv" | "laptop" | "fridge" | "washer" | "ac" | "generic";

export function kindOf(categorySlug: string): Kind {
  if (/smartfon|telefon/.test(categorySlug)) return "phone";
  if (/televizor/.test(categorySlug)) return "tv";
  if (/noutbuk/.test(categorySlug)) return "laptop";
  if (/muzlatkich/.test(categorySlug)) return "fridge";
  if (/kir-yuvish/.test(categorySlug)) return "washer";
  if (/konditsioner/.test(categorySlug)) return "ac";
  return "generic";
}

const SHAPES: Record<Kind, React.ReactNode> = {
  phone: (
    <>
      <rect x="36" y="18" width="28" height="64" rx="6" />
      <path d="M46 23h8" />
      <path d="M45 76h10" />
    </>
  ),
  tv: (
    <>
      <rect x="14" y="26" width="72" height="44" rx="3" />
      <path d="M42 78h16M50 70v8" />
    </>
  ),
  laptop: (
    <>
      <rect x="24" y="28" width="52" height="34" rx="3" />
      <path d="M16 70h68l-4 6H20Z" />
    </>
  ),
  fridge: (
    <>
      <rect x="32" y="14" width="36" height="72" rx="4" />
      <path d="M32 40h36M61 24v8M61 48v12" />
    </>
  ),
  washer: (
    <>
      <rect x="26" y="16" width="48" height="68" rx="5" />
      <path d="M26 28h48" />
      <circle cx="50" cy="56" r="16" />
      <circle cx="64" cy="22" r="1.5" />
    </>
  ),
  ac: (
    <>
      <rect x="14" y="34" width="72" height="24" rx="6" />
      <path d="M22 50h56M34 66v6M50 66v8M66 66v6" />
    </>
  ),
  generic: (
    <>
      <path d="M50 18 80 33v34L50 82 20 67V33Z" />
      <path d="M20 33l30 15 30-15M50 48v34" />
    </>
  ),
};

/** Har bir tur uchun o'z pastel rangi: fon va chiziq (kategoriya katakchalari jonli ko'rinsin). */
export const TINTS: Record<Kind, { bg: string; stroke: string }> = {
  phone: { bg: "bg-violet-100", stroke: "#7c3aed" },
  tv: { bg: "bg-sky-100", stroke: "#0284c7" },
  laptop: { bg: "bg-emerald-100", stroke: "#059669" },
  fridge: { bg: "bg-cyan-100", stroke: "#0891b2" },
  washer: { bg: "bg-amber-100", stroke: "#d97706" },
  ac: { bg: "bg-indigo-100", stroke: "#4f46e5" },
  generic: { bg: "bg-rose-100", stroke: "#e11d48" },
};

// Maxsus belgisi yo'q kategoriyalar bir xil rangda bo'lib qolmasin: nomiga qarab rang tanlanadi.
const EXTRA_TINTS = [
  TINTS.generic,
  { bg: "bg-orange-100", stroke: "#ea580c" },
  { bg: "bg-teal-100", stroke: "#0d9488" },
  { bg: "bg-fuchsia-100", stroke: "#c026d3" },
  { bg: "bg-lime-100", stroke: "#65a30d" },
  { bg: "bg-blue-100", stroke: "#2563eb" },
];
const hash = (text: string) => [...text].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);

export function Illustration({ category, className = "", tinted = true }: {
  category: string; seed?: number; className?: string; tinted?: boolean;
}) {
  const kind = kindOf(category);
  const tint = kind === "generic" ? EXTRA_TINTS[hash(category) % EXTRA_TINTS.length] : TINTS[kind];
  return (
    <div className={`flex h-full w-full items-center justify-center ${tinted ? tint.bg : "bg-surface"} ${className}`}>
      <svg viewBox="0 0 100 100" className="h-[46%] w-[46%]" fill="none" stroke={tinted ? tint.stroke : "#a1a1aa"} strokeWidth="2.2"
        strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={kind}>
        {SHAPES[kind]}
      </svg>
    </div>
  );
}
