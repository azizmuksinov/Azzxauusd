// Inline SVG ikonkalar (stroke, 24x24) — tashqi kutubxonasiz.
type P = { className?: string };
const base = (path: React.ReactNode, cls = "h-6 w-6") => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden>
    {path}
  </svg>
);

export const IconSearch = ({ className }: P) => base(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>, className);
export const IconCart = ({ className }: P) => base(<><circle cx="9" cy="20" r="1.4" /><circle cx="18" cy="20" r="1.4" /><path d="M2.5 3h2.6l2.4 12.2a1.6 1.6 0 0 0 1.6 1.3h8.6a1.6 1.6 0 0 0 1.6-1.2L21 7H6" /></>, className);
export const IconHeart = ({ className, filled }: P & { filled?: boolean }) => (
  <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" className={className ?? "h-6 w-6"} aria-hidden>
    <path d="M12 20.5s-7.5-4.6-9.3-9.6C1.5 7.4 3.8 4 7.3 4c2 0 3.5 1 4.7 2.6C13.2 5 14.7 4 16.7 4c3.5 0 5.8 3.4 4.6 6.9-1.8 5-9.3 9.6-9.3 9.6Z" />
  </svg>
);
export const IconUser = ({ className }: P) => base(<><circle cx="12" cy="8" r="4" /><path d="M4 21c1.2-4 4.3-6 8-6s6.8 2 8 6" /></>, className);
export const IconBox = ({ className }: P) => base(<><path d="M21 8 12 3 3 8v8l9 5 9-5V8Z" /><path d="m3 8 9 5 9-5M12 13v8" /></>, className);
export const IconMenu = ({ className }: P) => base(<path d="M4 6h16M4 12h16M4 18h10" />, className);
export const IconClose = ({ className }: P) => base(<path d="M6 6l12 12M18 6 6 18" />, className);
export const IconPin = ({ className }: P) => base(<><path d="M12 21s-7-6.3-7-11.5A7 7 0 0 1 19 9.5C19 14.7 12 21 12 21Z" /><circle cx="12" cy="9.5" r="2.5" /></>, className);
export const IconPhone = ({ className }: P) => base(<path d="M5 3h3l2 5-2.5 1.5a11 11 0 0 0 7 7L16 14l5 2v3a2 2 0 0 1-2 2A17 17 0 0 1 3 5a2 2 0 0 1 2-2Z" />, className);
export const IconTruck = ({ className }: P) => base(<><path d="M2 6h11v10H2zM13 9h4.5L21 12.5V16h-8" /><circle cx="6.5" cy="17.5" r="1.8" /><circle cx="17" cy="17.5" r="1.8" /></>, className);
export const IconShield = ({ className }: P) => base(<><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6l-8-3Z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>, className);
export const IconEye = ({ className }: P) => base(<><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>, className);
export const IconCard = ({ className }: P) => base(<><rect x="2.5" y="5" width="19" height="14" rx="2.5" /><path d="M2.5 10h19M6 15h4" /></>, className);
export const IconChevron = ({ className }: P) => base(<path d="m9 6 6 6-6 6" />, className);
export const IconCheck = ({ className }: P) => base(<path d="m5 12.5 4.5 4.5L19 7.5" />, className);
export const IconPlus = ({ className }: P) => base(<path d="M12 5v14M5 12h14" />, className);
export const IconMinus = ({ className }: P) => base(<path d="M5 12h14" />, className);
export const IconTrash = ({ className }: P) => base(<><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></>, className);
export const IconStar = ({ className, filled = true }: P & { filled?: boolean }) => (
  <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={1.5} className={className ?? "h-4 w-4"} aria-hidden>
    <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3Z" />
  </svg>
);
export const IconHome = ({ className }: P) => base(<><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10v10h13V10" /><path d="M10 20v-5h4v5" /></>, className);

export const IconScale = ({ className }: P) => base(<><path d="M12 4v16M7 20h10M5 7h14" /><path d="M5 7 2.5 13a2.6 2.6 0 0 0 5 0L5 7ZM19 7l-2.5 6a2.6 2.6 0 0 0 5 0L19 7Z" /></>, className);
export const IconShare = ({ className }: P) => base(<><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" /></>, className);
export const IconFilter = ({ className }: P) => base(<path d="M4 6h16M7 12h10M10 18h4" />, className);
export const IconMoon = ({ className }: P) => base(<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />, className);
export const IconSun = ({ className }: P) => base(<><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>, className);
export const IconChat = ({ className }: P) => base(<><path d="M4 5.5h16v10.5H9.5L5 19.5V16H4Z" /><path d="M8 9.5h8M8 12.5h5" /></>, className);
