// Demo tovarlari uchun SVG illyustratsiyalar (haqiqiy rasm yuklanmaguncha). Kategoriya bo'yicha tanlanadi,
// rang varianti tovar ID'siga qarab o'zgaradi — kartochkalar bir xil ko'rinmasin.

const PALETTES = [
  { bg: "#f3efff", body: "#2b2d42", accent: "#7c3aed", glow: "#c4b5fd" },
  { bg: "#eef6ff", body: "#1e293b", accent: "#2563eb", glow: "#93c5fd" },
  { bg: "#effaf5", body: "#334155", accent: "#059669", glow: "#6ee7b7" },
  { bg: "#fff4ec", body: "#3f3f46", accent: "#ea580c", glow: "#fdba74" },
  { bg: "#fdf2f8", body: "#1f2937", accent: "#db2777", glow: "#f9a8d4" },
];

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

export function Illustration({ category, seed = 0, className = "" }: { category: string; seed?: number; className?: string }) {
  const p = PALETTES[Math.abs(seed) % PALETTES.length];
  const kind = kindOf(category);
  // Konteyner kvadrat bo'lmasa ham (4:3, 4:5) fon butun maydonni egallaydi, rasm markazda qoladi.
  return (
    <div className="flex h-full w-full items-center justify-center" style={{ background: p.bg }}>
    <svg viewBox="0 0 200 200" className={`h-full w-full ${className}`} role="img" aria-label={kind}>
      <defs>
        <radialGradient id={`g${seed}${kind}`} cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor={p.glow} stopOpacity="0.55" />
          <stop offset="100%" stopColor={p.bg} stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`s${seed}${kind}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
          <stop offset="60%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="200" height="200" fill={p.bg} />
      <circle cx="100" cy="95" r="80" fill={`url(#g${seed}${kind})`} />
      <ellipse cx="100" cy="172" rx="56" ry="7" fill="#000" opacity="0.07" />
      {SHAPES[kind](p, `s${seed}${kind}`)}
    </svg>
    </div>
  );
}

type Pal = (typeof PALETTES)[number];
const SHAPES: Record<Kind, (p: Pal, shine: string) => React.ReactNode> = {
  phone: (p, s) => (
    <g>
      <rect x="66" y="28" width="68" height="138" rx="14" fill={p.body} />
      <rect x="71" y="34" width="58" height="126" rx="10" fill={p.accent} />
      <rect x="71" y="34" width="58" height="126" rx="10" fill={`url(#${s})`} />
      <rect x="90" y="38" width="20" height="5" rx="2.5" fill={p.body} />
      <circle cx="100" cy="92" r="16" fill="#fff" opacity="0.25" />
      <rect x="82" y="128" width="36" height="5" rx="2.5" fill="#fff" opacity="0.5" />
    </g>
  ),
  tv: (p, s) => (
    <g>
      <rect x="22" y="40" width="156" height="98" rx="8" fill={p.body} />
      <rect x="28" y="46" width="144" height="86" rx="4" fill={p.accent} />
      <path d="M28 120 70 80l30 26 22-18 50 32v12H28Z" fill="#fff" opacity="0.18" />
      <rect x="28" y="46" width="144" height="86" rx="4" fill={`url(#${s})`} />
      <rect x="92" y="138" width="16" height="16" fill={p.body} />
      <rect x="66" y="154" width="68" height="6" rx="3" fill={p.body} />
    </g>
  ),
  laptop: (p, s) => (
    <g>
      <rect x="42" y="42" width="116" height="80" rx="7" fill={p.body} />
      <rect x="48" y="48" width="104" height="68" rx="3" fill={p.accent} />
      <rect x="48" y="48" width="104" height="68" rx="3" fill={`url(#${s})`} />
      <path d="M26 124h148l-10 20H36Z" fill={p.body} opacity="0.85" />
      <rect x="86" y="126" width="28" height="4" rx="2" fill="#fff" opacity="0.4" />
    </g>
  ),
  fridge: (p, s) => (
    <g>
      <rect x="60" y="20" width="80" height="150" rx="10" fill="#e5e7eb" />
      <rect x="60" y="20" width="80" height="150" rx="10" fill={`url(#${s})`} />
      <rect x="60" y="74" width="80" height="3" fill="#cbd5e1" />
      <rect x="126" y="38" width="5" height="24" rx="2.5" fill={p.accent} />
      <rect x="126" y="90" width="5" height="34" rx="2.5" fill={p.accent} />
      <rect x="72" y="32" width="22" height="10" rx="3" fill={p.accent} opacity="0.35" />
    </g>
  ),
  washer: (p, s) => (
    <g>
      <rect x="48" y="30" width="104" height="134" rx="12" fill="#f1f5f9" stroke="#cbd5e1" strokeWidth="2" />
      <rect x="48" y="30" width="104" height="26" rx="12" fill="#e2e8f0" />
      <circle cx="132" cy="43" r="6" fill={p.accent} />
      <rect x="62" y="40" width="34" height="6" rx="3" fill="#94a3b8" />
      <circle cx="100" cy="108" r="38" fill={p.body} />
      <circle cx="100" cy="108" r="30" fill={p.accent} opacity="0.75" />
      <path d="M72 112c10 8 22 10 28 4s18-6 28 2" stroke="#fff" strokeWidth="4" fill="none" opacity="0.5" />
      <circle cx="100" cy="108" r="30" fill={`url(#${s})`} />
    </g>
  ),
  ac: (p, s) => (
    <g>
      <rect x="20" y="62" width="160" height="58" rx="14" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="2" />
      <rect x="20" y="62" width="160" height="58" rx="14" fill={`url(#${s})`} />
      <rect x="32" y="104" width="136" height="6" rx="3" fill="#cbd5e1" />
      <circle cx="160" cy="78" r="4" fill={p.accent} />
      <path d="M60 132c0 10 8 10 8 20M100 132c0 10 8 10 8 20M140 132c0 10 8 10 8 20" stroke={p.accent} strokeWidth="4" strokeLinecap="round" fill="none" opacity="0.7" />
    </g>
  ),
  generic: (p) => (
    <g>
      <path d="M100 34 158 64v64l-58 30-58-30V64Z" fill={p.accent} opacity="0.85" />
      <path d="M42 64 100 94l58-30M100 94v64" stroke="#fff" strokeWidth="3" fill="none" opacity="0.6" />
    </g>
  ),
};
