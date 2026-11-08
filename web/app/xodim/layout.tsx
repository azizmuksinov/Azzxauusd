import type { Metadata, Viewport } from "next";

import { ManifestLink } from "@/components/pwa";

// Telefonga ilova (PWA) sifatida o'rnatish: manifest, belgilar, iOS sozlamalari.
export const metadata: Metadata = {
  title: "TexnoDo'kon — Xodim paneli",
  icons: { icon: "/icons/xodim-192.png", apple: "/icons/xodim-apple-180.png" },
  appleWebApp: { capable: true, title: "Xodim", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { themeColor: "#6d28d9" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ManifestLink href="/manifest-xodim.webmanifest" />
      {children}
    </>
  );
}
