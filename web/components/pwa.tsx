"use client";

import { useEffect, useState } from "react";

// Xodim va kuryer ilovalari (PWA): service worker ro'yxatdan o'tkazish va "Ilovani o'rnatish" tugmasi.

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

export function usePwa(scope: "/xodim" | "/kuryer") {
  const [prompt, setPrompt] = useState<InstallEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js", { scope }).catch(() => {});
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    setInstalled(standalone);
    setIos(/iphone|ipad|ipod/i.test(navigator.userAgent));
    const onPrompt = (e: Event) => {
      e.preventDefault(); // tugmani o'zimiz ko'rsatamiz
      setPrompt(e as InstallEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setPrompt(null);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, [scope]);

  const install = async () => {
    if (!prompt) return;
    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    if (outcome === "accepted") setInstalled(true);
    setPrompt(null);
  };
  return { canInstall: !!prompt && !installed, installed, ios: ios && !installed, install };
}

export function InstallButton({ scope }: { scope: "/xodim" | "/kuryer" }) {
  const { canInstall, ios, install } = usePwa(scope);
  const [hint, setHint] = useState(false);
  if (canInstall) {
    return (
      <button onClick={install} className="rounded-xl bg-white px-3 py-2 text-sm font-semibold text-gray-900 hover:bg-gray-100">
        Ilovani o&apos;rnatish
      </button>
    );
  }
  if (ios) {
    return (
      <span className="relative">
        <button onClick={() => setHint((v) => !v)} className="rounded-xl bg-white/10 px-3 py-2 text-sm hover:bg-white/20">
          O&apos;rnatish
        </button>
        {hint ? (
          <span className="absolute right-0 top-11 z-50 w-64 rounded-xl bg-white p-3 text-xs text-gray-800 shadow-xl">
            Safari&apos;da pastdagi «Ulashish» tugmasini bosing → «Bosh ekranga qo&apos;shish» (Add to Home Screen).
          </span>
        ) : null}
      </span>
    );
  }
  return null;
}

/** Manifest havolasi `crossorigin="use-credentials"` bilan: yopiq (private) serverda manifest ham kirish cookie'si
 * bilan so'raladi (aks holda brauzer uni ololmaydi va ilova o'rnatilmaydi). SSR'da React bu atributni
 * tushirib qoldiradi — shuning uchun brauzerda qo'shiladi. */
export function ManifestLink({ href }: { href: string }) {
  useEffect(() => {
    document.querySelectorAll('link[rel="manifest"]').forEach((el) => el.remove());
    const link = document.createElement("link");
    link.rel = "manifest";
    link.href = href;
    link.crossOrigin = "use-credentials";
    document.head.appendChild(link);
    return () => link.remove();
  }, [href]);
  return null;
}
