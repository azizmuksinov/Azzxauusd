// Brend belgisi: sakkiz qirrali yulduz (ikki kvadrat) — feruza koshin naqshidan.
export function Star8({ className = "h-5 w-5", filled = false }: { className?: string; filled?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill={filled ? "currentColor" : "none"} stroke="currentColor"
      strokeWidth={filled ? 0 : 2.4} strokeLinejoin="round" aria-hidden>
      <path d="M16 2.5 19.96 6.44H25.56V12.04L29.5 16 25.56 19.96V25.56H19.96L16 29.5 12.04 25.56H6.44V19.96L2.5 16 6.44 12.04V6.44H12.04Z" />
    </svg>
  );
}
