import type { Metadata, Viewport } from "next";

import { ManifestLink } from "@/components/pwa";

// Telefonga ilova (PWA) sifatida o'rnatish: manifest, belgilar, iOS sozlamalari.
export const metadata: Metadata = {
  title: "TexnoDo'kon — Kuryer",
  icons: { icon: "/icons/kuryer-192.png", apple: "/icons/kuryer-apple-180.png" },
  appleWebApp: { capable: true, title: "Kuryer", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { themeColor: "#111827" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ManifestLink href="/manifest-kuryer.webmanifest" />
      {children}
    </>
  );
}
