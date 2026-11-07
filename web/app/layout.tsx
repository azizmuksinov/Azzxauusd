import type { Metadata, Viewport } from "next";

import { Footer } from "@/components/footer";
import { Header } from "@/components/header";
import { AppProvider } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "TexnoDo'kon — maishiy texnika va elektronika (demo)",
  description: "Maishiy texnika va elektronika onlayn do'koni: eshikkacha yetkazish, eshik oldida tekshirish (demo)",
  icons: { icon: "/favicon.svg" },
};

export const viewport: Viewport = { themeColor: "#6d28d9" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz">
      <body>
        <AppProvider>
          <Header />
          <main className="mx-auto min-h-[70vh] max-w-7xl px-4 py-6">{children}</main>
          <Footer />
        </AppProvider>
      </body>
    </html>
  );
}
