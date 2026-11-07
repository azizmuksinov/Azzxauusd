import type { Metadata } from "next";

import { Header } from "@/components/header";
import { AppProvider } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Texno Do'kon — demo",
  description: "Maishiy texnika va elektronika onlayn do'koni (demo)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz">
      <body>
        <AppProvider>
          <Header />
          <main className="mx-auto min-h-[70vh] max-w-7xl px-4 py-6">{children}</main>
          <footer className="mt-10 border-t bg-white py-6 text-center text-sm text-gray-500">
            © Texno Do'kon · demo ·{" "}
            <a href="/admin/" className="text-brand hover:underline">Admin</a> ·{" "}
            <a href="/api/docs/" className="text-brand hover:underline">API</a>
          </footer>
        </AppProvider>
      </body>
    </html>
  );
}
