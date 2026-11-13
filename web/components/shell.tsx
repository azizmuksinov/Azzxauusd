"use client";

import { usePathname } from "next/navigation";

/** Sahifa asosi: xodim panelida (chap menyu + keng jadvallar) kengroq, do'konda — odatdagidek. */
export function MainShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const wide = pathname.startsWith("/xodim") && !pathname.startsWith("/xodim/kirish");
  return (
    <main className={`mx-auto min-h-[70vh] px-4 pb-10 pt-4 md:pb-8 md:pt-6 ${wide ? "max-w-[1600px]" : "max-w-7xl"}`}>
      {children}
    </main>
  );
}
