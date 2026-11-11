import type { Metadata, Viewport } from "next";

import { CompareBar } from "@/components/compare";
import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
import { BottomNav } from "@/components/product-extras";
import { AppProvider } from "@/components/providers";
import { MainShell } from "@/components/shell";

import "./globals.css";

export const metadata: Metadata = {
  title: "TexnoDo'kon — maishiy texnika va elektronika (demo)",
  description: "Maishiy texnika va elektronika onlayn do'koni: eshikkacha yetkazish, eshik oldida tekshirish (demo)",
  icons: { icon: "/favicon.svg" },
};

export const viewport: Viewport = { themeColor: "#7c3aed" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz">
      <body>
        <AppProvider>
          <Header />
          <MainShell>{children}</MainShell>
          <Footer />
          <CompareBar />
          <BottomNav />
        </AppProvider>
      </body>
    </html>
  );
}
